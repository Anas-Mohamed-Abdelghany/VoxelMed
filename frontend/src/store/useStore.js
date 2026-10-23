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
  // Transient "landmark jump" state for grounded AI-report navigation:
  // activeLandmark = { organ, position: [z, y, x], at } | null
  activeLandmark: null,
  // Bumped on every landmark jump so the 3D volume can trigger a spin
  spinToken: 0,
  selectedOrgans: [],
  is3DMode: true,
  showCrosshair: true,
  measurements: [],
  loading: false,
  error: null,
  sidebarOpen: false,

  // AI Report
  aiMessages: [],

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

  // Grounded landmark navigation. Landmarks are stored as [z, y, x]
  // == [axial, coronal, sagittal] slice indices (centroid of each segmented organ).
  navigateToLandmark: async (organ) => {
    const state = get();
    const norm = (s) => String(s).toLowerCase().replace(/[\s_-]+/g, ' ').trim();
    const target = norm(organ);

    // 1) Resolve against locally-known landmarks (from segmentation)
    let key = Object.keys(state.landmarkPositions).find((k) => norm(k) === target);
    let pos = key ? state.landmarkPositions[key] : null;

    // 2) Fallback: ask the backend for this landmark's centroid
    if (!pos) {
      try {
        const res = await fetch(`/api/landmarks/${encodeURIComponent(organ)}/navigate`, { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          pos = data.position;
          key = data.organ || organ;
        }
      } catch {}
    }
    if (!Array.isArray(pos) || pos.length < 3) return false;

    // 3) Center all three MPR crosshairs on the organ centroid
    const [z, y, x] = pos;
    state.setCurrentSliceForAll(z, x, y);

    // 4) Flash the landmark + spin the 3D volume
    const at = Date.now();
    set({ activeLandmark: { organ: key || organ, position: pos, at }, spinToken: state.spinToken + 1 });
    setTimeout(() => {
      if (get().activeLandmark?.at === at) set({ activeLandmark: null });
    }, 2600);
    return true;
  },

  toggleOrgan: (organ) =>
    set((s) => ({
      selectedOrgans: s.selectedOrgans.includes(organ)
        ? s.selectedOrgans.filter((o) => o !== organ)
        : [...s.selectedOrgans, organ],
    })),
  // All 117 TotalSegmentator `total` task classes (exact output-file stems,
  // must stay in sync with backend/segmentation_config.json)
  selectAllOrgans: () =>
    set(() => ({
      selectedOrgans: [
        'skull', 'sacrum', 'vertebrae_S1', 'vertebrae_L5', 'vertebrae_L4', 'vertebrae_L3', 'vertebrae_L2', 'vertebrae_L1', 'vertebrae_T12', 'vertebrae_T11', 'vertebrae_T10', 'vertebrae_T9', 'vertebrae_T8', 'vertebrae_T7', 'vertebrae_T6', 'vertebrae_T5', 'vertebrae_T4', 'vertebrae_T3', 'vertebrae_T2', 'vertebrae_T1', 'vertebrae_C7', 'vertebrae_C6', 'vertebrae_C5', 'vertebrae_C4', 'vertebrae_C3', 'vertebrae_C2', 'vertebrae_C1', 'rib_left_1', 'rib_left_2', 'rib_left_3', 'rib_left_4', 'rib_left_5', 'rib_left_6', 'rib_left_7', 'rib_left_8', 'rib_left_9', 'rib_left_10', 'rib_left_11', 'rib_left_12', 'rib_right_1', 'rib_right_2', 'rib_right_3', 'rib_right_4', 'rib_right_5', 'rib_right_6', 'rib_right_7', 'rib_right_8', 'rib_right_9', 'rib_right_10', 'rib_right_11', 'rib_right_12', 'sternum', 'costal_cartilages', 'scapula_left', 'scapula_right', 'clavicula_left', 'clavicula_right', 'humerus_left', 'humerus_right', 'femur_left', 'femur_right', 'hip_left', 'hip_right',
        'esophagus', 'stomach', 'duodenum', 'small_bowel', 'colon', 'urinary_bladder',
        'heart', 'aorta', 'pulmonary_vein', 'brachiocephalic_trunk', 'subclavian_artery_left', 'subclavian_artery_right', 'common_carotid_artery_left', 'common_carotid_artery_right', 'brachiocephalic_vein_left', 'brachiocephalic_vein_right', 'atrial_appendage_left', 'superior_vena_cava', 'inferior_vena_cava', 'portal_vein_and_splenic_vein', 'iliac_artery_left', 'iliac_artery_right', 'iliac_vena_left', 'iliac_vena_right',
        'brain', 'spinal_cord', 'thyroid_gland', 'trachea', 'lung_upper_lobe_left', 'lung_upper_lobe_right', 'lung_middle_lobe_right', 'lung_lower_lobe_left', 'lung_lower_lobe_right', 'adrenal_gland_left', 'adrenal_gland_right', 'spleen', 'liver', 'gallbladder', 'kidney_left', 'kidney_right', 'kidney_cyst_left', 'kidney_cyst_right', 'pancreas', 'prostate',
        'gluteus_maximus_left', 'gluteus_maximus_right', 'gluteus_medius_left', 'gluteus_medius_right', 'gluteus_minimus_left', 'gluteus_minimus_right', 'autochthon_left', 'autochthon_right', 'iliopsoas_left', 'iliopsoas_right',
      ],
    })),
  deselectAllOrgans: () => set({ selectedOrgans: [] }),

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
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setAiMessages: (msgs) => set({ aiMessages: msgs }),


  // Radiomics state
  radiomicsData: null,
  isRadiomicsLoading: false,
  radiomicsError: null,

  setRadiomicsData: (data) => set({ radiomicsData: data }),
  setIsRadiomicsLoading: (loading) => set({ isRadiomicsLoading: loading }),
  setRadiomicsError: (error) => set({ radiomicsError: error }),

}));

export default useStore;