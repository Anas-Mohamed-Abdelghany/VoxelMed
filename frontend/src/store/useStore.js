import { create } from 'zustand';

const useStore = create((set, get) => ({
  volumeLoaded: false,
  volumeInfo: null,

  currentSlice: { axial: 0, sagittal: 0, coronal: 0 },
  windowCenter: 40,
  windowWidth: 400,

  // Tool Selection matching your sidebar
  activeTool: 'move', // 'move' | 'brush' | 'eraser' | 'smartbrush' | 'caliper'
  brushSize: 5,
  eraserSize: 5,
  drawingColor: '#ef4444',

  // Per-view Settings (Axial, Sagittal, Coronal)
  viewSettings: {
    axial: { zoom: 1.0, brightness: 0, contrast: 100, rotate: 0 },
    sagittal: { zoom: 1.0, brightness: 0, contrast: 100, rotate: 180 },
    coronal: { zoom: 1.0, brightness: 0, contrast: 100, rotate: 180 },
  },

  segmentationActive: false,
  segmentationLabels: {},
  landmarkPositions: {},
  selectedOrgans: [],
  is3DMode: true,
  showCrosshair: true,
  measurements: [],
  loading: false,
  error: null,

  // 3D Lab Controls
  lab3d: {
    boxCrop: false,
    clipX: { enabled: false, position: 0.5, flipped: false },
    clipY: { enabled: false, position: 0.5, flipped: false },
    clipZ: { enabled: false, position: 0.5, flipped: false },
    selectedOrgan: '',
    organOpacity: 1.0,
    backgroundOpacity: 1.0,
    tissuePreset: 'all',
    tissueThreshold: 0.12,
  },

  setVolumeLoaded: (loaded) => set({ volumeLoaded: loaded }),

  // When volume loads, automatically center the slice index on the body
  setVolumeInfo: (info) => {
    if (info && info.shape) {
      const [depth, height, width] = info.shape;
      set({
        volumeInfo: info,
        currentSlice: {
          axial: Math.floor(depth / 2),
          coronal: Math.floor(height / 2),
          sagittal: Math.floor(width / 2),
        },
      });
    } else {
      set({ volumeInfo: info });
    }
  },

  setSlice: (view, indexOrUpdater) =>
    set((s) => {
      const prev = s.currentSlice[view] || 0;
      const next = typeof indexOrUpdater === 'function' ? indexOrUpdater(prev) : indexOrUpdater;
      return {
        currentSlice: { ...s.currentSlice, [view]: Math.round(next) },
      };
    }),

  setCurrentSliceForAll: (axial, sagittal, coronal) =>
    set({
      currentSlice: {
        axial: Math.round(axial),
        sagittal: Math.round(sagittal),
        coronal: Math.round(coronal),
      },
    }),

  setWindowCenter: (wc) => set({ windowCenter: Math.round(wc) }),
  setWindowWidth: (ww) => set({ windowWidth: Math.max(1, Math.round(ww)) }),

  setActiveTool: (tool) => set({ activeTool: tool }),
  setBrushSize: (size) => set({ brushSize: Number(size) }),
  setEraserSize: (size) => set({ eraserSize: Number(size) }),
  setDrawingColor: (color) => set({ drawingColor: color }),

  updateViewSetting: (view, key, value) =>
    set((s) => ({
      viewSettings: {
        ...s.viewSettings,
        [view]: { ...s.viewSettings[view], [key]: value },
      },
    })),

  zoomView: (view, factor) =>
    set((s) => {
      const current = s.viewSettings[view].zoom;
      const next = Math.max(0.4, Math.min(6.0, current * factor));
      return {
        viewSettings: {
          ...s.viewSettings,
          [view]: { ...s.viewSettings[view], zoom: next },
        },
      };
    }),

  resetView: (view) =>
    set((s) => ({
      viewSettings: {
        ...s.viewSettings,
        [view]: { zoom: 1.0, brightness: 0, contrast: 100, rotate: view === 'axial' ? 0 : 180 },
      },
    })),

  setSegmentationActive: (active) => set({ segmentationActive: active }),
  setLandmarkPositions: (positions) => set({ landmarkPositions: positions }),
  toggleOrgan: (organ) =>
    set((s) => ({
      selectedOrgans: s.selectedOrgans.includes(organ)
        ? s.selectedOrgans.filter((o) => o !== organ)
        : [...s.selectedOrgans, organ],
    })),

  setIs3DMode: (mode) => set({ is3DMode: mode }),
  setShowCrosshair: (show) => set({ showCrosshair: show }),

  // 3D Lab actions
  updateLab3d: (key, value) =>
    set((s) => ({ lab3d: { ...s.lab3d, [key]: value } })),
  updateLab3dClip: (axis, key, value) =>
    set((s) => ({
      lab3d: {
        ...s.lab3d,
        [axis]: { ...s.lab3d[axis], [key]: value },
      },
    })),
  resetLab3d: () =>
    set({
      lab3d: {
        boxCrop: false,
        clipX: { enabled: false, position: 0.5, flipped: false },
        clipY: { enabled: false, position: 0.5, flipped: false },
        clipZ: { enabled: false, position: 0.5, flipped: false },
        selectedOrgan: '',
        organOpacity: 1.0,
        backgroundOpacity: 1.0,
        tissuePreset: 'all',
        tissueThreshold: 0.12,
      },
    }),

  addMeasurement: (m) => set((s) => ({ measurements: [...s.measurements, m] })),
  clearMeasurements: () => set({ measurements: [] }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));

export default useStore;