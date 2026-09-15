import React, { useRef, useState } from 'react';
import useStore from '../store/useStore';
import { uploadFile, getVolumeInfo, toggleMotionRestoration } from '../api/client';

export default function Toolbar() {
  const {
    setVolumeLoaded,
    setVolumeInfo,
    setLoading,
    setError,
    volumeInfo,
    toggleSidebar,
    sidebarOpen,
  } = useStore();

  const fileRef = useRef();
  const [isRestored, setIsRestored] = useState(false);
  const [processing, setProcessing] = useState(false);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      await uploadFile(file);
      const info = await getVolumeInfo();
      setVolumeInfo(info);
      setVolumeLoaded(true);
      setIsRestored(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to upload volume');
    } finally {
      setLoading(false);
      e.target.value = '';
    }
  };

  const handleToggleMotion = async () => {
    if (!volumeInfo || processing) return;
    setProcessing(true);
    setLoading(true);
    try {
      const res = await toggleMotionRestoration();
      setIsRestored(res.is_restored);
      const info = await getVolumeInfo();
      setVolumeInfo(info);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to toggle motion filter');
    } finally {
      setProcessing(false);
      setLoading(false);
    }
  };

  return (
    <div className="h-11 flex items-center justify-between px-2 md:px-3 bg-med-panel border-b border-med-border shrink-0 select-none z-30">
      {/* Left controls */}
      <div className="flex items-center gap-2 md:gap-3">
        {/* Hamburger (mobile only) */}
        <button
          onClick={toggleSidebar}
          className="md:hidden flex items-center justify-center w-8 h-8 rounded hover:bg-med-accent/20 text-med-text-dim hover:text-med-accent transition-colors"
          title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {sidebarOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>

        <div className="flex items-center gap-1.5 font-bold tracking-wider text-sm text-med-accent">
          <span>❖</span>
          <span className="hidden sm:inline">VOXELMED</span>
        </div>

        <div className="w-px h-5 bg-med-border mx-0.5 md:mx-1 hidden sm:block" />

        <button
          onClick={() => fileRef.current?.click()}
          className="px-2 md:px-3 py-1 bg-med-accent hover:bg-med-accent-hover text-white text-xs font-semibold rounded shadow transition-colors flex items-center gap-1.5"
        >
          <span>📁</span>
          <span className="hidden sm:inline">Open File</span>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".nii,.nii.gz,.dcm"
          className="hidden"
          onChange={handleUpload}
        />

        {/* Toggle Motion Restoration Button */}
        <button
          onClick={handleToggleMotion}
          disabled={!volumeInfo || processing}
          className={`px-2 md:px-2.5 py-1 text-xs border rounded flex items-center gap-1.5 transition-all font-medium disabled:opacity-30 ${
            isRestored
              ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400 shadow-sm'
              : 'border-med-border text-med-text-dim hover:border-med-accent hover:text-med-text'
          }`}
          title="Toggle bilateral filter to suppress motion blur"
        >
          <span>{isRestored ? '✓' : '⚡'}</span>
          <span className="hidden md:inline">{isRestored ? 'Motion Filter: Enabled' : 'Motion Filter: Disabled'}</span>
        </button>
      </div>

      {/* Right metadata */}
      {volumeInfo && (
        <div className="text-med-text-dim text-xs hidden md:flex items-center gap-2 font-mono">
          <span className="bg-med-dark/60 border border-med-border/60 px-2 py-0.5 rounded">
            {volumeInfo.shape?.join(' × ')} voxels
          </span>
          <span className="bg-med-dark/60 border border-med-border/60 px-2 py-0.5 rounded">
            Spacing: {volumeInfo.spacing?.map((s) => s.toFixed(2)).join(' × ')} mm
          </span>
        </div>
      )}
    </div>
  );
}
