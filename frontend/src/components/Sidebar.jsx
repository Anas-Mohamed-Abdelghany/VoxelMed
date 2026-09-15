import React, { useState, useRef } from 'react';
import useStore from '../store/useStore';
import AISegmentation from './AISegmentation';
import LandmarkNav from './LandmarkNav';

const TISSUE_PRESETS = [
  { id: 'all', label: 'All tissue' },
  { id: 'skin', label: 'Skin / Fat' },
  { id: 'soft', label: 'Soft tissue' },
  { id: 'bone', label: 'Bone' },
];

const TISSUE_THRESHOLDS = { all: 0.12, skin: 0.05, soft: 0.22, bone: 0.70 };

export default function Sidebar({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('Main');
  const [openAccordion, setOpenAccordion] = useState({
    axial: true,
    sagittal: false,
    coronal: false,
  });

  const colorInputRef = useRef(null);

  const {
    activeTool,
    setActiveTool,
    brushSize,
    setBrushSize,
    eraserSize,
    setEraserSize,
    drawingColor,
    setDrawingColor,
    currentSlice,
    setSlice,
    viewSettings,
    updateViewSetting,
    zoomView,
    resetView,
    volumeInfo,
    segmentationActive,
    selectedOrgans,
    landmarkPositions,
    // 3D Lab
    lab3d,
    updateLab3d,
    updateLab3dClip,
    resetLab3d,
  } = useStore();

  const toggleAccordion = (view) => {
    setOpenAccordion((prev) => ({ ...prev, [view]: !prev[view] }));
  };

  const getMaxSlice = (view) => {
    if (!volumeInfo?.shape) return 0;
    return (
      (view === 'axial'
        ? volumeInfo.shape[0]
        : view === 'sagittal'
        ? volumeInfo.shape[2]
        : volumeInfo.shape[1]) - 1 || 0
    );
  };

  return (
    <aside className={`
      w-[265px] shrink-0 bg-med-panel border-r border-med-border flex flex-col h-full select-none text-med-text font-sans text-xs
      fixed md:relative inset-y-0 left-0 z-40
      transition-transform duration-200 ease-in-out
      ${isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
    `}>
      {/* Mobile close button */}
      <div className="md:hidden flex items-center justify-between px-3 py-2 bg-med-dark/50 border-b border-med-border">
        <span className="text-xs font-bold text-med-text-dim uppercase tracking-wider">Menu</span>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded hover:bg-med-accent/20 text-med-text-dim hover:text-med-accent transition-colors"
          title="Close sidebar"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      {/* 1. Tabs Header: Main | AI Segmentation | 3D Lab */}
      <div className="flex bg-med-dark/50 border-b border-med-border">
        {[
          { id: 'Main', label: 'Main' },
          { id: 'AI Segmentation', label: 'AI Segmentation' },
          { id: '3D Lab', label: '3D Lab' },
        ].map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2.5 text-center font-bold text-[11px] transition-colors ${
                isActive
                  ? 'text-med-accent bg-med-panel border-b-2 border-med-accent'
                  : 'text-med-text-dim hover:text-med-text hover:bg-med-panel/40'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 2. Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {activeTab === 'Main' && (
          <>
            {/* Tool Selection Dropdown */}
            <div className="space-y-1">
              <label className="text-[12px] font-semibold text-med-text-dim">Tool:</label>
              <select
                value={activeTool}
                onChange={(e) => setActiveTool(e.target.value)}
                className="w-full bg-[#181824] border border-med-border rounded px-2 py-1.5 text-med-text text-xs focus:outline-none focus:border-med-accent"
              >
                <option value="move">Move</option>
                <option value="brush">Brush</option>
                <option value="eraser">Eraser</option>
                <option value="smartbrush">Smart Brush</option>
                <option value="caliper">Smart Caliper</option>
              </select>
            </div>

            {/* Select Color Button */}
            <div>
              <input
                ref={colorInputRef}
                type="color"
                value={drawingColor}
                onChange={(e) => setDrawingColor(e.target.value)}
                className="hidden"
              />
              <button
                onClick={() => colorInputRef.current?.click()}
                className="w-full py-1.5 bg-[#181824] hover:bg-[#202030] active:bg-[#282838] border border-med-border rounded text-xs text-med-text flex items-center justify-center gap-2 shadow-xs transition-colors"
              >
                <span
                  className="w-3.5 h-3.5 rounded-full border border-gray-500 shadow-sm"
                  style={{ backgroundColor: drawingColor }}
                />
                <span>Select Color</span>
              </button>
            </div>

            {/* Brush Size Slider */}
            <div className="space-y-1">
              <div className="flex justify-between text-[11px] text-med-text-dim">
                <span>Brush Size:</span>
                <span className="font-mono text-med-accent font-semibold">{brushSize} px</span>
              </div>
              <input
                type="range"
                min="1"
                max="20"
                value={brushSize}
                onChange={(e) => setBrushSize(e.target.value)}
                className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
              />
            </div>

            {/* Eraser Size Slider */}
            <div className="space-y-1">
              <div className="flex justify-between text-[11px] text-med-text-dim">
                <span>Eraser Size:</span>
                <span className="font-mono text-med-accent font-semibold">{eraserSize} px</span>
              </div>
              <input
                type="range"
                min="1"
                max="20"
                value={eraserSize}
                onChange={(e) => setEraserSize(e.target.value)}
                className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
              />
            </div>

            <hr className="border-med-border/80 my-2" />

            {/* Per-View Accordions (Axial, Sagittal, Coronal) */}
            {['axial', 'sagittal', 'coronal'].map((view) => {
              const viewTitle = view.charAt(0).toUpperCase() + view.slice(1);
              const isOpen = openAccordion[view];
              const max = getMaxSlice(view);
              const current = currentSlice[view] || 0;
              const settings = viewSettings[view];

              return (
                <div key={view} className="space-y-1.5">
                  <button
                    onClick={() => toggleAccordion(view)}
                    className="w-full py-1.5 px-2 bg-[#181824] hover:bg-[#202030] border border-med-border rounded text-xs font-semibold text-med-text flex items-center justify-between shadow-xs transition-colors"
                  >
                    <span>{viewTitle} Settings</span>
                    <span className="text-med-text-dim text-[10px]">{isOpen ? '▲' : '▼'}</span>
                  </button>

                  {isOpen && (
                    <div className="p-2.5 bg-[#0e0e16] border border-med-border/80 rounded space-y-2 text-xs">
                      {/* Slice Count & Slider */}
                      <div>
                        <div className="flex items-center justify-between text-[11px] mb-1">
                          <span className="text-med-text-dim">Slice:</span>
                          <span className="font-mono font-bold text-med-text">
                            {volumeInfo ? `${current + 1} / ${max + 1}` : '— / —'}
                          </span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max={max}
                          value={current}
                          onChange={(e) => setSlice(view, Number(e.target.value))}
                          className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
                        />
                      </div>

                      {/* Zoom Buttons */}
                      <div className="grid grid-cols-2 gap-1.5">
                        <button
                          onClick={() => zoomView(view, 1.15)}
                          className="py-1 bg-[#181824] hover:bg-[#222234] border border-med-border rounded text-med-text text-center"
                        >
                          Zoom In
                        </button>
                        <button
                          onClick={() => zoomView(view, 0.85)}
                          className="py-1 bg-[#181824] hover:bg-[#222234] border border-med-border rounded text-med-text text-center"
                        >
                          Zoom Out
                        </button>
                      </div>

                      {/* Brightness Slider */}
                      <div>
                        <div className="flex justify-between text-[11px] text-med-text-dim mb-0.5">
                          <span>Brightness:</span>
                          <span className="font-mono text-cyan-400">{settings.brightness}</span>
                        </div>
                        <input
                          type="range"
                          min="-100"
                          max="100"
                          value={settings.brightness}
                          onChange={(e) =>
                            updateViewSetting(view, 'brightness', Number(e.target.value))
                          }
                          className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
                        />
                      </div>

                      {/* Contrast Slider */}
                      <div>
                        <div className="flex justify-between text-[11px] text-med-text-dim mb-0.5">
                          <span>Contrast:</span>
                          <span className="font-mono text-cyan-400">{settings.contrast}%</span>
                        </div>
                        <input
                          type="range"
                          min="1"
                          max="300"
                          value={settings.contrast}
                          onChange={(e) =>
                            updateViewSetting(view, 'contrast', Number(e.target.value))
                          }
                          className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
                        />
                      </div>

                      {/* Rotate Spinbox */}
                      <div className="flex items-center justify-between">
                        <label className="text-med-text-dim text-[11px]">Rotate (°):</label>
                        <input
                          type="number"
                          min="-180"
                          max="180"
                          value={settings.rotate}
                          onChange={(e) =>
                            updateViewSetting(view, 'rotate', Number(e.target.value))
                          }
                          className="w-16 bg-[#181824] border border-med-border rounded px-1.5 py-0.5 text-center text-med-text font-mono"
                        />
                      </div>

                      {/* Reset View Button */}
                      <button
                        onClick={() => resetView(view)}
                        className="w-full py-1 bg-[#181824] hover:bg-[#222234] border border-med-border rounded text-med-text text-center text-[11px]"
                      >
                        Reset {viewTitle} View
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </>
        )}

        {/* AI Segmentation Tab */}
        {activeTab === 'AI Segmentation' && (
          <div className="space-y-3">
            <AISegmentation />
            <LandmarkNav />
          </div>
        )}

        {/* 3D Lab Tab */}
        {activeTab === '3D Lab' && (
          <div className="space-y-3">
            <div>
              <h3 className="font-bold text-med-accent text-sm">3D Lab</h3>
              <p className="text-med-text-dim text-[11px] mt-1">Cut, crop, and peel away layers to see inside the volume.</p>
            </div>

            {/* 2. Orthogonal Clips */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-bold text-med-text uppercase tracking-wider">Orthogonal Clips</h4>
              <p className="text-med-text-dim text-[10px]">Slide to cut the volume along an axis. "Flip" swaps which half is removed.</p>

              {[
                { axis: 'clipX', label: 'Axis 1 (X)', color: '#ef4444' },
                { axis: 'clipY', label: 'Axis 2 (Y)', color: '#22c55e' },
                { axis: 'clipZ', label: 'Axis 3 (Z)', color: '#3b82f6' },
              ].map(({ axis, label, color }) => (
                <div key={axis} className="p-2 bg-[#0e0e16] border border-med-border/80 rounded space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-1.5 text-[11px] text-med-text cursor-pointer">
                      <input
                        type="checkbox"
                        checked={lab3d[axis].enabled}
                        onChange={(e) => updateLab3dClip(axis, 'enabled', e.target.checked)}
                        className="accent-med-accent w-3 h-3"
                      />
                      <span className="font-semibold" style={{ color }}>{label}</span>
                    </label>
                    <button
                      onClick={() => updateLab3dClip(axis, 'flipped', !lab3d[axis].flipped)}
                      className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
                        lab3d[axis].flipped
                          ? 'bg-med-accent/20 border-med-accent text-med-accent'
                          : 'border-med-border text-med-text-dim hover:text-white hover:border-med-accent/50'
                      }`}
                    >
                      Flip
                    </button>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={Math.round(lab3d[axis].position * 100)}
                    onChange={(e) => updateLab3dClip(axis, 'position', Number(e.target.value) / 100)}
                    disabled={!lab3d[axis].enabled}
                    className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer disabled:opacity-30"
                  />
                </div>
              ))}
            </div>

            <hr className="border-med-border/80" />

            {/* 3. AI Segmentation (Opacity) */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-bold text-med-text uppercase tracking-wider">AI Segmentation</h4>
              <div className="space-y-1.5">
                <label className="text-[11px] text-med-text-dim">Organ:</label>
                {segmentationActive && Object.keys(landmarkPositions).length > 0 ? (
                  <select
                    value={lab3d.selectedOrgan}
                    onChange={(e) => updateLab3d('selectedOrgan', e.target.value)}
                    className="w-full bg-[#181824] border border-med-border rounded px-2 py-1 text-med-text text-xs focus:outline-none focus:border-med-accent"
                  >
                    <option value="">— None —</option>
                    {Object.keys(landmarkPositions).map((organ) => (
                      <option key={organ} value={organ}>{organ.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                ) : (
                  <div className="w-full bg-[#181824] border border-med-border/50 rounded px-2 py-1.5 text-med-text-dim text-[11px] italic">
                    Run AI Segmentation first
                  </div>
                )}
              </div>
              <div>
                <div className="flex justify-between text-[11px] text-med-text-dim mb-0.5">
                  <span>Organ opacity:</span>
                  <span className="font-mono text-cyan-400">{Math.round(lab3d.organOpacity * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={Math.round(lab3d.organOpacity * 100)}
                  onChange={(e) => updateLab3d('organOpacity', Number(e.target.value) / 100)}
                  className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
                />
              </div>
              <div>
                <div className="flex justify-between text-[11px] text-med-text-dim mb-0.5">
                  <span>Rest of volume opacity:</span>
                  <span className="font-mono text-cyan-400">{Math.round(lab3d.backgroundOpacity * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={Math.round(lab3d.backgroundOpacity * 100)}
                  onChange={(e) => updateLab3d('backgroundOpacity', Number(e.target.value) / 100)}
                  className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
                />
              </div>
            </div>

            <hr className="border-med-border/80" />

            {/* 4. Tissue Layers (intensity) */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-bold text-med-text uppercase tracking-wider">Tissue Layers</h4>
              <p className="text-med-text-dim text-[10px]">Peel back low-density tissue (skin/fat) to reveal denser structures (organs/bone).</p>

              <div className="space-y-1">
                {TISSUE_PRESETS.map((preset) => (
                  <label key={preset.id} className="flex items-center gap-2 text-xs text-med-text cursor-pointer py-0.5">
                    <input
                      type="radio"
                      name="tissuePreset"
                      checked={lab3d.tissuePreset === preset.id}
                      onChange={() => {
                        updateLab3d('tissuePreset', preset.id);
                        updateLab3d('tissueThreshold', TISSUE_THRESHOLDS[preset.id]);
                      }}
                      className="accent-med-accent w-3 h-3"
                    />
                    {preset.label}
                  </label>
                ))}
              </div>

              <div>
                <div className="flex justify-between text-[11px] text-med-text-dim mb-0.5">
                  <span>Lower-bound cutoff:</span>
                  <span className="font-mono text-cyan-400">{lab3d.tissueThreshold.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={Math.round(lab3d.tissueThreshold * 100)}
                  onChange={(e) => updateLab3d('tissueThreshold', Number(e.target.value) / 100)}
                  className="w-full h-1.5 bg-[#1e1e2d] accent-med-accent rounded cursor-pointer"
                />
              </div>
            </div>

            <hr className="border-med-border/80" />

            {/* Reset All */}
            <button
              onClick={resetLab3d}
              className="w-full py-2 bg-[#181824] hover:bg-[#222234] border border-med-border rounded text-med-text text-xs font-semibold transition-colors"
            >
              Reset All
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}