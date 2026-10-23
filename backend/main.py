import io
import os
import sys
import json
import shutil
import base64
import tempfile
import subprocess
from typing import Optional, List

import numpy as np
import httpx
import SimpleITK as sitk
import nibabel as nib
import cv2
from scipy.ndimage import zoom as ndzoom, center_of_mass
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# --- Import bootstrap -------------------------------------------------------
# Make `backend.*` imports work regardless of launch directory:
#   - from repo root:  uvicorn backend.main:app
#   - from backend/:   uvicorn main:app   (used by start.sh / --reload)
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from backend.radiomics_engine import RadiomicsEngine, biomarker_rows
except ModuleNotFoundError:  # running with backend/ itself on sys.path
    from radiomics_engine import RadiomicsEngine, biomarker_rows

load_dotenv()

app = FastAPI(title="VoxelMed API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

volumes = {}

COLORMAP = [
    # --- 1. SKELETON (25 items) - Bright Gold / Titanium / Platinum tones ---
    (255, 215, 0),    # 0: Skull - Pure Gold
    (240, 200, 90),   # 1: Clavicula - Light Gold
    (220, 180, 70),   # 2: Scapula - Amber Gold
    (245, 205, 100),  # 3: Humerus - Bright Amber
    (230, 190, 80),   # 4: Vertebrae C - Warm Gold
    (255, 230, 120),  # 5: Sternum - Bright Yellow-Gold
    (210, 170, 60),   # 6: Rib 1-12 - Bronze Gold
    (235, 195, 85),   # 7: Vertebrae T - Golden Amber
    (225, 185, 75),   # 8: Vertebrae L - Deep Gold
    (200, 160, 50),   # 9: Costal Cartilages - Dark Bronze
    (190, 150, 45),   # 10: Ulna - Metallic Bronze
    (215, 175, 65),   # 11: Radius - Brass
    (170, 130, 40),   # 12: Intervertebral Discs - Deep Brass
    (255, 220, 110),  # 13: Hip - Bright Gold
    (210, 165, 55),   # 14: Sacrum - Antique Gold
    (180, 140, 40),   # 15: Carpal - Dark Brass
    (195, 155, 45),   # 16: Metacarpal - Gold
    (185, 145, 42),   # 17: Phalanges Hand - Antique Brass
    (255, 235, 130),  # 18: Femur - Bright Platinum Gold
    (220, 180, 80),   # 19: Patella - Light Bronze
    (200, 155, 50),   # 20: Fibula - Bronze
    (240, 200, 95),   # 21: Tibia - Bright Gold
    (175, 135, 38),   # 22: Tarsal - Dark Bronze
    (190, 150, 44),   # 23: Metatarsal - Brass
    (182, 142, 41),   # 24: Phalanges Foot - Deep Bronze

    # --- 2. GASTROINTESTINAL (6 items) - Distinct Teals & Emerald Greens ---
    (0, 206, 209),    # 25: Esophagus - Dark Turquoise
    (60, 179, 113),   # 26: Stomach - Medium Sea Green
    (46, 139, 87),    # 27: Duodenum - Sea Green
    (32, 178, 170),   # 28: Small Bowel - Light Sea Green
    (72, 209, 204),   # 29: Colon - Pale Turquoise
    (70, 130, 180),   # 30: Urinary Bladder - Steel Blue

    # --- 3. CARDIOVASCULAR (18 items) - Vivid Reds (Arteries) & Royal Blues (Veins) ---
    (255, 0, 0),      # 31: Common Carotid Artery - Pure Vivid Red
    (0, 128, 255),    # 32: Subclavian Artery - Bright Blue
    (220, 20, 60),    # 33: Brachiocephalic Trunk - Crimson Red
    (0, 0, 205),      # 34: Superior Vena Cava - Medium Blue
    (255, 69, 0),     # 35: Aorta - Orange-Red (High Contrast!)
    (255, 105, 180),  # 36: Right Atrium - Hot Pink
    (219, 112, 147),  # 37: Right Ventricle - Pale Violet Red
    (218, 165, 32),   # 38: Portal Vein - Goldenrod (Distinct from GI)
    (238, 44, 44),    # 39: Iliac Artery - Firebrick Red
    (30, 144, 255),   # 40: Iliac Vein - Dodger Blue
    (0, 191, 255),    # 41: Brachiocephalic Vein - Deep Sky Blue
    (138, 43, 226),   # 42: Pulmonary Artery - Blue Violet
    (255, 20, 147),   # 43: Atrial Appendage - Deep Pink
    (255, 77, 77),    # 44: Left Ventricle - Bright Red
    (178, 34, 34),    # 45: Myocardium - Firebrick
    (255, 182, 193),  # 46: Left Atrium - Light Pink
    (100, 149, 237),  # 47: Splenic Vein - Cornflower Blue
    (0, 0, 139),      # 48: Inferior Vena Cava - Dark Blue

    # --- 4. OTHER ORGANS (14 items) - Maximum Color Separation ---
    (147, 112, 219),  # 49: Brain - Medium Purple
    (0, 255, 255),    # 50: Spinal Cord - Cyan / Aqua
    (50, 205, 50),    # 51: Thyroid Gland - Lime Green
    (245, 222, 179),  # 52: Trachea - Wheat
    (135, 206, 235),  # 53: Lung Upper Lobe - Sky Blue
    (0, 150, 255),    # 54: Lung Middle Lobe - Vivid Sky Blue
    (0, 102, 204),    # 55: Lung Lower Lobe - Cerulean Blue
    (255, 165, 0),    # 56: Adrenal Gland - Pure Orange
    (220, 20, 60),    # 57: Spleen - Crimson (Distinct Red)
    (46, 125, 50),    # 58: Liver - Deep Emerald Green (High Contrast!)
    (124, 252, 0),    # 59: Gallbladder - Lawn Green
    (255, 255, 0),    # 60: Kidney - Bright Pure Yellow (Extremely distinct!)
    (255, 140, 0),    # 61: Pancreas - Dark Orange
    (186, 85, 211),   # 62: Prostate - Orchid

    # --- 5. MUSCLES (18 items) - Rich Brick Reds / Maroons ---
    (165, 42, 42),    # 63: Supraspinatus - Brown / Brick Red
    (178, 34, 34),    # 64: Infraspinatus - Firebrick
    (150, 40, 40),    # 65: Subscapularis - Dark Red
    (139, 0, 0),      # 66: Deltoid - Dark Red
    (160, 50, 50),    # 67: Pectoralis Minor - Brick
    (170, 60, 60),    # 68: Coracobrachial - Reddish Brown
    (145, 35, 35),    # 69: Teres Major - Deep Red
    (130, 30, 30),    # 70: Serratus Anterior - Maroon
    (120, 25, 25),    # 71: Autochthon - Dark Maroon
    (165, 45, 45),    # 72: Triceps Brachii - Brick Red
    (155, 40, 40),    # 73: Iliopsoas - Dark Red
    (175, 55, 55),    # 74: Gluteus Minimus - Coral Red
    (165, 45, 45),    # 75: Gluteus Medius - Brick
    (150, 35, 35),    # 76: Gluteus Maximus - Maroon
    (140, 30, 30),    # 77: Thigh Medial - Dark Red
    (180, 70, 70),    # 78: Sartorius - Light Brick Red
    (160, 45, 45),    # 79: Quadriceps Femoris - Brick
    (135, 25, 25),    # 80: Thigh Posterior - Deep Maroon
    (170, 50, 50),    # 81: Trapezius - Red
]
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "segmentation_config.json")

# ----------------------------------------------------------------------
# Request Models
# ----------------------------------------------------------------------
class SegmentRequest(BaseModel):
    sectors: List[str] = []
    organs: List[str] = []

class DrawRequest(BaseModel):
    view: str
    slice_index: int
    points: List[List[int]]
    label: int = 1
    erase: bool = False
    radius: int = 5
    smart: bool = False

class MeasureRequest(BaseModel):
    view: str
    slice_index: int
    point1: List[int]
    point2: List[int]

class RadiomicsRequest(BaseModel):
    patient_height_m: float = 1.75
    session_id: str = "default"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def get_session(session_id: str = "default"):
    if session_id not in volumes:
        raise HTTPException(status_code=404, detail="No volume loaded. Upload a file first.")
    return volumes[session_id]

def normalize_slice(arr, window_center=None, window_width=None):
    if window_center is not None and window_width is not None:
        min_val = window_center - window_width / 2.0
        max_val = window_center + window_width / 2.0
        arr = np.clip(arr, min_val, max_val)
        arr = ((arr - min_val) / (max_val - min_val + 1e-8) * 255.0).astype(np.uint8)
    else:
        p2, p98 = np.percentile(arr[arr != 0], [2, 98]) if np.any(arr != 0) else (0, 1)
        arr = np.clip(arr, p2, p98)
        arr = ((arr - p2) / (p98 - p2 + 1e-8) * 255.0).astype(np.uint8)
    return arr

def arr_to_png_base64(arr):
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def load_nifti(path: str):
    img = sitk.ReadImage(path)
    arr = sitk.GetArrayFromImage(img)
    return arr, img.GetSpacing(), img.GetOrigin(), img.GetDirection()

def find_totalsegmentator_executable():
    """Locate TotalSegmentator across system paths, user pip paths, and venvs."""
    candidates = [
        shutil.which("TotalSegmentator"),
        os.path.expanduser("~/.local/bin/TotalSegmentator"),
        os.path.join(os.path.dirname(sys.executable), "TotalSegmentator"),
        "/usr/local/bin/TotalSegmentator",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None

def enhanced_smart_brush(target_slice, ref_slice, center_x, center_y, radius, label_val):
    h, w = ref_slice.shape[:2]
    cx, cy = int(round(center_x)), int(round(center_y))
    r = int(max(1, radius))

    pad = max(4, r // 2)
    x0, x1 = max(0, cx - r - pad), min(w, cx + r + pad + 1)
    y0, y1 = max(0, cy - r - pad), min(h, cy + r + pad + 1)

    sub_ref = ref_slice[y0:y1, x0:x1].astype(np.float32)
    if sub_ref.size == 0 or (sub_ref.max() - sub_ref.min() < 1e-6):
        cv2.circle(target_slice, (cx, cy), r, label_val, -1)
        return

    norm = ((sub_ref - sub_ref.min()) / (sub_ref.max() - sub_ref.min() + 1e-6) * 255.0).astype(np.uint8)
    gx = cv2.Sobel(norm, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(norm, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx ** 2 + gy ** 2)

    local_cx = min(max(cx - x0, 0), norm.shape[1] - 1)
    local_cy = min(max(cy - y0, 0), norm.shape[0] - 1)
    seed_val = float(norm[local_cy, local_cx])

    Y, X = np.ogrid[:norm.shape[0], :norm.shape[1]]
    dist_sq = (X - local_cx) ** 2 + (Y - local_cy) ** 2
    intensity_diff = np.abs(norm.astype(np.float32) - seed_val)

    in_radius = dist_sq <= float(r) ** 2
    near_center = dist_sq <= float(max(2, r * 0.4)) ** 2
    below_edge = grad < 80.0
    similar_int = intensity_diff < 40.0

    adaptive_mask = near_center | (in_radius & below_edge & similar_int)
    sub_target = target_slice[y0:y1, x0:x1]
    sub_target[adaptive_mask > 0] = label_val

# ----------------------------------------------------------------------
# API Endpoints
# ----------------------------------------------------------------------
def _dicom_slice_position(img) -> float:
    """z position (ImagePositionPatient[2]) of a single DICOM slice, if present."""
    try:
        if not img.HasMetaDataKey("0020|0032"):
            return None
        vals = [float(v) for v in img.GetMetaData("0020|0032").replace("\\", " ").split()]
        return vals[2] if len(vals) >= 3 else None
    except ValueError:
        return None

def _dicom_instance_number(img) -> int:
    """InstanceNumber of a single DICOM slice, if present."""
    try:
        if not img.HasMetaDataKey("0020|0013"):
            return None
        return int(float(img.GetMetaData("0020|0013").strip()))
    except ValueError:
        return None

def _dicom_float_tag(img, tag) -> float:
    """Generic float-valued DICOM metadata tag, if present."""
    try:
        if not img.HasMetaDataKey(tag):
            return None
        return float(img.GetMetaData(tag).strip())
    except ValueError:
        return None

async def _load_dicom_series(dcm_uploads: List[UploadFile]):
    """
    Read one or more DICOM (.dcm) uploads as a single series.
    A study folder selection often contains several series (scouts,
    reconstructions, prior scans...): the largest detected series wins and
    unrelated files are ignored instead of stacking slices from mixed
    series into one garbled volume.
    Returns (array, spacing, origin, direction) with 3D-normalised metadata.
    """
    tmp_dir = tempfile.mkdtemp(prefix="voxelmed_dcm_")
    try:
        paths = []
        for i, f in enumerate(dcm_uploads):
            # Index-prefixed names: selections from different folders can
            # share basenames and would otherwise overwrite each other.
            safe_name = "%05d_%s" % (i, os.path.basename(f.filename or "slice.dcm"))
            path = os.path.join(tmp_dir, safe_name)
            with open(path, "wb") as out:
                out.write(await f.read())
            paths.append(path)

        reader = sitk.ImageSeriesReader()

        # Group uploads by SeriesInstanceUID and keep the largest series;
        # GDCM also sorts its slices by image position.
        best_names = []
        try:
            for sid in reader.GetGDCMSeriesIDs(tmp_dir) or []:
                names = list(reader.GetGDCMSeriesFileNames(tmp_dir, sid))
                if len(names) > len(best_names):
                    best_names = names
        except Exception:
            best_names = []

        # If every detected series holds a single file while several files
        # were uploaded, the UIDs were regenerated per slice (anonymisation):
        # grouping is meaningless, so stack everything manually instead.
        if len(paths) > 1 and len(best_names) <= 1:
            best_names = []

        if best_names:
            reader.SetFileNames(best_names)
            image = reader.Execute()
            arr = sitk.GetArrayFromImage(image)
            spacing = image.GetSpacing()
            origin = image.GetOrigin()
            direction = image.GetDirection()
            skipped = len(paths) - len(best_names)
            if skipped > 0:
                print(f"[VoxelMed INFO] DICOM upload: using the largest series "
                      f"({len(best_names)} slices); ignored {skipped} file(s) "
                      f"from other series.")
        else:
            # No series detected (broken/missing SeriesInstanceUID):
            # read every file and stack the slices in acquisition order.
            slices = []
            for p in paths:
                img = sitk.ReadImage(p)
                slice_arr = sitk.GetArrayFromImage(img)
                if slice_arr.ndim == 2:
                    slice_arr = slice_arr[np.newaxis, ...]
                slices.append({
                    "path": p,
                    "arr": slice_arr,
                    "spacing": img.GetSpacing(),
                    "origin": img.GetOrigin(),
                    "direction": img.GetDirection(),
                    "z": _dicom_slice_position(img),
                    "inst": _dicom_instance_number(img),
                    "step": _dicom_float_tag(img, "0018|0088"),   # SpacingBetweenSlices
                    "thickness": _dicom_float_tag(img, "0018|0050"),
                })

            # Sort by acquisition order; only rely on a tag when every slice
            # carries it so a missing tag can never crash the sort.
            zs = [s["z"] for s in slices]
            insts = [s["inst"] for s in slices]
            if all(z is not None for z in zs):
                slices.sort(key=lambda s: s["z"])
            elif all(v is not None for v in insts):
                slices.sort(key=lambda s: s["inst"])
            else:
                slices.sort(key=lambda s: os.path.basename(s["path"]))

            # Slice spacing from consecutive positions, else from the
            # SpacingBetweenSlices/SliceThickness tags, else 1.0.
            z_step = None
            valid_zs = sorted(z for z in zs if z is not None)
            if len(valid_zs) >= 2:
                diffs = np.diff(np.asarray(valid_zs, dtype=float))
                diffs = diffs[diffs > 1e-6]
                if diffs.size:
                    z_step = float(np.median(diffs))
            if z_step is None:
                z_step = next(
                    (s["step"] or s["thickness"] for s in slices
                     if s["step"] or s["thickness"]),
                    1.0,
                )

            try:
                arr = np.concatenate([s["arr"] for s in slices], axis=0)
            except ValueError:
                raise RuntimeError(
                    "DICOM slices have inconsistent image sizes; "
                    "make sure all selected .dcm files belong to one series."
                )
            spacing = slices[0]["spacing"]
            origin = slices[0]["origin"]
            direction = slices[0]["direction"]
            if len(spacing) >= 3:
                spacing = (spacing[0], spacing[1], z_step)

        if arr.ndim == 2:  # single-slice DICOM -> volume with depth 1
            arr = arr[np.newaxis, ...]

        # Normalise 2D metadata to 3D so downstream 3D code keeps working
        if len(spacing) == 2:
            spacing = (spacing[0], spacing[1], 1.0)
        if len(origin) == 2:
            origin = (origin[0], origin[1], 0.0)
        if len(direction) == 4:
            direction = (direction[0], direction[1], 0.0,
                         direction[2], direction[3], 0.0,
                         0.0, 0.0, 1.0)

        return arr, spacing, origin, direction
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

@app.post("/api/upload")
async def upload_file(files: List[UploadFile] = File(...), session_id: str = "default"):
    if not files:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    first_name = (files[0].filename or "").lower()

    # DICOM series: one or many .dcm files
    if first_name.endswith(".dcm"):
        dcm_files = [f for f in files if (f.filename or "").lower().endswith(".dcm")]
        if not dcm_files:
            raise HTTPException(status_code=400, detail="No DICOM (.dcm) files provided.")
        try:
            arr, spacing, origin, direction = await _load_dicom_series(dcm_files)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to read DICOM series: {e}",
            )
        original_name = files[0].filename
    else:
        file = files[0]
        content = await file.read()
        filename = first_name
        original_name = file.filename

        if filename.endswith((".nii", ".nii.gz")):
            tmp = tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False)
            tmp.write(content)
            tmp.close()
            arr, spacing, origin, direction = load_nifti(tmp.name)
            os.unlink(tmp.name)
        elif filename.endswith((".jpg", ".jpeg", ".png")):
            # 2D raster image: load as grayscale and treat as a single-slice
            # volume so the rest of the 3D pipeline works unchanged.
            img = Image.open(io.BytesIO(content)).convert("L")
            arr = np.asarray(img, dtype=np.uint8)[np.newaxis, ...]
            spacing = (1.0, 1.0, 1.0)
            origin = (0.0, 0.0, 0.0)
            direction = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        else:
            raise HTTPException(status_code=400, detail="Please upload a .nii, .nii.gz, .dcm, .jpg, .jpeg or .png file.")

    volumes[session_id] = {
        "array": arr,
        "original_array": arr.copy(),
        "is_restored": False,
        "spacing": spacing,
        "origin": origin,
        "direction": direction,
        "mask": np.zeros_like(arr, dtype=np.uint8),
        "filename": original_name,
        "landmarks": {},
        "label_colormap": {},
    }

    return {
        "status": "ok",
        "shape": list(arr.shape),
        "spacing": list(spacing),
        "filename": original_name,
    }

@app.get("/api/volume")
async def get_volume_info(session_id: str = "default"):
    vol = get_session(session_id)
    return {
        "shape": list(vol["array"].shape),
        "spacing": list(vol["spacing"]),
        "origin": list(vol["origin"]),
        "filename": vol["filename"],
        "is_restored": vol.get("is_restored", False),
    }

@app.get("/api/volume/data")
async def get_volume_data(session_id: str = "default"):
    vol = get_session(session_id)
    arr = vol["array"]
    mask = vol.get("mask", None)

    target_voxels = 128 * 128 * 128
    current_voxels = arr.size
    factor = (target_voxels / current_voxels) ** (1.0 / 3.0) if current_voxels > target_voxels else 1.0

    if factor < 1.0:
        arr_3d = ndzoom(arr, factor, order=1)
        mask_3d = ndzoom(mask, factor, order=0) if mask is not None else None
    else:
        arr_3d = arr
        mask_3d = mask

    normalized = normalize_slice(arr_3d.astype(np.float64))
    dims = [int(x) for x in arr_3d.shape]

    vol_b64 = base64.b64encode(normalized.tobytes()).decode("utf-8")
    mask_b64 = ""
    if mask_3d is not None and np.any(mask_3d > 0):
        mask_b64 = base64.b64encode(mask_3d.astype(np.uint8).tobytes()).decode("utf-8")

    return {
        "data": vol_b64,
        "mask": mask_b64,
        "dims": dims,
        "spacing": list(vol["spacing"]),
        "label_colormap": {str(k): list(v) for k, v in vol.get("label_colormap", {}).items()},
        "organ_to_label": vol.get("organ_to_label", {}),
    }

@app.get("/api/segmentation/mask3d")
async def get_mask_3d(session_id: str = "default"):
    """Segmentation mask + label mapping for the 3D volume renderer.

    Used to refresh the 3D mask AFTER segmentation runs without re-downloading
    the whole CT volume. Applies the exact same downsampling as /api/volume/data
    so the mask stays voxel-aligned with the already-loaded 3D texture.
    """
    vol = get_session(session_id)
    arr = vol["array"]
    mask = vol.get("mask", None)
    if mask is None:
        return {"mask": "", "label_colormap": {}, "organ_to_label": {}}

    target_voxels = 128 * 128 * 128
    current_voxels = arr.size
    factor = (target_voxels / current_voxels) ** (1.0 / 3.0) if current_voxels > target_voxels else 1.0
    mask_3d = ndzoom(mask, factor, order=0) if factor < 1.0 else mask

    mask_b64 = ""
    if np.any(mask_3d > 0):
        mask_b64 = base64.b64encode(mask_3d.astype(np.uint8).tobytes()).decode("utf-8")

    return {
        "mask": mask_b64,
        "label_colormap": {str(k): list(v) for k, v in vol.get("label_colormap", {}).items()},
        "organ_to_label": vol.get("organ_to_label", {}),
    }

@app.get("/api/slice/{view}/{slice_index}/base64")
async def get_slice_base64(
    view: str,
    slice_index: int,
    window_center: float = Query(default=None),
    window_width: float = Query(default=None),
    session_id: str = "default",
):
    vol = get_session(session_id)
    arr = vol["array"]
    max_idx = arr.shape[0 if view == "axial" else 2 if view == "sagittal" else 1] - 1
    slice_index = max(0, min(max_idx, slice_index))

    if view == "axial":
        slice_data = arr[slice_index, :, :]
    elif view == "sagittal":
        slice_data = arr[:, :, slice_index]
    elif view == "coronal":
        slice_data = arr[:, slice_index, :]
    else:
        raise HTTPException(status_code=400, detail="Invalid view plane")

    normalized = normalize_slice(slice_data.astype(np.float64), window_center, window_width)
    return {"image": arr_to_png_base64(normalized), "slice_index": slice_index, "max_slice": max_idx}

@app.get("/api/slices/montage/{view}/base64")
async def get_montage_base64(
    view: str,
    window_center: float = Query(default=None),
    window_width: float = Query(default=None),
    session_id: str = "default",
):
    vol = get_session(session_id)
    arr = vol["array"]
    axis = 0 if view == "axial" else 2 if view == "sagittal" else 1
    num_slices = arr.shape[axis]

    max_tiles = 20
    if num_slices <= max_tiles:
        indices = list(range(num_slices))
    else:
        indices = [int(i * (num_slices - 1) / (max_tiles - 1)) for i in range(max_tiles)]

    slices = []
    for idx in indices:
        if view == "axial":
            slice_data = arr[idx, :, :]
        elif view == "sagittal":
            slice_data = arr[:, :, idx]
        else:
            slice_data = arr[:, idx, :]
        normalized = normalize_slice(slice_data.astype(np.float64), window_center, window_width)
        slices.append(Image.fromarray(normalized))

    target_size = 512
    upscaled = []
    for img in slices:
        w, h = img.size
        scale = target_size / max(w, h)
        if scale > 1:
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.NEAREST)
        upscaled.append(img)

    n = len(upscaled)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    tile_w, tile_h = upscaled[0].size

    montage = Image.new('L', (cols * tile_w, rows * tile_h), 0)
    for i, img in enumerate(upscaled):
        r, c = divmod(i, cols)
        montage.paste(img, (c * tile_w, r * tile_h))

    buf = io.BytesIO()
    montage.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {"image": b64, "view": view, "total_slices": num_slices, "montage_slices": n}

@app.get("/api/segmentation/{view}/{slice_index}/base64")
async def get_segmentation_slice_base64(view: str, slice_index: int, session_id: str = "default"):
    vol = get_session(session_id)
    mask = vol["mask"]
    max_idx = mask.shape[0 if view == "axial" else 2 if view == "sagittal" else 1] - 1
    slice_index = max(0, min(max_idx, slice_index))

    if view == "axial":
        slice_data = mask[slice_index, :, :]
    elif view == "sagittal":
        slice_data = mask[:, :, slice_index]
    elif view == "coronal":
        slice_data = mask[:, slice_index, :]
    else:
        raise HTTPException(status_code=400, detail="Invalid view")

    h, w = slice_data.shape
    color_img = np.zeros((h, w, 4), dtype=np.uint8)
    label_colormap = vol.get("label_colormap", {})
    for label_id in np.unique(slice_data):
        if label_id == 0:
            continue
        rgb = label_colormap.get(int(label_id), COLORMAP[(int(label_id) - 1) % len(COLORMAP)])
        color_img[slice_data == label_id] = [rgb[0], rgb[1], rgb[2], 255]

    return {"image": arr_to_png_base64(color_img), "slice_index": slice_index}

# ----------------------------------------------------------------------
# Robust TotalSegmentator with Automatic Fallback
# ----------------------------------------------------------------------
@app.post("/api/segment")
@app.post("/api/segmentation/run")
async def run_segmentation(req: Optional[SegmentRequest] = None, session_id: str = "default"):
    if req is None:
        req = SegmentRequest()

    vol = get_session(session_id)
    arr = vol["array"]
    vol_shape = arr.shape

    totalseg_exe = find_totalsegmentator_executable()
    seg_successful = False
    combined_mask = np.zeros_like(arr, dtype=np.uint8)
    landmarks = {}
    organ_to_label = {}
    label_idx = 1

    if totalseg_exe:
        print(f"\n[VoxelMed] Found TotalSegmentator at: {totalseg_exe}")
        tmp_vol = tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False)
        tmp_vol.close()

        sitk_img = sitk.GetImageFromArray(arr)
        sitk_img.SetSpacing(vol["spacing"])
        sitk_img.SetOrigin(vol["origin"])
        sitk_img.SetDirection(vol["direction"])
        sitk.WriteImage(sitk_img, tmp_vol.name)

        out_dir = tempfile.mkdtemp(prefix="voxelmed_out_")

        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["OMP_NUM_THREADS"] = "1"
        env["nnUNet_n_proc_DA"] = "1"

        cmd = [totalseg_exe, "-i", tmp_vol.name, "-o", out_dir, "--fast"]

        print(f"[VoxelMed] Executing: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
            print(f"[VoxelMed] Subprocess completed with exit code: {result.returncode}")

            if result.returncode == 0:
                config = {}
                if os.path.exists(CONFIG_PATH):
                    with open(CONFIG_PATH) as f:
                        config = json.load(f)

                selected_set = set(req.organs) if req.organs else None

                for sector_name, sector_organs in config.items():
                    for organ_name, stem in sector_organs.items():
                        if selected_set and stem not in selected_set and organ_name not in selected_set:
                            continue

                        mask_path = os.path.join(out_dir, f"{stem}.nii.gz")
                        if not os.path.exists(mask_path):
                            mask_path = os.path.join(out_dir, f"{stem}.nii")

                        if os.path.exists(mask_path):
                            mask_nib = nib.load(mask_path)
                            mask_data = (mask_nib.get_fdata() > 0.5).astype(np.uint8)
                            mask_data = np.transpose(mask_data, (2, 1, 0))

                            if mask_data.shape != vol_shape:
                                factors = [s / o for s, o in zip(vol_shape, mask_data.shape)]
                                mask_data = (ndzoom(mask_data.astype(np.float32), factors, order=0) > 0.5).astype(np.uint8)

                            if np.any(mask_data > 0):
                                combined_mask[mask_data > 0] = label_idx
                                cz, cy, cx = center_of_mass(mask_data)
                                landmarks[organ_name] = [int(round(cz)), int(round(cy)), int(round(cx))]
                                organ_to_label[organ_name] = label_idx
                                vol["label_colormap"][label_idx] = COLORMAP[(label_idx - 1) % len(COLORMAP)]
                                label_idx += 1

                if len(landmarks) > 0:
                    seg_successful = True
                    print(f"[VoxelMed] Successfully loaded {len(landmarks)} organs from TotalSegmentator.")
            else:
                print(f"[VoxelMed WARNING] TotalSegmentator failed:\n{result.stderr[-800:]}")
        except Exception as e:
            print(f"[VoxelMed WARNING] Exception running TotalSegmentator: {e}")
        finally:
            if os.path.exists(tmp_vol.name):
                os.unlink(tmp_vol.name)
            shutil.rmtree(out_dir, ignore_errors=True)

    if not seg_successful:
        print("[VoxelMed INFO] Running high-speed anatomical segmenter fallback...")
        norm_vol = normalize_slice(arr.astype(np.float64))

        fallback_organs = [
            ("Skeleton", norm_vol > 175),
            ("Brain", (norm_vol >= 45) & (norm_vol <= 110)),
            ("Liver", (norm_vol >= 80) & (norm_vol <= 140)),
            ("Kidneys", (norm_vol >= 60) & (norm_vol <= 130)),
            ("Soft Tissue", (norm_vol >= 30) & (norm_vol <= 75)),
        ]

        label_idx = 1
        for name, mask_bool in fallback_organs:
            if np.any(mask_bool):
                combined_mask[mask_bool] = label_idx
                cz, cy, cx = center_of_mass(mask_bool.astype(np.float32))
                landmarks[name] = [int(round(cz)), int(round(cy)), int(round(cx))]
                organ_to_label[name] = label_idx
                vol["label_colormap"][label_idx] = COLORMAP[(label_idx - 1) % len(COLORMAP)]
                label_idx += 1

        print(f"[VoxelMed INFO] Fallback segmentation generated {len(landmarks)} anatomical landmarks.")

    vol["mask"] = combined_mask
    vol["landmarks"] = landmarks
    vol["organ_to_label"] = organ_to_label

    return {
        "status": "ok",
        "landmarks": landmarks,
        "num_organs": len(landmarks),
    }

@app.post("/api/landmarks/{organ_name}/navigate")
async def navigate_to_landmark(organ_name: str, session_id: str = "default"):
    vol = get_session(session_id)
    if organ_name not in vol["landmarks"]:
        raise HTTPException(status_code=404, detail=f"Landmark '{organ_name}' not found")
    return {"position": vol["landmarks"][organ_name], "organ": organ_name}

@app.get("/api/landmarks")
async def get_landmarks(session_id: str = "default"):
    vol = get_session(session_id)
    return {"landmarks": vol["landmarks"]}

@app.post("/api/segmentation/draw")
async def draw_segmentation_endpoint(req: DrawRequest, session_id: str = "default"):
    vol = get_session(session_id)
    mask = vol["mask"]
    arr = vol["array"]

    slice_idx = req.slice_index
    if req.view == "axial":
        target = mask[slice_idx, :, :]
        ref = arr[slice_idx, :, :]
    elif req.view == "sagittal":
        target = mask[:, :, slice_idx]
        ref = arr[:, :, slice_idx]
    elif req.view == "coronal":
        target = mask[:, slice_idx, :]
        ref = arr[:, slice_idx, :]
    else:
        raise HTTPException(status_code=400, detail="Invalid view")

    val = 0 if req.erase else req.label
    r = req.radius

    for pt in req.points:
        x, y = pt[0], pt[1]
        if req.smart and not req.erase:
            enhanced_smart_brush(target, ref, x, y, r, val)
        else:
            cv2.circle(target, (int(x), int(y)), int(r), int(val), -1)

    return {"status": "ok"}

@app.post("/api/measure")
async def measure(req: MeasureRequest, session_id: str = "default"):
    vol = get_session(session_id)
    sp = vol["spacing"]
    p1, p2 = np.array(req.point1, dtype=np.float64), np.array(req.point2, dtype=np.float64)

    if req.view == "axial":
        dist_mm = float(np.hypot((p2[0] - p1[0]) * sp[0], (p2[1] - p1[1]) * sp[1]))
    elif req.view == "sagittal":
        dist_mm = float(np.hypot((p2[0] - p1[0]) * sp[1], (p2[1] - p1[1]) * sp[2]))
    else:
        dist_mm = float(np.hypot((p2[0] - p1[0]) * sp[0], (p2[1] - p1[1]) * sp[2]))

    return {
        "view": req.view,
        "slice_index": req.slice_index,
        "distance_mm": round(dist_mm, 2),
        "point1": req.point1,
        "point2": req.point2,
    }

@app.post("/api/restore/toggle")
async def toggle_motion_restoration(session_id: str = "default"):
    vol = get_session(session_id)
    is_restored = vol.get("is_restored", False)

    if is_restored:
        vol["array"] = vol["original_array"].copy()
        vol["is_restored"] = False
        return {"status": "ok", "is_restored": False, "message": "Original scan restored"}
    else:
        arr = vol["original_array"].astype(np.float32)
        restored = np.empty_like(arr)
        for i in range(arr.shape[0]):
            sl = arr[i]
            denoised = cv2.bilateralFilter(sl, d=5, sigmaColor=40, sigmaSpace=40)
            gauss = cv2.GaussianBlur(denoised, (0, 0), 1.5)
            sharpened = cv2.addWeighted(denoised, 1.4, gauss, -0.4, 0)
            restored[i] = sharpened

        vol["array"] = restored
        vol["is_restored"] = True
        return {"status": "ok", "is_restored": True, "message": "Motion artifact restoration active"}

# ----------------------------------------------------------------------
# Radiomics & AI Biomarker Engine Endpoint
# ----------------------------------------------------------------------
@app.post("/api/radiomics/analyze")
async def analyze_radiomics(req: RadiomicsRequest = RadiomicsRequest()):
    vol = get_session(req.session_id)
    
    if vol.get("array") is None:
        raise HTTPException(status_code=400, detail="No volume loaded. Please upload a CT scan.")
    
    if vol.get("mask") is None or np.sum(vol["mask"]) == 0:
        raise HTTPException(
            status_code=400, 
            detail="No segmentation mask found. Please run AI Segmentation first."
        )

    try:
        engine = RadiomicsEngine(vol)
        biomarkers = engine.extract_all_biomarkers(height_m=req.patient_height_m)
        diagnoses = engine.predict_pathology(biomarkers)
        
        return {
            "status": "success",
            "biomarkers": biomarkers,
            "biomarker_rows": biomarker_rows(biomarkers),
            "diagnoses": diagnoses
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Radiomics analysis failed: {str(e)}")

# ----------------------------------------------------------------------
# Organ Volume Measurement (standalone feature - no model inference)
# ----------------------------------------------------------------------
@app.post("/api/radiomics/volumes")
async def measure_organ_volumes(req: RadiomicsRequest = RadiomicsRequest()):
    vol = get_session(req.session_id)

    if vol.get("array") is None:
        raise HTTPException(status_code=400, detail="No volume loaded. Please upload a CT scan.")

    if vol.get("mask") is None or np.sum(vol["mask"]) == 0:
        raise HTTPException(
            status_code=400,
            detail="No segmentation mask found. Please run AI Segmentation first."
        )

    try:
        engine = RadiomicsEngine(vol)
        organ_volumes = engine.extract_organ_volumes()
        if not organ_volumes:
            raise HTTPException(
                status_code=400,
                detail="No segmented organs found in the mask. Please run AI Segmentation first."
            )

        return {
            "status": "success",
            "organ_volumes": organ_volumes,
            "total_cm3": round(sum(v["vol_cm3"] for v in organ_volumes), 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Volume measurement failed: {str(e)}")

# ----------------------------------------------------------------------
# AI Report Endpoint
# ----------------------------------------------------------------------
class AIReportRequest(BaseModel):
    messages: list
    model: str = "openrouter/free"

@app.post("/api/ai/report")
async def ai_report(req: AIReportRequest):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set in .env")

    async def stream_openrouter():
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:3000",
                    "X-Title": "VoxelMed",
                },
                json={
                    "model": req.model,
                    "messages": req.messages,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"data: {json.dumps({'error': f'OpenRouter error {resp.status_code}: {body.decode()}'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"
                    elif line.strip() == "":
                        continue

    return StreamingResponse(stream_openrouter(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)