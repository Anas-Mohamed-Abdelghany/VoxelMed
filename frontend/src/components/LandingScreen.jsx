import React, { useRef } from 'react';
import useStore from '../store/useStore';
import { uploadFile, getVolumeInfo } from '../api/client';

export default function LandingScreen() {
  const fileRef = useRef();
  const { setVolumeLoaded, setVolumeInfo, setLoading, setError } = useStore();

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
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load file');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-4 md:p-8">
      <div className="flex flex-col items-center gap-4 md:gap-6 p-6 md:p-12 rounded-2xl bg-med-panel border border-med-border shadow-2xl max-w-sm md:max-w-md w-full">
        <div className="w-14 h-14 md:w-20 md:h-20 rounded-full bg-med-accent/10 flex items-center justify-center">
          <svg className="w-7 h-7 md:w-10 md:h-10 text-med-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 3.75a6 6 0 00-6 6c0 3.09 2.05 5.65 4.84 6.49A3.75 3.75 0 009 18.75h0a3.75 3.75 0 003.16-3.26A6 6 0 009 3.75z" />
          </svg>
        </div>
        <div className="text-center">
          <h1 className="text-xl md:text-2xl font-bold mb-1">VoxelMed</h1>
          <p className="text-med-text-dim text-xs md:text-sm">3D Medical Image Viewer</p>
        </div>
        <button
          onClick={() => fileRef.current?.click()}
          className="w-full md:w-auto px-6 py-3 bg-med-accent hover:bg-med-accent-hover rounded-lg font-medium transition-colors"
        >
          Open NIfTI / DICOM File
        </button>
        <input ref={fileRef} type="file" accept=".nii,.nii.gz,.dcm" className="hidden" onChange={handleUpload} />
        <p className="text-med-text-dim text-xs">Supports .nii, .nii.gz, and DICOM series</p>
      </div>
    </div>
  );
}
