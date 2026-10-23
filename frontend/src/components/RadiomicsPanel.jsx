import React, { useState } from 'react';
import useStore from '../store/useStore';
import { runRadiomicsAnalysis, calculateOrganVolumes } from '../api/client';

export default function RadiomicsPanel() {
  const { 
    radiomicsData, 
    setRadiomicsData, 
    isRadiomicsLoading, 
    setIsRadiomicsLoading,
    radiomicsError,
    setRadiomicsError,
    organVolumes,
    setOrganVolumes,
    isVolumesLoading,
    setIsVolumesLoading,
    volumesError,
    setVolumesError 
  } = useStore();

  const [height, setHeight] = useState(1.75);

  // Feature 1: AI pathology classifier (model weights on radiomic features)
  const handleRunAnalysis = async () => {
    setIsRadiomicsLoading(true);
    setRadiomicsError(null);
    try {
      const result = await runRadiomicsAnalysis(height);
      setRadiomicsData(result);
    } catch (err) {
      setRadiomicsError(err.message);
    } finally {
      setIsRadiomicsLoading(false);
    }
  };

  // Feature 2: organ volume measurement (standalone, no model involved)
  const handleCalculateVolumes = async () => {
    setIsVolumesLoading(true);
    setVolumesError(null);
    try {
      const result = await calculateOrganVolumes();
      setOrganVolumes(result);
    } catch (err) {
      setVolumesError(err.message);
    } finally {
      setIsVolumesLoading(false);
    }
  };

  const renderDiagnosisCards = (diagnoses) =>
    Object.entries(diagnoses).map(([key, d]) => (
      <div
        key={key}
        className={`p-2.5 rounded border text-xs flex flex-col gap-1 transition-all ${
          d.prediction
            ? 'bg-amber-950/20 border-amber-500/50 text-amber-200'
            : 'bg-[#181824] border-med-border/80 text-med-text'
        }`}
      >
        <div className="flex justify-between items-center font-bold">
          <span>{d.label || key}</span>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-mono ${
              d.prediction 
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40' 
                : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
            }`}
          >
            {d.prediction ? `High Risk (${(d.risk_score * 100).toFixed(0)}%)` : 'Normal'}
          </span>
        </div>
        <span className="text-[10.5px] text-med-text-dim">{d.evidence}</span>
      </div>
    ));

  // Biomarker rows are rendered entirely from backend metadata
  // (label / value / unit / reference range) - nothing hardcoded here.
  const biomarkerRows = radiomicsData?.biomarker_rows || [];

  return (
    <div className="flex flex-col h-full p-3 overflow-y-auto text-med-text space-y-4">
      {/* Header */}
      <div>
        <h3 className="text-sm font-bold text-med-accent">AI Biomarker Risk Engine</h3>
        <p className="text-[11px] text-med-text-dim mt-0.5">
          Radiomic Phenotypes & Quantitative Tissue Pathology
        </p>
      </div>

      {/* Patient Input Controls */}
      <div className="p-2.5 bg-[#0e0e16] border border-med-border/80 rounded space-y-2">
        <label className="block text-[11px] text-med-text-dim">
          Patient Height (meters) for L3 SMI:
        </label>
        <input
          type="number"
          step="0.01"
          value={height}
          onChange={(e) => setHeight(parseFloat(e.target.value) || 1.75)}
          className="w-20 px-2 py-1 text-xs bg-[#181824] border border-med-border rounded text-med-text font-mono focus:outline-none focus:border-med-accent"
        />
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleRunAnalysis}
            disabled={isRadiomicsLoading || isVolumesLoading}
            className="flex-1 min-w-[140px] px-3 py-1.5 text-xs font-semibold rounded bg-med-accent hover:bg-med-accent/80 text-black disabled:opacity-50 transition-colors shadow-xs"
          >
            {isRadiomicsLoading ? 'Analyzing Voxels...' : 'Run Pathology Classifier'}
          </button>
          <button
            onClick={handleCalculateVolumes}
            disabled={isVolumesLoading || isRadiomicsLoading}
            title="Measure the volumes of the segmented organs - a standalone measurement, no AI model involved"
            className="flex-1 min-w-[140px] px-3 py-1.5 text-xs font-semibold rounded border border-med-accent text-med-accent hover:bg-med-accent/10 disabled:opacity-50 transition-colors shadow-xs"
          >
            {isVolumesLoading ? 'Measuring Volumes...' : 'Calculate Organ Volumes'}
          </button>
        </div>
      </div>

      {/* Error Messages */}
      {radiomicsError && (
        <div className="p-2.5 text-xs text-rose-300 bg-rose-950/40 border border-rose-800 rounded">
          {radiomicsError}
        </div>
      )}
      {volumesError && (
        <div className="p-2.5 text-xs text-rose-300 bg-rose-950/40 border border-rose-800 rounded">
          {volumesError}
        </div>
      )}

      {/* Diagnostic Predictions */}
      {radiomicsData && (
        <div className="space-y-4">
          <div>
            <h4 className="text-[11px] font-bold text-med-text uppercase tracking-wider mb-2">
              Predicted Pathology Risks
            </h4>
            <div className="grid grid-cols-1 gap-2">
              {renderDiagnosisCards(radiomicsData.diagnoses)}
            </div>
          </div>

          {/* Biomarkers Table (rows supplied by the backend) */}
          <div>
            <h4 className="text-[11px] font-bold text-med-text uppercase tracking-wider mb-2">
              Physical Biomarkers
            </h4>
            <div className="border border-med-border/80 rounded bg-[#0e0e16] p-2">
              <table className="w-full text-[11px] text-left border-collapse">
                <thead>
                  <tr className="border-b border-med-border/80 text-med-text-dim text-[10px]">
                    <th className="py-1">Biomarker</th>
                    <th className="py-1 text-right">Value</th>
                    <th className="py-1 text-right">Ref. Range</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-med-border/40 text-med-text">
                  {biomarkerRows.map((row) => (
                    <tr key={row.key}>
                      <td className="py-1.5">{row.label}</td>
                      <td className="py-1.5 text-right font-mono text-cyan-400">
                        {row.value}{row.unit ? ` ${row.unit}` : ''}
                      </td>
                      <td className="py-1.5 text-right text-med-text-dim">{row.ref}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Organ volume measurement results (standalone feature) */}
      {organVolumes && (
        <div>
          <h4 className="text-[11px] font-bold text-med-text uppercase tracking-wider mb-2">
            Segmented Organ Volumes
          </h4>
          <div className="border border-med-border/80 rounded bg-[#0e0e16] p-2 max-h-64 overflow-y-auto">
            <table className="w-full text-[11px] text-left border-collapse">
              <thead>
                <tr className="border-b border-med-border/80 text-med-text-dim text-[10px]">
                  <th className="py-1">Organ</th>
                  <th className="py-1 text-right">Volume (cm³)</th>
                  <th className="py-1 text-right">% of Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-med-border/40 text-med-text">
                {organVolumes.organ_volumes.map((v) => (
                  <tr key={v.key}>
                    <td className="py-1">{v.organ}</td>
                    <td className="py-1 text-right font-mono text-cyan-400">{v.vol_cm3}</td>
                    <td className="py-1 text-right font-mono text-med-text-dim">{v.pct_of_total}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2 pt-2 border-t border-med-border/60 text-[10.5px] text-med-text-dim flex justify-between">
              <span>Total segmented volume</span>
              <span className="font-mono text-cyan-400">{organVolumes.total_cm3} cm³</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
