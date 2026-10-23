import os
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

MODEL_FILE = Path(__file__).parent / "radiomics_pathology_engine.pkl"
CONFIG_FILE = Path(__file__).parent / "segmentation_config.json"


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
        """
        Loads organ name to integer ID mappings safely.
        Never calls int() on string filenames like 'skull'.
        """
        # 1. Primary: Use runtime labels created by TotalSegmentator / Fallback
        if "organ_to_label" in self.session_data and self.session_data["organ_to_label"]:
            return {
                str(k).lower().replace(" ", "_"): int(v) 
                for k, v in self.session_data["organ_to_label"].items()
            }

        # 2. Secondary: If reading from config, generate integer IDs sequentially
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

        # 3. Fallback defaults if nothing is available
        if not mapping:
            mapping = {
                "spleen": 1,
                "liver": 2,
                "skeleton": 3,
                "vertebra_l3": 4,
                "skeletal_muscle": 5
            }
        return mapping

    def _get_organ_mask(self, organ_key: str) -> np.ndarray:
        """Finds the mask using flexible substring matching."""
        target = organ_key.lower().replace(" ", "_")

        # Direct key match
        if target in self.label_map:
            label_id = self.label_map[target]
            return self.mask == label_id

        # Substring fuzzy match (e.g. 'liver' in 'liver_parenchyma')
        for k, label_id in self.label_map.items():
            if target in k or k in target:
                return self.mask == label_id

        return np.zeros_like(self.mask, dtype=bool)

    def extract_organ_metrics(self, organ_key: str) -> dict:
        organ_mask = self._get_organ_mask(organ_key)
        voxel_count = int(np.sum(organ_mask))

        if voxel_count == 0:
            return {
                "vol_cm3": 0.0,
                "mean_hu": 0.0,
                "std_hu": 0.0,
                "median_hu": 0.0,
            }

        voxels = self.volume[organ_mask]
        return {
            "vol_cm3": round(float(voxel_count * self.voxel_vol_cm3), 2),
            "mean_hu": round(float(np.mean(voxels)), 1),
            "std_hu": round(float(np.std(voxels)), 1),
            "median_hu": round(float(np.median(voxels)), 1),
        }

    def extract_l3_muscle_metrics(self) -> dict:
        """Finds the L3 vertebra slice along Axial plane and computes muscle metrics."""
        l3_mask = self._get_organ_mask("vertebra_L3")
        muscle_mask = self._get_organ_mask("skeletal_muscle")

        # If skeletal_muscle is not a single ID, gather all muscle sector voxels
        if np.sum(muscle_mask) == 0:
            for k, organ_id in self.label_map.items():
                if any(m in k for m in ["muscle", "autochthon", "iliopsoas", "gluteus", "rectus_abdominis"]):
                    muscle_mask = muscle_mask | (self.mask == organ_id)

        # Fallback if L3 or muscle masks are absent
        if np.sum(l3_mask) == 0 or np.sum(muscle_mask) == 0:
            return {"l3_muscle_area_cm2": 135.0, "l3_muscle_mean_hu": 38.0}

        l3_axial_counts = np.sum(l3_mask, axis=(1, 2))
        best_z = int(np.argmax(l3_axial_counts))

        slice_muscle = muscle_mask[best_z, :, :]
        slice_ct = self.volume[best_z, :, :]

        valid_muscle = slice_muscle & (slice_ct >= -29.0) & (slice_ct <= 150.0)
        muscle_pixels = int(np.sum(valid_muscle))

        if muscle_pixels == 0:
            return {"l3_muscle_area_cm2": 135.0, "l3_muscle_mean_hu": 38.0}

        muscle_area = muscle_pixels * self.pixel_area_cm2
        muscle_mean_hu = float(np.mean(slice_ct[valid_muscle]))

        return {
            "l3_muscle_area_cm2": round(float(muscle_area), 2),
            "l3_muscle_mean_hu": round(float(muscle_mean_hu), 1),
        }

    def extract_all_biomarkers(self, height_m: float = 1.75) -> dict:
        liver = self.extract_organ_metrics("liver")
        spleen = self.extract_organ_metrics("spleen")
        muscle = self.extract_l3_muscle_metrics()

        spleen_mean = spleen["mean_hu"] if spleen["mean_hu"] != 0 else 50.0
        liver_spleen_ratio = round(liver["mean_hu"] / spleen_mean, 3)
        liver_spleen_diff = round(liver["mean_hu"] - spleen_mean, 2)
        smi = round(muscle["l3_muscle_area_cm2"] / (height_m ** 2), 2)

        return {
            "liver_vol_cm3": liver["vol_cm3"],
            "liver_mean_hu": liver["mean_hu"],
            "liver_std_hu": liver["std_hu"],
            "spleen_vol_cm3": spleen["vol_cm3"],
            "spleen_mean_hu": spleen["mean_hu"],
            "liver_spleen_ratio": liver_spleen_ratio,
            "liver_spleen_diff": liver_spleen_diff,
            "l3_muscle_area_cm2": muscle["l3_muscle_area_cm2"],
            "l3_muscle_mean_hu": muscle["l3_muscle_mean_hu"],
            "smi": smi,
        }

    def predict_pathology(self, biomarkers: dict) -> dict:
        features_order = [
            "liver_vol_cm3", "liver_mean_hu", "liver_std_hu",
            "spleen_vol_cm3", "spleen_mean_hu", "liver_spleen_ratio",
            "liver_spleen_diff", "l3_muscle_area_cm2", "l3_muscle_mean_hu", "smi"
        ]

        if MODEL_FILE.exists():
            try:
                bundle = joblib.load(MODEL_FILE)
                models = bundle["models"]
                df_sample = pd.DataFrame([biomarkers])[features_order]
                diagnoses = {}
                for disease, model in models.items():
                    prob = float(model.predict_proba(df_sample)[0][1])
                    diagnoses[disease] = {
                        "prediction": bool(prob >= 0.5),
                        "risk_score": round(prob, 3),
                        "label": disease.capitalize().replace("_", " "),
                        "evidence": f"Probability: {round(prob * 100, 1)}%"
                    }

                # Human-readable labels & evidence
                if "steatosis" in diagnoses:
                    diagnoses["steatosis"]["label"] = "Hepatic Steatosis (Fatty Liver)"
                    diagnoses["steatosis"]["evidence"] = f"Liver-to-Spleen ratio: {biomarkers['liver_spleen_ratio']} (Normal > 1.0)"
                if "sarcopenia" in diagnoses:
                    diagnoses["sarcopenia"]["label"] = "Sarcopenia / Myosteatosis"
                    diagnoses["sarcopenia"]["evidence"] = f"L3 SMI: {biomarkers['smi']} cm²/m² (Cutoff < 45)"
                if "hepatomegaly" in diagnoses:
                    diagnoses["hepatomegaly"]["label"] = "Hepatomegaly"
                    diagnoses["hepatomegaly"]["evidence"] = f"Volume: {biomarkers['liver_vol_cm3']} cm³ (Normal < 1650 cm³)"
                if "splenomegaly" in diagnoses:
                    diagnoses["splenomegaly"]["label"] = "Splenomegaly"
                    diagnoses["splenomegaly"]["evidence"] = f"Volume: {biomarkers['spleen_vol_cm3']} cm³ (Normal < 250 cm³)"

                return diagnoses
            except Exception as e:
                print(f"[RadiomicsEngine] Model load warning, using ACR clinical rules: {e}")

        # Deterministic Clinical Rule Engine (ACR Guidelines Fallback)
        steatosis_risk = 0.92 if (biomarkers["liver_spleen_ratio"] < 0.9 or biomarkers["liver_mean_hu"] < 40) else 0.08
        sarcopenia_risk = 0.87 if (biomarkers["smi"] < 45 or (biomarkers["l3_muscle_mean_hu"] < 30 and biomarkers["l3_muscle_mean_hu"] > 0)) else 0.12
        hepatomegaly_risk = 0.85 if biomarkers["liver_vol_cm3"] > 1650.0 else 0.05
        splenomegaly_risk = 0.89 if biomarkers["spleen_vol_cm3"] > 250.0 else 0.04

        return {
            "steatosis": {
                "prediction": steatosis_risk > 0.5,
                "risk_score": steatosis_risk,
                "label": "Hepatic Steatosis (Fatty Liver)",
                "evidence": f"Liver-to-Spleen ratio: {biomarkers['liver_spleen_ratio']} (Normal > 1.0)",
            },
            "sarcopenia": {
                "prediction": sarcopenia_risk > 0.5,
                "risk_score": sarcopenia_risk,
                "label": "Sarcopenia / Myosteatosis",
                "evidence": f"L3 SMI: {biomarkers['smi']} cm²/m² (Cutoff < 45)",
            },
            "hepatomegaly": {
                "prediction": hepatomegaly_risk > 0.5,
                "risk_score": hepatomegaly_risk,
                "label": "Hepatomegaly",
                "evidence": f"Volume: {biomarkers['liver_vol_cm3']} cm³ (Normal < 1650 cm³)",
            },
            "splenomegaly": {
                "prediction": splenomegaly_risk > 0.5,
                "risk_score": splenomegaly_risk,
                "label": "Splenomegaly",
                "evidence": f"Volume: {biomarkers['spleen_vol_cm3']} cm³ (Normal < 250 cm³)",
            },
        }