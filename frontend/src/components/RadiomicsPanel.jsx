import React, { useState } from 'react';
import useStore from '../store/useStore';
import { runRadiomicsAnalysis } from '../api/client';

export default function RadiomicsPanel() {
  const { 
    radiomicsData, 
    setRadiomicsData, 
    isRadiomicsLoading, 
    setIsRadiomicsLoading,
    radiomicsError,
    setRadiomicsError 
  } = useStore();

  const [height, setHeight] = useState(1.75);

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
        <div className="flex gap-2">
          <input
            type="number"
            step="0.01"
            value={height}
            onChange={(e) => setHeight(parseFloat(e.target.value) || 1.75)}
            className="w-20 px-2 py-1 text-xs bg-[#181824] border border-med-border rounded text-med-text font-mono focus:outline-none focus:border-med-accent"
          />
          <button
            onClick={handleRunAnalysis}
            disabled={isRadiomicsLoading}
            className="flex-1 px-3 py-1.5 text-xs font-semibold rounded bg-med-accent hover:bg-med-accent/80 text-black disabled:opacity-50 transition-colors shadow-xs"
          >
            {isRadiomicsLoading ? 'Analyzing Voxels...' : 'Run Pathology Classifier'}
          </button>
        </div>
      </div>

      {/* Error Message */}
      {radiomicsError && (
        <div className="p-2.5 text-xs text-rose-300 bg-rose-950/40 border border-rose-800 rounded">
          {radiomicsError}
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
              {Object.entries(radiomicsData.diagnoses).map(([key, d]) => (
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
              ))}
            </div>
          </div>

          {/* Biomarkers Table */}
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
                  <tr>
                    <td className="py-1.5">Liver Volume</td>
                    <td className="py-1.5 text-right font-mono text-cyan-400">
                      {radiomicsData.biomarkers.liver_vol_cm3} cm³
                    </td>
                    <td className="py-1.5 text-right text-med-text-dim">&lt; 1600 cm³</td>
                  </tr>
                  <tr>
                    <td className="py-1.5">Liver Mean Density</td>
                    <td className="py-1.5 text-right font-mono text-cyan-400">
                      {radiomicsData.biomarkers.liver_mean_hu} HU
                    </td>
                    <td className="py-1.5 text-right text-med-text-dim">50 - 65 HU</td>
                  </tr>
                  <tr>
                    <td className="py-1.5">Spleen Volume</td>
                    <td className="py-1.5 text-right font-mono text-cyan-400">
                      {radiomicsData.biomarkers.spleen_vol_cm3} cm³
                    </td>
                    <td className="py-1.5 text-right text-med-text-dim">&lt; 250 cm³</td>
                  </tr>
                  <tr>
                    <td className="py-1.5">Liver/Spleen Ratio</td>
                    <td className="py-1.5 text-right font-mono text-cyan-400">
                      {radiomicsData.biomarkers.liver_spleen_ratio}
                    </td>
                    <td className="py-1.5 text-right text-med-text-dim">&gt; 1.0</td>
                  </tr>
                  <tr>
                    <td className="py-1.5">L3 Muscle Area</td>
                    <td className="py-1.5 text-right font-mono text-cyan-400">
                      {radiomicsData.biomarkers.l3_muscle_area_cm2} cm²
                    </td>
                    <td className="py-1.5 text-right text-med-text-dim">&gt; 130 cm²</td>
                  </tr>
                  <tr>
                    <td className="py-1.5">L3 SMI</td>
                    <td className="py-1.5 text-right font-mono text-cyan-400">
                      {radiomicsData.biomarkers.smi} cm²/m²
                    </td>
                    <td className="py-1.5 text-right text-med-text-dim">&gt; 45 cm²/m²</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}