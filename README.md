# VoxelMed

**AI-Powered Medical Image Viewer & Exploration Platform**

Built for the *AI for Real-World Response* Hackathon (Track 1 - Medical Sector) by Anas, Zyad, Hassan, and Nada.

---

## Overview

VoxelMed is a dual-architecture medical imaging application for viewing, segmenting, and exploring CT/MRI volumes. It provides clinical-grade multi-planar reconstruction, real-time 3D volume rendering, AI-powered organ segmentation, and interactive volume exploration tools.

**Two modes of operation:**

| Mode | Stack | Entry Point |
|------|-------|-------------|
| **Desktop** | PyQt5 + VTK + SimpleITK | `python -m backend.app` |
| **Web** | FastAPI + React + Three.js | Backend: `uvicorn backend.main:app` / Frontend: `npm run dev` |

---

## Features

### Core Viewer

| Feature | Description |
|---------|-------------|
| Multi-Planar Reconstruction (MPR) | Synchronized Axial, Sagittal, and Coronal views |
| 3D Volume Rendering | Real-time GPU-accelerated 3D visualization (VTK on desktop, Three.js + GLSL raymarching on web) |
| Interactive Crosshairs | Orthogonal crosshair tracking; clicking one view syncs all three |
| Window/Level Adjustment | Brightness/contrast via right-click-drag, sliders, or clinical presets |
| Per-View Zoom & Pan | Independent zoom (scroll wheel) and pan (left-drag) per view panel |
| Per-View Rotation | Configurable rotation (-180 to +180) per view |
| Anatomical Compass | Labeled orientation badges (A/P/R/L/S/I) on each view |
| Maximize/Restore | Any panel can be maximized to fill the viewport |

### Segmentation

| Feature | Description |
|---------|-------------|
| Manual Brush | Pixel-level painting on segmentation masks |
| Eraser | Remove painted regions from masks |
| Smart Brush | Edge-aware brush that snaps to tissue boundaries using Sobel gradient detection |
| Multi-View Sync | Drawing on one view updates all orthogonal views |
| Per-Organ Mask Toggle | Show/hide individual organ segmentation overlays |
| Color Picker | Custom brush/label color selection |
| Brush Size Control | Configurable diameter (1-20px) |

### AI-Powered Features

| Feature | Description |
|---------|-------------|
| TotalSegmentator Integration | Automatic multi-organ CT segmentation (81+ organs across 5 sectors) via CLI subprocess |
| Fallback Segmentation | Threshold-based tissue masks when TotalSegmentator is unavailable |
| Landmark Detection | Computes organ centroids from segmentation masks |
| Landmark Navigation | Click an organ name to jump all views to its centroid |
| Sector-Based Selection | Choose organs by anatomical sector (Skeleton, GI, Cardiovascular, Other, Muscles) |
| Organ Map | Overview image of all TotalSegmentator organ classes |

### Measurement

| Feature | Description |
|---------|-------------|
| Smart Caliper | Auto-detects lesion boundaries via Otsu thresholding + connected components; computes RECIST diameter |
| Manual Caliper | Two-point distance measurement with mm display and perpendicular tick marks |
| Measurement History | All measurements stored with view, slice index, and distance |

### 3D Lab (Volume Explorer)

| Feature | Description |
|---------|-------------|
| Orthogonal Clip Planes | Three independent clipping planes (X/Y/Z) with sliders and flip buttons |
| AI Segmentation Layers | Per-organ opacity control (selected organ vs. rest of volume) |
| Tissue Layer Presets | Radio-button presets: All Tissue, Skin/Fat, Soft Tissue, Bone |
| Tissue Threshold Slider | Manual intensity cutoff to peel away low-density tissue |
| Reset All | Restore all clips, layers, and visibility to defaults |

### Motion Artifact Restoration

| Feature | Description |
|---------|-------------|
| Bilateral Filter + Unsharp Mask | Per-slice edge-preserving denoising + contrast enhancement |
| Toggle On/Off | One-click toggle to switch between original and restored volume |

### Clinical Presets (Web)

| Preset | Window | Level |
|--------|--------|-------|
| Brain | 80 | 40 |
| Subdural/Hemorrhage | 210 | 75 |
| Soft Tissue | 350 | 50 |
| Bone | 2000 | 500 |
| Lung | 1500 | -600 |
| Mediastinum | 40 | 40 |
| Liver/Abdomen | 150 | 30 |

---

## Tech Stack

### Frontend (Web)

| Category | Technology |
|----------|------------|
| Framework | React 18 |
| Build Tool | Vite 5 |
| State Management | Zustand |
| 3D Rendering | Three.js + React Three Fiber + Drei |
| Medical Imaging | Cornerstone Core + Math + Tools |
| Styling | Tailwind CSS |
| Shaders | Custom GLSL 3.0 raymarching |

### Backend

| Category | Technology |
|----------|------------|
| API Framework | FastAPI |
| Desktop GUI | PyQt5 |
| Medical Image I/O | SimpleITK, NiBabel |
| Image Processing | OpenCV, NumPy, SciPy |
| 3D Visualization | VTK |
| AI Segmentation | TotalSegmentator (CLI) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload NIfTI file |
| `GET` | `/api/volume` | Get volume metadata |
| `GET` | `/api/volume/data` | Get downsampled 3D volume as base64 |
| `GET` | `/api/slice/{view}/{index}/base64` | Get 2D slice as base64 PNG |
| `GET` | `/api/segmentation/{view}/{index}/base64` | Get segmentation overlay as RGBA PNG |
| `POST` | `/api/segmentation/run` | Run AI segmentation |
| `POST` | `/api/segmentation/draw` | Draw on segmentation mask |
| `POST` | `/api/landmarks/{organ}/navigate` | Navigate to organ landmark |
| `GET` | `/api/landmarks` | Get all landmark positions |
| `POST` | `/api/measure` | Measure distance between two points |
| `POST` | `/api/restore/toggle` | Toggle motion artifact restoration |

---

## Project Structure

```
VoxelMed/
├── backend/
│   ├── app.py                  # Desktop entry point
│   ├── main.py                 # FastAPI web server
│   ├── image_viewer.py         # Main QMainWindow (desktop)
│   ├── image_processing.py     # Slice display, crosshairs, caliper, restoration
│   ├── image_label.py          # Mouse interaction widget
│   ├── segmentation.py         # Brush/eraser/smart brush drawing
│   ├── vtk_renderer.py         # VTK 3D volume rendering
│   ├── ui.py                   # Desktop GUI builder (toolbar, sidebar, views)
│   ├── landmark_detector.py    # TotalSegmentator QThread worker
│   ├── landmark_nav.py         # Landmark navigation sidebar
│   ├── volume_explorer.py      # Standalone 3D Lab window
│   ├── volume_explorer_ui.py   # 3D Lab UI
│   ├── segmentation_config.json # Organ/sector mapping (81 organs, 5 sectors)
│   ├── run_segmentation.py     # CLI batch segmentation script
│   └── dicom - nfti/           # Sample data
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Root layout
│   │   ├── components/
│   │   │   ├── LandingScreen.jsx   # File upload screen
│   │   │   ├── Toolbar.jsx         # Top toolbar
│   │   │   ├── Sidebar.jsx         # Left panel (Main / AI Seg / 3D Lab)
│   │   │   ├── MPRViewer.jsx       # 2x2 grid (3 MPR + 3D)
│   │   │   ├── VolumeRenderer.jsx  # Three.js 3D renderer
│   │   │   ├── AISegmentation.jsx  # Organ selection UI
│   │   │   ├── LandmarkNav.jsx     # Landmark navigation
│   │   │   └── ControlsPanel.jsx   # Clinical presets & tools
│   │   ├── api/client.js       # API client functions
│   │   ├── store/useStore.js   # Zustand state management
│   │   └── styles/             # CSS
│   ├── public/
│   │   └── map.png             # Organ map image
│   ├── package.json
│   ├── vite.config.js          # Dev server + API proxy
│   └── tailwind.config.js      # Custom color palette
├── LICENSE                     # MIT License
└── README.md
```

---

## Supported Formats

| Format | Extensions | Read | Write |
|--------|------------|------|-------|
| NIfTI | `.nii`, `.nii.gz` | Yes | Yes |
| DICOM | Series of `.dcm` | Yes | No |
| PNG | Base64 encoded | Generated for API | N/A |

---

## Configuration

### segmentation_config.json

Maps 5 anatomical sectors to 81 TotalSegmentator organ classes:

| Sector | Count | Examples |
|--------|-------|----------|
| Skeleton | 25 | Skull, Vertebrae, Femur, Ribs, etc. |
| Gastrointestinal | 6 | Esophagus, Stomach, Colon, Bladder |
| Cardiovascular | 18 | Aorta, Heart chambers, Vena Cava |
| Other organs | 14 | Brain, Liver, Kidney, Lungs, Spleen |
| Muscles | 18 | Deltoid, Trapezius, Gluteus, Quadriceps |

### Backend Session State

Each session stores:
```python
{
    "array": np.ndarray,           # Current volume (may be restored)
    "original_array": np.ndarray,  # Original unmodified volume
    "is_restored": bool,           # Motion restoration active
    "spacing": tuple,              # Voxel spacing in mm
    "origin": tuple,               # Volume origin
    "direction": tuple,            # Direction cosines
    "mask": np.uint8 array,        # Segmentation mask
    "filename": str,               # Original filename
    "landmarks": dict,             # {organ_name: [z, y, x]}
    "label_colormap": dict,        # {label_id: (R, G, B)}
}
```

---

## Getting Started

### Desktop

```bash
pip install PyQt5 vtk SimpleITK nibabel opencv-python numpy scipy
python -m backend.app
```

### Web

```bash
# Terminal 1 - Backend
pip install fastapi uvicorn simpleitk nibabel opencv-python numpy scipy pillow
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## License

MIT License - Copyright 2026 Anas Mohamed Abdelghany
