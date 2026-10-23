import React, { useState } from 'react';
import useStore from '../store/useStore';
import { runSegmentation, getVolumeInfo } from '../api/client';

const SECTORS = [
  'Skeleton',
  'Gastrointestinal',
  'Cardiovascular',
  'Other organs',
  'Muscles',
];

const SECTOR_ORGANS = {
  Skeleton: ["skull","sacrum","vertebrae_S1","vertebrae_L5","vertebrae_L4","vertebrae_L3","vertebrae_L2","vertebrae_L1","vertebrae_T12","vertebrae_T11","vertebrae_T10","vertebrae_T9","vertebrae_T8","vertebrae_T7","vertebrae_T6","vertebrae_T5","vertebrae_T4","vertebrae_T3","vertebrae_T2","vertebrae_T1","vertebrae_C7","vertebrae_C6","vertebrae_C5","vertebrae_C4","vertebrae_C3","vertebrae_C2","vertebrae_C1","rib_left_1","rib_left_2","rib_left_3","rib_left_4","rib_left_5","rib_left_6","rib_left_7","rib_left_8","rib_left_9","rib_left_10","rib_left_11","rib_left_12","rib_right_1","rib_right_2","rib_right_3","rib_right_4","rib_right_5","rib_right_6","rib_right_7","rib_right_8","rib_right_9","rib_right_10","rib_right_11","rib_right_12","sternum","costal_cartilages","scapula_left","scapula_right","clavicula_left","clavicula_right","humerus_left","humerus_right","femur_left","femur_right","hip_left","hip_right"],
  Gastrointestinal: ["esophagus","stomach","duodenum","small_bowel","colon","urinary_bladder"],
  Cardiovascular: ["heart","aorta","pulmonary_vein","brachiocephalic_trunk","subclavian_artery_left","subclavian_artery_right","common_carotid_artery_left","common_carotid_artery_right","brachiocephalic_vein_left","brachiocephalic_vein_right","atrial_appendage_left","superior_vena_cava","inferior_vena_cava","portal_vein_and_splenic_vein","iliac_artery_left","iliac_artery_right","iliac_vena_left","iliac_vena_right"],
  'Other organs': ["brain","spinal_cord","thyroid_gland","trachea","lung_upper_lobe_left","lung_upper_lobe_right","lung_middle_lobe_right","lung_lower_lobe_left","lung_lower_lobe_right","adrenal_gland_left","adrenal_gland_right","spleen","liver","gallbladder","kidney_left","kidney_right","kidney_cyst_left","kidney_cyst_right","pancreas","prostate"],
  Muscles: ["gluteus_maximus_left","gluteus_maximus_right","gluteus_medius_left","gluteus_medius_right","gluteus_minimus_left","gluteus_minimus_right","autochthon_left","autochthon_right","iliopsoas_left","iliopsoas_right"],
};

export default function AISegmentation() {
  const { setSegmentationActive, setLandmarkPositions, setLoading, setError, selectedOrgans, toggleOrgan, selectAllOrgans, deselectAllOrgans } = useStore();
  const [expandedSector, setExpandedSector] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [showMap, setShowMap] = useState(false);

  const handleRun = async () => {
    setIsRunning(true);
    setLoading(true);
    setError(null);
    try {
      const result = await runSegmentation(selectedOrgans);
      setLandmarkPositions(result.landmarks || {});
      setSegmentationActive(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Segmentation failed');
    } finally {
      setIsRunning(false);
      setLoading(false);
    }
  };

  return (
    <div className="sidebar-section">
      <h3>AI Segmentation</h3>
      <button
        onClick={() => setShowMap(true)}
        className="w-full mt-2 py-1 text-[11px] font-medium rounded border border-med-border hover:border-med-accent/50 text-med-text-dim hover:text-med-text transition-colors"
      >
        Map
      </button>
      <div className="flex gap-2 mt-2">
        <button
          onClick={selectAllOrgans}
          className="flex-1 py-1 text-[11px] font-medium rounded border border-med-border hover:border-med-accent/50 text-med-text-dim hover:text-med-text transition-colors"
        >
          Select All
        </button>
        <button
          onClick={deselectAllOrgans}
          className="flex-1 py-1 text-[11px] font-medium rounded border border-med-border hover:border-med-accent/50 text-med-text-dim hover:text-med-text transition-colors"
        >
          Deselect All
        </button>
      </div>
      <div className="space-y-2 mt-2">
        {Object.entries(SECTOR_ORGANS).map(([sector, organs]) => (
          <div key={sector}>
            <button
              onClick={() => setExpandedSector(expandedSector === sector ? null : sector)}
              className="w-full flex items-center justify-between text-xs py-1.5 px-2 rounded border border-med-border hover:border-med-accent/50 transition-colors"
            >
              <span className="text-med-text">{sector}</span>
              <span className="text-med-text-dim text-[10px]">{organs.length}</span>
            </button>
            {expandedSector === sector && (
              <div className="mt-1 space-y-0.5 pl-2 max-h-40 overflow-y-auto">
                {organs.map((organ) => (
                  <label key={organ} className="flex items-center gap-1.5 text-[11px] text-med-text-dim cursor-pointer hover:text-med-text py-0.5">
                    <input
                      type="checkbox"
                      checked={selectedOrgans.includes(organ)}
                      onChange={() => toggleOrgan(organ)}
                      className="accent-med-accent w-3 h-3"
                    />
                    {organ.replace(/_/g, ' ')}
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <button
        onClick={handleRun}
        disabled={isRunning || selectedOrgans.length === 0}
        className="w-full mt-3 py-2 text-xs font-medium rounded-lg bg-med-accent hover:bg-med-accent-hover disabled:bg-med-border disabled:text-med-text-dim transition-colors"
      >
        {isRunning ? 'Running...' : `Run Segmentation (${selectedOrgans.length} organs)`}
      </button>
      {showMap && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setShowMap(false)}
        >
          <div
            className="relative bg-med-bg rounded-lg border border-med-border overflow-hidden max-w-[90vw] max-h-[90vw]"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setShowMap(false)}
              className="absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center rounded bg-black/50 text-white text-sm hover:bg-black/70"
            >
              ×
            </button>
            <img src="/map.png" alt="Organ Map" className="block max-w-[85vw] max-h-[85vh] object-contain" />
          </div>
        </div>
      )}
    </div>
  );
}
