import React from 'react';
import useStore from '../store/useStore';

const CLINICAL_WL_PRESETS = [
  { name: 'Brain', wc: 40, ww: 80, badge: 'CT' },
  { name: 'Subdural', wc: 75, ww: 210, badge: 'Hemorrhage' },
  { name: 'Soft Tissue', wc: 50, ww: 350, badge: 'General' },
  { name: 'Bone', wc: 500, ww: 2000, badge: 'Ortho' },
  { name: 'Lung', wc: -600, ww: 1500, badge: 'Chest' },
  { name: 'Mediastinum', wc: 40, ww: 400, badge: 'Thorax' },
  { name: 'Liver / Abdomen', wc: 30, ww: 150, badge: 'Abdo' },
];

const ORGAN_LIST = [
  { id: 'all', label: 'All Anatomical Structures' },
  { id: 'brain', label: 'Brain (Cerebrum / Cerebellum)' },
  { id: 'liver', label: 'Liver' },
  { id: 'kidney', label: 'Kidneys' },
  { id: 'spleen', label: 'Spleen' },
  { id: 'skeleton', label: 'Skeleton / Spine' },
  { id: 'vessels', label: 'Aorta / Major Vessels' },
];

export default function ControlsPanel() {
  const {
    windowCenter,
    setWindowCenter,
    windowWidth,
    setWindowWidth,
    showCrosshair,
    setShowCrosshair,
    brushSize,
    setBrushSize,
    brushColor,
    setBrushColor,
    isolatedOrgan,
    setIsolatedOrgan,
    measurements,
    clearMeasurements,
  } = useStore();

  return (
    <div className="p-3 space-y-4 text-xs select-none">
      {/* 1. Organ Isolation Selection */}
      <div className="sidebar-section">
        <h3>Organ Isolation (2D & 3D)</h3>
        <p className="text-med-text-dim text-[11px] mb-2">
          Select an organ to isolate it and hide surrounding tissue:
        </p>
        <select
          value={isolatedOrgan}
          onChange={(e) => setIsolatedOrgan(e.target.value)}
          className="w-full bg-med-dark border border-med-border rounded px-2 py-1.5 text-med-text text-xs focus:outline-none focus:border-med-accent"
        >
          {ORGAN_LIST.map((org) => (
            <option key={org.id} value={org.id}>
              {org.label}
            </option>
          ))}
        </select>
      </div>

      {/* 2. Clinical Diagnostic W/L Presets with Clean Grid Layout */}
      <div className="sidebar-section">
        <h3>Clinical W/L Presets</h3>
        <div className="grid grid-cols-2 gap-2 mt-2">
          {CLINICAL_WL_PRESETS.map((preset) => {
            const isActive =
              Math.abs(windowCenter - preset.wc) < 2 &&
              Math.abs(windowWidth - preset.ww) < 2;
            return (
              <button
                key={preset.name}
                onClick={() => {
                  setWindowCenter(preset.wc);
                  setWindowWidth(preset.ww);
                }}
                className={`flex flex-col justify-between p-2 rounded border text-left transition-all ${
                  isActive
                    ? 'bg-med-accent/20 border-med-accent text-med-accent shadow-sm'
                    : 'border-med-border text-med-text-dim hover:border-med-accent/60 hover:text-med-text'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="font-bold text-[11px] truncate">{preset.name}</span>
                  <span className="text-[8px] px-1 py-0.5 bg-med-border/60 rounded text-med-text-dim uppercase font-mono">
                    {preset.badge}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-gray-400 mt-1">
                  W:{preset.ww} L:{preset.wc}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Manual Sliders */}
      <div className="sidebar-section">
        <h3>Manual Intensity Windowing</h3>
        <div className="space-y-3 mt-2">
          <div>
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-med-text-dim">Level (Center)</span>
              <span className="font-mono text-cyan-400 font-semibold">{windowCenter} HU</span>
            </div>
            <input
              type="range"
              min="-1000"
              max="1500"
              step="1"
              value={windowCenter}
              onChange={(e) => setWindowCenter(Number(e.target.value))}
              className="w-full h-1.5 bg-med-border rounded appearance-none accent-med-accent cursor-pointer"
            />
          </div>
          <div>
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-med-text-dim">Width</span>
              <span className="font-mono text-cyan-400 font-semibold">{windowWidth} HU</span>
            </div>
            <input
              type="range"
              min="1"
              max="4000"
              step="1"
              value={windowWidth}
              onChange={(e) => setWindowWidth(Number(e.target.value))}
              className="w-full h-1.5 bg-med-border rounded appearance-none accent-med-accent cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* 4. Brush & Mask Options */}
      <div className="sidebar-section">
        <h3>Brush & Contours</h3>
        <div className="space-y-2.5 mt-2">
          <div className="flex items-center justify-between">
            <span className="text-med-text-dim">Brush Color</span>
            <input
              type="color"
              value={brushColor}
              onChange={(e) => setBrushColor(e.target.value)}
              className="w-6 h-6 rounded cursor-pointer border-0 bg-transparent p-0"
            />
          </div>
          <div>
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-med-text-dim">Brush Diameter</span>
              <span className="font-mono text-med-text">{brushSize} px</span>
            </div>
            <input
              type="range"
              min="1"
              max="30"
              step="1"
              value={brushSize}
              onChange={(e) => setBrushSize(Number(e.target.value))}
              className="w-full h-1.5 bg-med-border rounded appearance-none accent-med-accent cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* 5. RECIST Caliper History */}
      <div className="sidebar-section">
        <div className="flex items-center justify-between">
          <h3>RECIST Caliper Measurements ({measurements.length})</h3>
          {measurements.length > 0 && (
            <button
              onClick={clearMeasurements}
              className="text-[10px] text-red-400 hover:text-red-300"
            >
              Clear
            </button>
          )}
        </div>
        <div className="mt-2 space-y-1.5 max-h-32 overflow-y-auto">
          {measurements.length === 0 ? (
            <p className="text-[11px] text-med-text-dim italic">
              Select the Caliper tool (📏) and drag on any slice to measure distance.
            </p>
          ) : (
            measurements.map((m, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-1.5 rounded bg-med-dark border border-med-border text-[11px]"
              >
                <span className="text-med-text font-medium uppercase">
                  #{idx + 1} {m.view} [sl.{m.slice_index}]
                </span>
                <span className="font-mono text-cyan-400 font-bold">{m.distance_mm} mm</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 6. Display Settings */}
      <div className="sidebar-section">
        <h3>Overlays</h3>
        <label className="flex items-center gap-2 text-xs text-med-text-dim cursor-pointer mt-1 hover:text-med-text">
          <input
            type="checkbox"
            checked={showCrosshair}
            onChange={(e) => setShowCrosshair(e.target.checked)}
            className="accent-med-accent rounded"
          />
          Show 3D Orthogonal Crosshairs
        </label>
      </div>
    </div>
  );
}
