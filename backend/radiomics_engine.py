import os
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.stats import skew
from xgboost import XGBClassifier

MODEL_FILE = Path(__file__).parent / "radiomics_pathology_engine.pkl"
CONFIG_FILE = Path(__file__).parent / "segmentation_config.json"

# ----------------------------------------------------------------------
# Display metadata - single source of truth for the biomarker UI.
# The frontend renders whatever rows this defines; adding a biomarker
# here is enough, no React changes needed.
# ----------------------------------------------------------------------
BIOMARKER_META = {
    "liver_vol_cm3":      {"label": "Liver Volume",       "unit": "cm³",    "ref": "< 1600 cm³"},
    "liver_mean_hu":      {"label": "Liver Mean Density", "unit": "HU",     "ref": "50 - 65 HU"},
    "spleen_vol_cm3":     {"label": "Spleen Volume",      "unit": "cm³",    "ref": "< 250 cm³"},
    "liver_spleen_ratio": {"label": "Liver/Spleen Ratio", "unit": "",       "ref": "> 1.0"},
    "l3_muscle_area_cm2": {"label": "L3 Muscle Area",     "unit": "cm²",    "ref": "> 130 cm²"},
    "smi":                {"label": "L3 SMI",             "unit": "cm²/m²", "ref": "> 45 cm²/m²"},
}

# Human-readable labels + the biomarker that grounds the evidence string,
# per model name. Unknown models still render generically.
DIAGNOSIS_META = {
    "steatosis":    {"label": "Hepatic Steatosis (Fatty Liver)",
                     "evidence_key": "liver_spleen_ratio", "evidence_fmt": "Liver-to-Spleen ratio: {}"},
    "sarcopenia":   {"label": "Sarcopenia / Myosteatosis",
                     "evidence_key": "smi", "evidence_fmt": "L3 SMI: {} cm²/m²"},
    "hepatomegaly": {"label": "Hepatomegaly",
                     "evidence_key": "liver_vol_cm3", "evidence_fmt": "Liver Volume: {} cm³"},
    "splenomegaly": {"label": "Splenomegaly",
                     "evidence_key": "spleen_vol_cm3", "evidence_fmt": "Spleen Volume: {} cm³"},
}


def _finite(value, default: float = 0.0) -> float:
    """Replace NaN/inf with a finite default (JSON- and model-safe).
    E.g. skew() of a uniform organ region is NaN."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


def biomarker_rows(biomarkers: dict) -> list:
    """Table rows for the UI, driven by BIOMARKER_META."""
    rows = []
    for key, meta in BIOMARKER_META.items():
        if key not in biomarkers:
            continue
        rows.append({
            "key": key,
            "label": meta["label"],
            "value": biomarkers[key],
            "unit": meta.get("unit", ""),
            "ref": meta.get("ref", ""),
        })
    return rows


def _diagnosis_label(disease: str) -> str:
    return DIAGNOSIS_META.get(disease, {}).get(
        "label", disease.replace("_", " ").title()
    )


def _diagnosis_evidence(disease: str, biomarkers: dict, probability: float) -> str:
    meta = DIAGNOSIS_META.get(disease)
    if meta:
        return meta["evidence_fmt"].format(biomarkers.get(meta["evidence_key"], "n/a"))
    return f"Probability: {round(probability * 100, 1)}%"


class RadiomicsEngine:
    def __init__(self, session_data: dict):
        self.session_data = session_data
        self.volume = session_data["array"]
        self.mask = session_data["mask"]
        self.spacing = session_data.get("spacing", (1.0, 1.0, 1.0))

        # Voxel volume in cm^3 (1000 mm^3 = 1 cm^3)
        self.voxel_vol_cm3 = float(np.prod(self.spacing)) / 1000.0
        # In-plane pixel area in cm^2 (axial plane slice Y*X)
        self.pixel_area_cm2 = float(self.spacing[0] * self.spacing[1]) / 100.0

        self.label_map = self._load_label_map()

    def _load_label_map(self) -> dict:
        """Loads organ name to integer ID mappings safely."""
        if "organ_to_label" in self.session_data and self.session_data["organ_to_label"]:
            return {
                str(k).lower().replace(" ", "_"): int(v) 
                for k, v in self.session_data["organ_to_label"].items()
            }

        mapping = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                idx = 1
                for sector, organs in cfg.items():
                    for organ_name, stem in organs.items():
                        mapping[organ_name.lower().replace(" ", "_")] = idx
                        mapping[str(stem).lower()] = idx
                        idx += 1
            except Exception as e:
                print(f"[RadiomicsEngine] Config load warning: {e}")

        if not mapping:
            mapping = {
                "spleen": 1, "liver": 2, "skeleton": 3,
                "vertebra_l3": 4, "skeletal_muscle": 5, "aorta": 6
            }
        return mapping

    def _get_organ_mask(self, organ_key: str) -> np.ndarray:
        """Finds the mask using flexible substring matching."""
        target = organ_key.lower().replace(" ", "_")

        if target in self.label_map:
            label_id = self.label_map[target]
            return self.mask == label_id

        for k, label_id in self.label_map.items():
            if target in k or k in target:
                return self.mask == label_id

        return np.zeros_like(self.mask, dtype=bool)

    def extract_all_biomarkers(self, height_m: float = 1.75) -> dict:
        # 1. Contrast Check via Aorta
        aorta_mask = self._get_organ_mask("aorta")
        has_contrast = 0
        if np.sum(aorta_mask) > 0:
            if float(np.mean(self.volume[aorta_mask])) > 140.0:
                has_contrast = 1

        # 2. Liver Radiomics (First-order & High-Order Asymmetry)
        liver_mask = self._get_organ_mask("liver")
        liver_voxels = self.volume[liver_mask] if np.sum(liver_mask) > 0 else np.array([])
        
        if len(liver_voxels) > 0:
            liver_vol = round(float(np.sum(liver_mask) * self.voxel_vol_cm3), 2)
            liver_mean = round(float(np.mean(liver_voxels)), 1)
            liver_std = round(float(np.std(liver_voxels)), 1)
            liver_p10 = round(float(np.percentile(liver_voxels, 10)), 1)
            liver_p90 = round(float(np.percentile(liver_voxels, 90)), 1)
            # skew() is undefined (NaN + warning) for a uniform region
            liver_skew = round(float(skew(liver_voxels)), 3) if liver_std > 0 else 0.0
        else:
            liver_vol, liver_mean, liver_std, liver_p10, liver_p90, liver_skew = 0.0, 55.0, 8.0, 45.0, 65.0, 0.0

        # 3. Spleen Radiomics (Biological Control)
        spleen_mask = self._get_organ_mask("spleen")
        spleen_voxels = self.volume[spleen_mask] if np.sum(spleen_mask) > 0 else np.array([])
        
        if len(spleen_voxels) > 0:
            spleen_vol = round(float(np.sum(spleen_mask) * self.voxel_vol_cm3), 2)
            spleen_mean = round(float(np.mean(spleen_voxels)), 1)
        else:
            spleen_vol, spleen_mean = 180.0, 50.0

        # 4. L3 Muscle Cross-Section & SMI
        l3_mask = self._get_organ_mask("vertebra_L3")
        muscle_mask = self._get_organ_mask("skeletal_muscle")

        if np.sum(muscle_mask) == 0:
            for k, organ_id in self.label_map.items():
                if any(m in k for m in ["muscle", "autochthon", "iliopsoas", "gluteus", "rectus_abdominis"]):
                    muscle_mask = muscle_mask | (self.mask == organ_id)

        if np.sum(l3_mask) > 0:
            best_z = int(np.argmax(np.sum(l3_mask, axis=(1, 2))))
            slice_muscle = muscle_mask[best_z, :, :]
            slice_ct = self.volume[best_z, :, :]
            valid_muscle = slice_muscle & (slice_ct >= -29.0) & (slice_ct <= 150.0)
            muscle_pixels = int(np.sum(valid_muscle))
            
            if muscle_pixels > 0:
                muscle_area = round(float(muscle_pixels * self.pixel_area_cm2), 2)
                muscle_mean_hu = round(float(np.mean(slice_ct[valid_muscle])), 1)
            else:
                muscle_area, muscle_mean_hu = 135.0, 38.0
        else:
            muscle_area, muscle_mean_hu = 135.0, 38.0

        smi = round(muscle_area / (height_m ** 2), 2)
        ratio = round(liver_mean / spleen_mean, 3) if spleen_mean != 0 else 1.0
        diff = round(liver_mean - spleen_mean, 2)

        # Sanitise: NaN/inf (e.g. skew of a uniform region) would crash the
        # JSON response and poison the model input.
        return {k: _finite(v) for k, v in {
            "liver_vol_cm3": liver_vol,
            "liver_mean_hu": liver_mean,
            "liver_std_hu": liver_std,
            "liver_p10": liver_p10,
            "liver_p90": liver_p90,
            "liver_skewness": liver_skew,
            "spleen_vol_cm3": spleen_vol,
            "spleen_mean_hu": spleen_mean,
            "liver_spleen_ratio": ratio,
            "liver_spleen_diff": diff,
            "l3_muscle_area_cm2": muscle_area,
            "l3_muscle_mean_hu": muscle_mean_hu,
            "smi": smi,
            "has_contrast": has_contrast
        }.items()}

    def extract_organ_volumes(self) -> list:
        """
        Measure the volume of every organ present in the segmentation mask.
        Standalone measurement feature: iterates whatever the segmentation
        produced (no hardcoded organ list, no model inference).
        """
        total_voxels = int(np.sum(self.mask > 0))
        if total_voxels == 0:
            return []

        rows = []
        seen_ids = set()
        for name, label_id in sorted(self.label_map.items(), key=lambda kv: (kv[1], kv[0])):
            if label_id in seen_ids:
                continue  # several keys can map to the same label id
            seen_ids.add(label_id)
            voxels = int(np.sum(self.mask == label_id))
            if voxels == 0:
                continue
            rows.append({
                "key": name,
                "organ": name.replace("_", " ").title(),
                "vol_cm3": round(float(voxels * self.voxel_vol_cm3), 2),
                "pct_of_total": round(100.0 * voxels / total_voxels, 1),
            })

        rows.sort(key=lambda r: r["vol_cm3"], reverse=True)
        return rows

    def predict_pathology(self, biomarkers: dict) -> dict:
        if MODEL_FILE.exists():
            try:
                bundle = joblib.load(MODEL_FILE)
                models = bundle["models"]

                # Feature order comes from the model bundle itself - never
                # hardcode it here, so retraining can never break inference.
                features_order = bundle.get("features")
                if not features_order:
                    any_model = next(iter(models.values()), None)
                    features_order = list(getattr(any_model, "feature_names_in_", []))
                if not features_order:
                    raise ValueError("model bundle has no feature order")

                # Missing biomarkers degrade to 0.0 instead of crashing.
                sample = {f: float(biomarkers.get(f, 0.0)) for f in features_order}
                df_sample = pd.DataFrame([sample], columns=features_order)

                diagnoses = {}
                for disease, model in models.items():
                    prob = float(model.predict_proba(df_sample)[0][1])
                    diagnoses[disease] = {
                        "prediction": bool(prob >= 0.5),
                        "risk_score": round(prob, 3),
                        "label": _diagnosis_label(disease),
                        "evidence": _diagnosis_evidence(disease, biomarkers, prob),
                    }
                return diagnoses
            except Exception as e:
                print(f"[RadiomicsEngine] Model load warning, using ACR clinical rules: {e}")

        # Deterministic Clinical Rule Engine (ACR fallback)
        fallback_rules = {
            "steatosis":    (0.92, 0.08,
                             biomarkers["liver_spleen_ratio"] < 0.9 or biomarkers["liver_mean_hu"] < 40),
            "sarcopenia":   (0.87, 0.12,
                             biomarkers["smi"] < 48 or biomarkers["l3_muscle_mean_hu"] < 32),
            "hepatomegaly": (0.85, 0.05, biomarkers["liver_vol_cm3"] > 1600.0),
            "splenomegaly": (0.89, 0.04, biomarkers["spleen_vol_cm3"] > 230.0),
        }

        diagnoses = {}
        for disease, (hi_risk, lo_risk, positive) in fallback_rules.items():
            risk = hi_risk if positive else lo_risk
            diagnoses[disease] = {
                "prediction": risk > 0.5,
                "risk_score": risk,
                "label": _diagnosis_label(disease),
                "evidence": _diagnosis_evidence(disease, biomarkers, risk),
            }
        return diagnoses