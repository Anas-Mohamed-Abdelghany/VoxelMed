import React, { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import useStore from '../store/useStore';
import {
  getSliceAsBase64,
  getSegmentationSliceAsBase64,
  performMeasurement,
  drawSegmentation,
} from '../api/client';
import VolumeRenderer from './VolumeRenderer';

// Fixed Anatomical Compass when Sagittal/Coronal are rotated 180°
const COMPASS_LABELS = {
  axial: { top: 'A', bottom: 'P', left: 'R', right: 'L' },
  sagittal: { top: 'S', bottom: 'I', left: 'A', right: 'P' },
  coronal: { top: 'S', bottom: 'I', left: 'R', right: 'L' },
};

function SlicePanel({ view, label, accentColor, maximizedView, onToggleMaximize }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  const isDrawing = useRef(false);
  const strokePoints = useRef([]);
  const caliperStart = useRef(null);

  const [activeCaliper, setActiveCaliper] = useState(null);
  const [sliceImg, setSliceImg] = useState(null);
  const [maskImg, setMaskImg] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cursorPos, setCursorPos] = useState(null); // Real-time brush cursor outline

  const {
    currentSlice,
    setSlice,
    setCurrentSliceForAll,
    windowCenter,
    windowWidth,
    volumeInfo,
    activeTool,
    brushSize,
    eraserSize,
    drawingColor,
    viewSettings,
    segmentationActive,
    setSegmentationActive,
    showCrosshair,
    measurements,
    addMeasurement,
  } = useStore();

  const sliceIndex = currentSlice[view] || 0;
  const settings = viewSettings[view] || {
    zoom: 1,
    brightness: 0,
    contrast: 100,
    rotate: view === 'axial' ? 0 : 180,
  };

  const maxSlice = useMemo(() => {
    if (!volumeInfo?.shape) return 1;
    return (
      (view === 'axial'
        ? volumeInfo.shape[0]
        : view === 'sagittal'
        ? volumeInfo.shape[2]
        : volumeInfo.shape[1]) - 1 || 1
    );
  }, [volumeInfo, view]);

  // 1. Fetch CT Slice
  useEffect(() => {
    let cancelled = false;
    async function fetchSlice() {
      setLoading(true);
      try {
        const res = await getSliceAsBase64(view, sliceIndex, windowCenter, windowWidth);
        if (!cancelled && res.image) {
          const img = new Image();
          img.onload = () => {
            setSliceImg(img);
            setLoading(false);
          };
          img.src = `data:image/png;base64,${res.image}`;
        }
      } catch (err) {
        if (!cancelled) setLoading(false);
      }
    }
    if (volumeInfo) fetchSlice();
    return () => { cancelled = true; };
  }, [view, sliceIndex, windowCenter, windowWidth, volumeInfo]);

  // 2. Fetch Segmentation Mask (transparent RGBA)
  const refreshMask = useCallback(async () => {
    try {
      const res = await getSegmentationSliceAsBase64(view, sliceIndex);
      if (res.image) {
        const img = new Image();
        img.onload = () => setMaskImg(img);
        img.src = `data:image/png;base64,${res.image}`;
      }
    } catch (err) {}
  }, [view, sliceIndex]);

  useEffect(() => {
    if (segmentationActive) refreshMask();
    else setMaskImg(null);
  }, [segmentationActive, refreshMask]);

  // Redraw Canvas
  const redrawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !sliceImg) return;

    if (maximizedView === view) {
      const container = containerRef.current;
      if (container) {
        const rect = container.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const w = Math.floor(rect.width * dpr);
        const h = Math.floor(rect.height * dpr);
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w;
          canvas.height = h;
        }
      }
    } else {
      if (canvas.width !== sliceImg.width || canvas.height !== sliceImg.height) {
        canvas.width = sliceImg.width;
        canvas.height = sliceImg.height;
      }
    }

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (maximizedView === view) {
      const scale = Math.min(canvas.width / sliceImg.width, canvas.height / sliceImg.height);
      const dw = sliceImg.width * scale;
      const dh = sliceImg.height * scale;
      const dx = (canvas.width - dw) / 2;
      const dy = (canvas.height - dh) / 2;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(sliceImg, dx, dy, dw, dh);
    } else {
      ctx.drawImage(sliceImg, 0, 0);
    }

    // 2. Draw segmentation mask (RGBA: background is completely transparent, no darkening!)
    if (maskImg) {
      ctx.save();
      ctx.globalAlpha = 0.65;
      if (maximizedView === view) {
        const scale = Math.min(canvas.width / maskImg.width, canvas.height / maskImg.height);
        const dw = maskImg.width * scale;
        const dh = maskImg.height * scale;
        const dx = (canvas.width - dw) / 2;
        const dy = (canvas.height - dh) / 2;
        ctx.drawImage(maskImg, dx, dy, dw, dh);
      } else {
        ctx.drawImage(maskImg, 0, 0);
      }
      ctx.restore();
    }

    // Helper: convert image coords to canvas coords (scales when maximized)
    const toCanvas = (ix, iy) => {
      if (maximizedView === view && sliceImg) {
        const s = Math.min(canvas.width / sliceImg.width, canvas.height / sliceImg.height);
        const dw = sliceImg.width * s;
        const dh = sliceImg.height * s;
        const ox = (canvas.width - dw) / 2;
        const oy = (canvas.height - dh) / 2;
        return [ox + ix * s, oy + iy * s];
      }
      return [ix, iy];
    };

    // 3. Live interactive brush strokes (drawn in real-time as you drag)
    if (isDrawing.current && strokePoints.current.length > 0) {
      ctx.save();
      const currentRadius = activeTool === 'eraser' ? eraserSize : brushSize;
      ctx.strokeStyle = activeTool === 'eraser' ? 'rgba(255,255,255,0.9)' : drawingColor;
      ctx.lineWidth = currentRadius * 2 * (maximizedView === view && sliceImg
        ? Math.min(canvas.width / sliceImg.width, canvas.height / sliceImg.height) : 1);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      ctx.beginPath();
      const [sx0, sy0] = toCanvas(strokePoints.current[0][0], strokePoints.current[0][1]);
      ctx.moveTo(sx0, sy0);
      for (let i = 1; i < strokePoints.current.length; i++) {
        const [sx, sy] = toCanvas(strokePoints.current[i][0], strokePoints.current[i][1]);
        ctx.lineTo(sx, sy);
      }
      ctx.stroke();

      if (strokePoints.current.length === 1) {
        ctx.fillStyle = activeTool === 'eraser' ? 'rgba(255,255,255,0.9)' : drawingColor;
        ctx.beginPath();
        ctx.arc(sx0, sy0, currentRadius * (maximizedView === view && sliceImg
          ? Math.min(canvas.width / sliceImg.width, canvas.height / sliceImg.height) : 1), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    // 4. Live Brush Cursor Circle
    if (cursorPos && (activeTool === 'brush' || activeTool === 'smartbrush' || activeTool === 'eraser')) {
      ctx.save();
      const r = activeTool === 'eraser' ? eraserSize : brushSize;
      const [cx, cy] = toCanvas(cursorPos[0], cursorPos[1]);
      const drawR = r * (maximizedView === view && sliceImg
        ? Math.min(canvas.width / sliceImg.width, canvas.height / sliceImg.height) : 1);
      ctx.strokeStyle = activeTool === 'smartbrush' ? '#f59e0b' : '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.arc(cx, cy, drawR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // 5. Orthogonal Crosshair
    if (showCrosshair && volumeInfo?.shape) {
      let x = 0, y = 0;
      if (view === 'axial') {
        x = currentSlice.sagittal;
        y = currentSlice.coronal;
      } else if (view === 'sagittal') {
        x = currentSlice.coronal;
        y = currentSlice.axial;
      } else if (view === 'coronal') {
        x = currentSlice.sagittal;
        y = currentSlice.axial;
      }

      ctx.save();
      ctx.strokeStyle = accentColor || '#3b82f6';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      const [chx, chy] = toCanvas(x, y);
      ctx.beginPath();
      ctx.moveTo(chx, 0); ctx.lineTo(chx, canvas.height);
      ctx.moveTo(0, chy); ctx.lineTo(canvas.width, chy);
      ctx.stroke();
      ctx.restore();
    }

    // 6. Caliper Graphics
    const drawCaliper = (p1, p2, dist, color = '#22d3ee') => {
      const [cp1x, cp1y] = toCanvas(p1[0], p1[1]);
      const [cp2x, cp2y] = toCanvas(p2[0], p2[1]);
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cp1x, cp1y);
      ctx.lineTo(cp2x, cp2y);
      ctx.stroke();

      const midX = (cp1x + cp2x) / 2;
      const midY = (cp1y + cp2y) / 2;
      const text = `${dist.toFixed(1)} mm`;

      ctx.font = 'bold 11px monospace';
      ctx.fillStyle = '#000000';
      ctx.fillRect(midX - 25, midY - 9, 50, 18);
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, midX, midY);
      ctx.restore();
    };

    if (activeCaliper) {
      drawCaliper(activeCaliper.p1, activeCaliper.p2, activeCaliper.dist, '#f59e0b');
    }

    measurements
      .filter((m) => m.view === view && m.slice_index === sliceIndex)
      .forEach((m) => drawCaliper(m.point1, m.point2, m.distance_mm, '#22d3ee'));
  }, [
    sliceImg,
    maskImg,
    showCrosshair,
    currentSlice,
    view,
    volumeInfo,
    accentColor,
    activeCaliper,
    measurements,
    sliceIndex,
    drawingColor,
    brushSize,
    eraserSize,
    activeTool,
    cursorPos,
    maximizedView,
  ]);

  useEffect(() => {
    redrawCanvas();
  }, [redrawCanvas]);

  // Unified coordinate mapping for mouse and touch events
  const getRawCoords = useCallback((e) => {
    const canvas = canvasRef.current;
    if (!canvas || !sliceImg) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    // Support both mouse (clientX/clientY) and touch (touches[0]) events
    let clientX, clientY;
    if (e.touches && e.touches.length > 0) {
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else if (e.changedTouches && e.changedTouches.length > 0) {
      clientX = e.changedTouches[0].clientX;
      clientY = e.changedTouches[0].clientY;
    } else {
      clientX = e.clientX;
      clientY = e.clientY;
    }

    let cx = Math.max(0, Math.min(canvas.width - 1, (clientX - rect.left) * scaleX));
    let cy = Math.max(0, Math.min(canvas.height - 1, (clientY - rect.top) * scaleY));

    // Convert canvas coords back to image coords when maximized
    let x, y;
    if (maximizedView === view) {
      const s = Math.min(canvas.width / sliceImg.width, canvas.height / sliceImg.height);
      const dw = sliceImg.width * s;
      const dh = sliceImg.height * s;
      const ox = (canvas.width - dw) / 2;
      const oy = (canvas.height - dh) / 2;
      x = Math.round((cx - ox) / s);
      y = Math.round((cy - oy) / s);
    } else {
      x = Math.round(cx);
      y = Math.round(cy);
    }

    // Clamp to image bounds
    x = Math.max(0, Math.min(sliceImg.width - 1, x));
    y = Math.max(0, Math.min(sliceImg.height - 1, y));

    // Invert coordinates when view is rotated 180 degrees
    const rot = settings.rotate % 360;
    if (rot === 180 || rot === -180) {
      x = sliceImg.width - 1 - x;
      y = sliceImg.height - 1 - y;
    }

    return [x, y];
  }, [settings.rotate, maximizedView, view, sliceImg]);

  const syncCrosshair = useCallback((pt) => {
    if (!pt) return;
    const [x, y] = pt;
    if (view === 'axial') setCurrentSliceForAll(currentSlice.axial, x, y);
    else if (view === 'sagittal') setCurrentSliceForAll(y, currentSlice.sagittal, x);
    else if (view === 'coronal') setCurrentSliceForAll(y, x, currentSlice.coronal);
  }, [view, currentSlice, setCurrentSliceForAll]);

  const handleMouseDown = useCallback((e) => {
    const pt = getRawCoords(e);
    if (!pt) return;

    if (activeTool === 'brush' || activeTool === 'smartbrush' || activeTool === 'eraser') {
      isDrawing.current = true;
      strokePoints.current = [pt];
      redrawCanvas(); // Immediate live draw
    } else if (activeTool === 'caliper') {
      caliperStart.current = pt;
      setActiveCaliper({ p1: pt, p2: pt, dist: 0 });
    } else if (activeTool === 'move' || e.button === 0) {
      syncCrosshair(pt);
    }
  }, [activeTool, getRawCoords, syncCrosshair, redrawCanvas]);

  const handleMouseMove = useCallback((e) => {
    const pt = getRawCoords(e);
    if (!pt) return;

    setCursorPos(pt);

    if (isDrawing.current) {
      strokePoints.current.push(pt);
      redrawCanvas(); // Instant real-time visual feedback while dragging
    } else if (caliperStart.current) {
      const p1 = caliperStart.current;
      const sp = volumeInfo?.spacing || [1, 1, 1];
      const dist = Math.hypot((pt[0] - p1[0]) * sp[0], (pt[1] - p1[1]) * sp[1]);
      setActiveCaliper({ p1, p2: pt, dist });
      redrawCanvas();
    } else if (e.buttons === 1 && activeTool === 'move') {
      syncCrosshair(pt);
    } else {
      redrawCanvas();
    }
  }, [activeTool, getRawCoords, syncCrosshair, volumeInfo, redrawCanvas]);

  const handleMouseUp = useCallback(async (e) => {
    const pt = getRawCoords(e);

    if (isDrawing.current && strokePoints.current.length > 0) {
      isDrawing.current = false;
      try {
        const radiusToUse = activeTool === 'eraser' ? eraserSize : brushSize;
        await drawSegmentation(view, sliceIndex, {
          points: strokePoints.current,
          label: 1,
          erase: activeTool === 'eraser',
          radius: radiusToUse,
          smart: activeTool === 'smartbrush',
        });
        setSegmentationActive(true);
        refreshMask();
      } catch (err) {}
      strokePoints.current = [];
    }

    if (caliperStart.current && pt) {
      const p1 = caliperStart.current;
      if (p1[0] !== pt[0] || p1[1] !== pt[1]) {
        try {
          const res = await performMeasurement(view, sliceIndex, p1, pt);
          addMeasurement(res);
        } catch (err) {}
      }
      caliperStart.current = null;
      setActiveCaliper(null);
    }
    redrawCanvas();
  }, [view, sliceIndex, activeTool, brushSize, eraserSize, getRawCoords, setSegmentationActive, refreshMask, addMeasurement, redrawCanvas]);

  const handleMouseLeave = useCallback(() => {
    setCursorPos(null);
    if (isDrawing.current) {
      isDrawing.current = false;
      strokePoints.current = [];
    }
    redrawCanvas();
  }, [redrawCanvas]);

  // Touch handlers — same logic as mouse, with preventDefault to stop page scroll
  const handleTouchStart = useCallback((e) => {
    e.preventDefault();
    const pt = getRawCoords(e);
    if (!pt) return;

    setCursorPos(pt);

    if (activeTool === 'brush' || activeTool === 'smartbrush' || activeTool === 'eraser') {
      isDrawing.current = true;
      strokePoints.current = [pt];
      redrawCanvas();
    } else if (activeTool === 'caliper') {
      caliperStart.current = pt;
      setActiveCaliper({ p1: pt, p2: pt, dist: 0 });
    } else {
      syncCrosshair(pt);
    }
  }, [activeTool, getRawCoords, syncCrosshair, redrawCanvas]);

  const handleTouchMove = useCallback((e) => {
    e.preventDefault();
    const pt = getRawCoords(e);
    if (!pt) return;

    setCursorPos(pt);

    if (isDrawing.current) {
      strokePoints.current.push(pt);
      redrawCanvas();
    } else if (caliperStart.current) {
      const p1 = caliperStart.current;
      const sp = volumeInfo?.spacing || [1, 1, 1];
      const dist = Math.hypot((pt[0] - p1[0]) * sp[0], (pt[1] - p1[1]) * sp[1]);
      setActiveCaliper({ p1, p2: pt, dist });
      redrawCanvas();
    } else if (activeTool === 'move') {
      syncCrosshair(pt);
    } else {
      redrawCanvas();
    }
  }, [activeTool, getRawCoords, syncCrosshair, volumeInfo, redrawCanvas]);

  const handleTouchEnd = useCallback(async (e) => {
    const pt = getRawCoords(e);

    if (isDrawing.current && strokePoints.current.length > 0) {
      isDrawing.current = false;
      try {
        const radiusToUse = activeTool === 'eraser' ? eraserSize : brushSize;
        await drawSegmentation(view, sliceIndex, {
          points: strokePoints.current,
          label: 1,
          erase: activeTool === 'eraser',
          radius: radiusToUse,
          smart: activeTool === 'smartbrush',
        });
        setSegmentationActive(true);
        refreshMask();
      } catch (err) {}
      strokePoints.current = [];
    }

    if (caliperStart.current && pt) {
      const p1 = caliperStart.current;
      if (p1[0] !== pt[0] || p1[1] !== pt[1]) {
        try {
          const res = await performMeasurement(view, sliceIndex, p1, pt);
          addMeasurement(res);
        } catch (err) {}
      }
      caliperStart.current = null;
      setActiveCaliper(null);
    }

    setCursorPos(null);
    redrawCanvas();
  }, [view, sliceIndex, activeTool, brushSize, eraserSize, getRawCoords, setSegmentationActive, refreshMask, addMeasurement, redrawCanvas]);

  // Wheel slice navigation
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 1 : -1;
    setSlice(view, Math.max(0, Math.min(maxSlice, sliceIndex + delta)));
  }, [view, sliceIndex, maxSlice, setSlice]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  // Register touch listeners manually with { passive: false } so preventDefault works
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Find the viewport div (the flex-1 child with the canvas)
    const viewport = el.querySelector('.cursor-crosshair');
    if (!viewport) return;

    const on = (evt, handler) => viewport.addEventListener(evt, handler, { passive: false });
    const off = (evt, handler) => viewport.removeEventListener(evt, handler);

    on('touchstart', handleTouchStart);
    on('touchmove', handleTouchMove);
    on('touchend', handleTouchEnd);
    on('touchcancel', handleTouchEnd);

    return () => {
      off('touchstart', handleTouchStart);
      off('touchmove', handleTouchMove);
      off('touchend', handleTouchEnd);
      off('touchcancel', handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchMove, handleTouchEnd]);

  const compass = COMPASS_LABELS[view];

  return (
    <div
      ref={containerRef}
      className={`relative bg-black flex flex-col overflow-hidden border border-med-border rounded min-h-[280px] md:min-h-0 ${
        maximizedView === view ? 'flex-1' : ''
      }`}
      onContextMenu={(e) => e.preventDefault()}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 bg-med-panel/90 border-b border-med-border z-10 select-none">
        <span className="text-xs font-bold uppercase tracking-wider text-med-text flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: accentColor }} />
          {label}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-med-text-dim font-mono">
            {sliceIndex + 1} / {maxSlice + 1}
          </span>
          <button
            onClick={onToggleMaximize}
            title={maximizedView === view ? 'Restore 2x2' : 'Maximize'}
            className="text-[11px] text-med-text-dim hover:text-med-accent transition-colors px-1"
          >
            {maximizedView === view ? '❐' : '⤢'}
          </button>
        </div>
      </div>

      {/* Viewport Canvas */}
      <div
        className="flex-1 relative flex items-center justify-center overflow-hidden cursor-crosshair select-none touch-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      >
        <canvas
          ref={canvasRef}
          style={{
            transform: `scale(${settings.zoom}) rotate(${settings.rotate}deg)`,
            filter: `brightness(${1 + settings.brightness / 100}) contrast(${settings.contrast / 100})`,
            transition: 'filter 0.05s ease-out',
          }}
          className={`${maximizedView === view ? 'w-full h-full' : 'max-w-full max-h-full object-contain'} slice-canvas`}
        />

        {loading && !sliceImg && (
          <div className="absolute text-med-text-dim text-xs flex items-center gap-2">
            <div className="w-3 h-3 border-2 border-med-accent border-t-transparent rounded-full animate-spin" />
            Loading slice...
          </div>
        )}

        {/* Anatomical Compass Badges */}
        <div className="absolute inset-0 pointer-events-none p-1.5 flex flex-col justify-between select-none">
          <div className="flex justify-between text-[10px] font-mono text-amber-400/80 drop-shadow">
            <span>{label.toUpperCase()}</span>
            <span>Zoom: {(settings.zoom * 100).toFixed(0)}%</span>
          </div>
          <div className="relative w-full h-full">
            <span className="absolute top-0 left-1/2 -translate-x-1/2 text-xs font-bold text-amber-400/90 drop-shadow">
              {compass.top}
            </span>
            <span className="absolute bottom-0 left-1/2 -translate-x-1/2 text-xs font-bold text-amber-400/90 drop-shadow">
              {compass.bottom}
            </span>
            <span className="absolute top-1/2 left-0 -translate-y-1/2 text-xs font-bold text-amber-400/90 drop-shadow">
              {compass.left}
            </span>
            <span className="absolute top-1/2 right-0 -translate-y-1/2 text-xs font-bold text-amber-400/90 drop-shadow">
              {compass.right}
            </span>
          </div>
        </div>
      </div>

      {/* Slice slider */}
      <div className="px-2 py-1 bg-med-panel/90 border-t border-med-border flex items-center">
        <input
          type="range"
          min="0"
          max={maxSlice}
          value={sliceIndex}
          onChange={(e) => setSlice(view, Number(e.target.value))}
          className="w-full h-1 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
        />
      </div>
    </div>
  );
}

export default function MPRViewer() {
  const { is3DMode, setIs3DMode, segmentationActive } = useStore();
  const [maximizedView, setMaximizedView] = useState(null);

  const handleToggleMaximize = (view) => {
    setMaximizedView((prev) => (prev === view ? null : view));
  };

  return (
    <div className={`w-full h-full p-1.5 bg-med-dark gap-1.5 min-h-0 ${
      maximizedView
        ? 'flex'
        : 'flex flex-col overflow-y-auto md:overflow-hidden md:grid md:grid-cols-2 md:grid-rows-2'
    }`}>
      {(!maximizedView || maximizedView === 'axial') && (
        <SlicePanel
          view="axial"
          label="Axial"
          accentColor="#ef4444"
          maximizedView={maximizedView}
          onToggleMaximize={() => handleToggleMaximize('axial')}
        />
      )}
      {(!maximizedView || maximizedView === 'sagittal') && (
        <SlicePanel
          view="sagittal"
          label="Sagittal"
          accentColor="#22c55e"
          maximizedView={maximizedView}
          onToggleMaximize={() => handleToggleMaximize('sagittal')}
        />
      )}
      {(!maximizedView || maximizedView === 'coronal') && (
        <SlicePanel
          view="coronal"
          label="Coronal"
          accentColor="#3b82f6"
          maximizedView={maximizedView}
          onToggleMaximize={() => handleToggleMaximize('coronal')}
        />
      )}

      {/* 4th Quadrant: 3D Volume Engine */}
      {(!maximizedView || maximizedView === '3d') && (
      <div className={`relative bg-black border border-med-border rounded flex flex-col overflow-hidden min-h-[280px] md:min-h-0 ${
        maximizedView === '3d' ? 'flex-1' : ''
      }`}>
        <div className="flex items-center justify-between px-2 py-1 bg-med-panel/90 border-b border-med-border z-10 select-none">
          <span className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            3D Volume Engine
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setIs3DMode(!is3DMode)}
              className={`text-xs px-2 py-0.5 rounded font-medium transition-colors ${
                is3DMode
                  ? 'bg-med-accent text-white'
                  : 'bg-med-border/60 text-med-text-dim hover:text-white'
              }`}
            >
              {is3DMode ? '3D Active' : 'Enable 3D'}
            </button>
            <button
              onClick={() => setMaximizedView(maximizedView === '3d' ? null : '3d')}
              title={maximizedView === '3d' ? 'Restore 2x2' : 'Maximize'}
              className="text-[11px] text-med-text-dim hover:text-med-accent transition-colors px-1"
            >
              {maximizedView === '3d' ? '❐' : '⤢'}
            </button>
          </div>
        </div>

        <div className="flex-1 w-full h-full relative">
          {is3DMode ? (
            <VolumeRenderer />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center text-center p-4">
              <div className="w-12 h-12 rounded-full bg-med-accent/10 flex items-center justify-center text-2xl text-med-accent mb-2">
                🧊
              </div>
              <h4 className="text-xs font-semibold text-med-text">3D Engine Standby</h4>
              <p className="text-[11px] text-med-text-dim max-w-xs mt-1">
                Click "Enable 3D" to run real-time raymarched anatomical rendering.
              </p>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}