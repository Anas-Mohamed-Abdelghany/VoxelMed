import React from 'react';
import useStore from '../store/useStore';

export default function LandmarkNav() {
  const { landmarkPositions, segmentationActive, navigateToLandmark } = useStore();

  const organs = Object.keys(landmarkPositions);

  if (!segmentationActive || organs.length === 0) {
    return (
      <div className="sidebar-section">
        <h3>Landmarks</h3>
        <p className="text-med-text-dim text-xs mt-2">
          Run AI segmentation first to enable landmark navigation.
        </p>
      </div>
    );
  }

  return (
    <div className="sidebar-section">
      <h3>Landmark Navigation</h3>
      <div className="space-y-1 mt-2 max-h-60 overflow-y-auto">
        {organs.map((organ) => {
          const pos = landmarkPositions[organ];
          return (
            <button
              key={organ}
              onClick={() => navigateToLandmark(organ)}
              className="w-full flex items-center justify-between text-xs py-1.5 px-2 rounded border border-med-border hover:border-med-accent/50 hover:bg-med-accent/5 transition-colors text-left"
            >
              <span className="text-med-text">{organ.replace(/_/g, ' ')}</span>
              <span className="text-med-text-dim text-[10px] font-mono">
                {pos ? `${pos[0]},${pos[1]},${pos[2]}` : '?'}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
