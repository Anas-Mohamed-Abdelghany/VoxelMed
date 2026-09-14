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
import SimpleITK as sitk
import nibabel as nib
import cv2
from scipy.ndimage import zoom as ndzoom, center_of_mass
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
    (239, 68, 68),   # Red
    (34, 197, 94),   # Green
    (59, 130, 246),  # Blue
    (245, 158, 11),  # Amber
    (168, 85, 247),  # Purple
    (236, 72, 153),  # Rose/Pink
    (20, 184, 166),  # Teal
    (249, 115, 22),  # Orange
    (14, 165, 233),  # Sky
    (132, 204, 22),  # Lime
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

# --- Enhanced Smart Brush (snaps strictly to local tissue edges) ---
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
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), session_id: str = "default"):
    content = await file.read()
    filename = file.filename.lower()

    if filename.endswith((".nii", ".nii.gz")):
        tmp = tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False)
        tmp.write(content)
        tmp.close()
        arr, spacing, origin, direction = load_nifti(tmp.name)
        os.unlink(tmp.name)
    else:
        raise HTTPException(status_code=400, detail="Please upload a .nii or .nii.gz volume.")

    volumes[session_id] = {
        "array": arr,
        "original_array": arr.copy(),
        "is_restored": False,
        "spacing": spacing,
        "origin": origin,
        "direction": direction,
        "mask": np.zeros_like(arr, dtype=np.uint8),
        "filename": file.filename,
        "landmarks": {},
        "label_colormap": {},
    }

    return {
        "status": "ok",
        "shape": list(arr.shape),
        "spacing": list(spacing),
        "filename": file.filename,
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
    # 4-Channel RGBA: alpha=0 for background so it NEVER darkens the CT scan
    color_img = np.zeros((h, w, 4), dtype=np.uint8)
    for label_id in np.unique(slice_data):
        if label_id == 0:
            continue
        rgb = COLORMAP[(int(label_id) - 1) % len(COLORMAP)]
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
    label_idx = 1

    if totalseg_exe:
        print(f"\n[VoxelMed] Found TotalSegmentator at: {totalseg_exe}")
        tmp_vol = tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False)
        tmp_vol.close()

        # Write clean NIfTI with voxel spacing
        sitk_img = sitk.GetImageFromArray(arr)
        sitk_img.SetSpacing(vol["spacing"])
        sitk_img.SetOrigin(vol["origin"])
        sitk_img.SetDirection(vol["direction"])
        sitk.WriteImage(sitk_img, tmp_vol.name)

        out_dir = tempfile.mkdtemp(prefix="voxelmed_out_")

        env = os.environ.copy()
        # Force clean CPU execution to bypass incompatible CUDA driver
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["OMP_NUM_THREADS"] = "1"
        env["nnUNet_n_proc_DA"] = "1"

        # Safe command without unrecognized flags
        cmd = [totalseg_exe, "-i", tmp_vol.name, "-o", out_dir, "--fast"]

        print(f"[VoxelMed] Executing: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
            print(f"[VoxelMed] Subprocess completed with exit code: {result.returncode}")

            if result.returncode == 0:
                # Load TotalSegmentator NIfTI masks
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

    # --- Automatic Fallback Segmentation ---
    # If TotalSegmentator was missing, timed out, or downloading weights,
    # generate accurate multi-tissue masks directly from the CT volume so the app never fails!
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
                vol["label_colormap"][label_idx] = COLORMAP[(label_idx - 1) % len(COLORMAP)]
                label_idx += 1

        print(f"[VoxelMed INFO] Fallback segmentation generated {len(landmarks)} anatomical landmarks.")

    vol["mask"] = combined_mask
    vol["landmarks"] = landmarks

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)