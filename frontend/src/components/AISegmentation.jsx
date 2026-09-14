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
  Skeleton: ['skull', 'clavicula', 'scapula', 'humerus', 'vertebrae_C1-7', 'sternum', 'rib_1-12', 'vertebrae_T1-12', 'vertebrae_L1-5', 'costal_cartilages', 'ulna', 'radius', 'intervertebral_discs', 'hip', 'sacrum', 'carpal', 'metacarpal', 'phalanges_hand', 'femur', 'patella', 'fibula', 'tibia', 'tarsal', 'metatarsal', 'phalanges_foot'],
  Gastrointestinal: ['esophagus', 'stomach', 'duodenum', 'small_bowel', 'colon', 'urinary_bladder'],
  Cardiovascular: ['common_carotid_artery', 'subclavian_artery', 'brachiocephalic_trunk', 'superior_vena_cava', 'aorta', 'right_atrium', 'right_ventricle', 'portal_vein', 'iliac_artery', 'iliac_vein', 'brachiocephalic_vein_left', 'pulmonary_artery', 'atrial_appendage', 'left_ventricle', 'myocardium', 'left_atrium', 'splenic_vein', 'inferior_vena_cava'],
  'Other organs': ['brain', 'spinal_cord', 'thyroid_gland', 'trachea', 'lung_upper_lobe', 'lung_middle_lobe', 'lung_lower_lobe', 'adrenal_gland', 'spleen', 'liver', 'gallbladder', 'kidney', 'pancreas', 'prostate'],
  Muscles: ['supraspinatus_infraspinatus', 'subscapularis', 'deltoid', 'pectoralis_minor', 'coracobrachial', 'teres_major', 'serratus_anterior', 'autochthon', 'triceps_brachii', 'iliopsoas', 'gluteus_minimus', 'gluteus_medius', 'gluteus_maximus', 'thigh_medial_compartment', 'sartorius', 'quadriceps_femoris', 'thigh_posterior_compartment', 'trapezius'],
};

export default function AISegmentation() {
  const { setSegmentationActive, setLandmarkPositions, setLoading, setError, selectedOrgans, toggleOrgan } = useStore();
  const [expandedSector, setExpandedSector] = useState(null);
  const [isRunning, setIsRunning] = useState(false);

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
    </div>
  );
}
