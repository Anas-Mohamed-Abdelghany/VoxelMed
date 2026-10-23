# Save as compile_model.py in W:\VoxelMed\
import pandas as pd
import numpy as np
import joblib
from xgboost import XGBClassifier

print("Loading balanced clinical dataset on Windows...")
df = pd.read_csv("backend/balanced_clinical_radiomics.csv")

# 1. Ensure all features exist with safe defaults
if "has_contrast" not in df.columns:
    df["has_contrast"] = 0

# 2. Derive Consensus Clinical Diagnostic Labels (ACR Guidelines)
if "steatosis" not in df.columns:
    df["steatosis"] = np.where(
        df["has_contrast"] == 0,
        ((df["liver_spleen_diff"] < -10.0) | (df["liver_spleen_ratio"] < 0.90) | (df["liver_p10"] < 30.0)),
        ((df["liver_spleen_diff"] < -20.0) | (df["liver_spleen_ratio"] < 0.82))
    ).astype(int)

if "sarcopenia" not in df.columns:
    df["sarcopenia"] = ((df["smi"] < 48.0) | (df["l3_muscle_mean_hu"] < 32.0)).astype(int)

if "hepatomegaly" not in df.columns:
    df["hepatomegaly"] = (df["liver_vol_cm3"] > 1600.0).astype(int)

if "splenomegaly" not in df.columns:
    df["splenomegaly"] = (df["spleen_vol_cm3"] > 230.0).astype(int)

features = [
    "liver_vol_cm3", "liver_mean_hu", "liver_std_hu", "liver_p10", "liver_p90",
    "liver_skewness", "spleen_vol_cm3", "spleen_mean_hu", "liver_spleen_ratio",
    "liver_spleen_diff", "l3_muscle_area_cm2", "l3_muscle_mean_hu", "smi", "has_contrast"
]

models = {}

print("Compiling native Windows XGBoost models for all 4 pathologies...")
for target in ["steatosis", "sarcopenia", "hepatomegaly", "splenomegaly"]:
    n_pos = int(df[target].sum())
    n_neg = len(df) - n_pos
    pos_weight = float(n_neg / max(1, n_pos))

    clf = XGBClassifier(
        n_estimators=70,
        max_depth=3,
        learning_rate=0.04,
        subsample=0.75,
        colsample_bytree=0.75,
        scale_pos_weight=pos_weight,
        reg_alpha=1.5,
        reg_lambda=3.0,
        eval_metric="logloss",
        random_state=42
    )

    clf.fit(df[features], df[target])
    models[target] = clf
    print(f"  * {target.capitalize()} ({n_pos} Positive / {n_neg} Negative) compiled successfully.")

# Save directly as a native Windows pickle
joblib.dump({"models": models, "features": features}, "backend/radiomics_pathology_engine.pkl")

# Update CSV with labels for your records
df.to_csv("backend/balanced_clinical_radiomics.csv", index=False)
print("\n[SUCCESS] Native Windows model saved to backend/radiomics_pathology_engine.pkl!")