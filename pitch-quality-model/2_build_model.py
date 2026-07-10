"""
Step 2: Train Stuff and Location XGBoost models per pitch type.
Uses 2023+2024+2025 data as training set.
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import cross_val_score

from utils import (
    PITCH_TYPES, STUFF_FEATURES, LOCATION_FEATURES,
    MIN_PITCHES_MODEL, engineer_features, load_scaling, save_scaling, to_plus,
)

COMBINED   = "data/statcast_2023_2026.parquet"
MODELS_DIR = "models"
os.makedirs(MODELS_DIR, exist_ok=True)

# HistGradientBoosting ≈ XGBoost, no libomp dependency on Mac
XGB_PARAMS = dict(
    max_iter=300,
    max_depth=5,
    learning_rate=0.05,
    min_samples_leaf=20,
    random_state=42,
)


def get_target(df: pd.DataFrame) -> pd.Series:
    """Use delta_run_exp if available and populated, else fall back to woba proxy."""
    if "delta_run_exp" in df.columns:
        valid = df["delta_run_exp"].notna().sum()
        if valid / len(df) > 0.5:
            print(f"    Using delta_run_exp ({valid:,} valid rows)")
            return df["delta_run_exp"]

    print("    Falling back to woba run value proxy")
    from utils import compute_run_value_fallback
    return compute_run_value_fallback(df)


def train_model(
    X: pd.DataFrame,
    y: pd.Series,
    label: str,
) -> HistGradientBoostingRegressor:
    model = HistGradientBoostingRegressor(**XGB_PARAMS)
    scores = cross_val_score(model, X, y, cv=3, scoring="neg_mean_squared_error", n_jobs=-1)
    rmse = np.sqrt(-scores.mean())
    print(f"    {label}: CV RMSE = {rmse:.4f}")
    model.fit(X, y)
    return model


if __name__ == "__main__":
    print("Loading data...")
    df_all = pd.read_parquet(COMBINED)

    # Training set: 2023+2024+2025
    df_train = df_all[df_all["game_year"].isin([2023, 2024, 2025])].copy()
    print(f"Training rows (2023-2025): {len(df_train):,}")

    # Feature engineering
    df_train = engineer_features(df_train)

    scaling_params: dict[str, dict] = load_scaling()  # load existing so skip check works

    # CU and KC are frequently mis-tagged by Statcast → pool them into one model
    POOL_TYPES: dict[str, list[str]] = {"CU": ["CU", "KC"]}
    SKIP_TYPES = {alt for alts in POOL_TYPES.values() for alt in alts if alt not in POOL_TYPES}

    for pitch_type in PITCH_TYPES:
        if pitch_type in SKIP_TYPES:
            pool_parent = next(k for k, v in POOL_TYPES.items() if pitch_type in v)
            print(f"\n=== {pitch_type} → pooled into {pool_parent} model — skipping ===")
            continue

        pool = POOL_TYPES.get(pitch_type, [pitch_type])
        df_pt = df_train[df_train["pitch_type"].isin(pool)].copy()
        n = len(df_pt)
        pool_label = "+".join(pool) if len(pool) > 1 else pitch_type
        print(f"\n=== {pool_label} ({n:,} pitches) ===")

        if n < MIN_PITCHES_MODEL:
            print(f"  Skipping — fewer than {MIN_PITCHES_MODEL} pitches.")
            continue

        # Skip if both models already trained
        stuff_path = f"{MODELS_DIR}/stuff_{pitch_type}.pkl"
        loc_path   = f"{MODELS_DIR}/location_{pitch_type}.pkl"
        if os.path.exists(stuff_path) and os.path.exists(loc_path) and pitch_type in scaling_params:
            print(f"  Already trained — skipping.")
            continue

        # Target
        y = get_target(df_pt)

        # Drop rows where key features or target are null
        stuff_mask = df_pt[STUFF_FEATURES].notna().all(axis=1) & y.notna()
        loc_mask   = df_pt[LOCATION_FEATURES].notna().all(axis=1) & y.notna()

        print(f"  Stuff rows: {stuff_mask.sum():,} | Location rows: {loc_mask.sum():,}")

        # ── Stuff model ─────────────────────────────────────────────────
        print("  Training Stuff model...")
        X_stuff = df_pt.loc[stuff_mask, STUFF_FEATURES]
        y_stuff = y[stuff_mask]
        stuff_model = train_model(X_stuff, y_stuff, "Stuff")
        joblib.dump(stuff_model, f"{MODELS_DIR}/stuff_{pitch_type}.pkl")

        # Scaling params from training predictions
        stuff_preds = stuff_model.predict(X_stuff)
        stuff_mean  = float(np.mean(stuff_preds))
        stuff_scale = float(np.std(stuff_preds))
        # Calibrate scale so 1 SD ≈ 15 points (like Fangraphs)
        stuff_scale = stuff_scale if stuff_scale > 0 else 1.0

        # ── Location model ───────────────────────────────────────────────
        print("  Training Location model...")
        X_loc = df_pt.loc[loc_mask, LOCATION_FEATURES]
        y_loc = y[loc_mask]
        loc_model = train_model(X_loc, y_loc, "Location")
        joblib.dump(loc_model, f"{MODELS_DIR}/location_{pitch_type}.pkl")

        loc_preds = loc_model.predict(X_loc)
        loc_mean  = float(np.mean(loc_preds))
        loc_scale = float(np.std(loc_preds))
        loc_scale = loc_scale if loc_scale > 0 else 1.0

        scaling_params[pitch_type] = {
            "stuff_mean":    stuff_mean,
            "stuff_scale":   stuff_scale,
            "location_mean": loc_mean,
            "location_scale": loc_scale,
        }

        # Sanity check: league average should be ~100
        sample_stuff = to_plus(stuff_preds[:1000], stuff_mean, stuff_scale)
        sample_loc   = to_plus(loc_preds[:1000],   loc_mean,   loc_scale)
        print(f"  Sanity check (sample mean): Stuff+ ≈ {np.mean(sample_stuff):.1f} | Loc+ ≈ {np.mean(sample_loc):.1f}")

    # For pooled alias types (e.g. KC uses CU model), compute their own scaling params.
    # KC pitchers have a different raw mean than the CU+KC training mix, so without
    # this, to_plus() would systematically bias KC scores relative to 100.
    ALIAS_TO_PRIMARY = {alias: primary
                        for primary, members in POOL_TYPES.items()
                        for alias in members if alias != primary}
    for alias_type, primary_type in ALIAS_TO_PRIMARY.items():
        if primary_type not in scaling_params:
            continue
        df_alias = df_train[df_train["pitch_type"] == alias_type].copy()
        if len(df_alias) < 100:
            continue
        s_model = joblib.load(f"{MODELS_DIR}/stuff_{primary_type}.pkl")
        l_model = joblib.load(f"{MODELS_DIR}/location_{primary_type}.pkl")
        s_ok = df_alias[STUFF_FEATURES].notna().all(axis=1)
        l_ok = df_alias[LOCATION_FEATURES].notna().all(axis=1)
        s_preds = s_model.predict(df_alias.loc[s_ok, STUFF_FEATURES]) if s_ok.any() else np.array([0.0])
        l_preds = l_model.predict(df_alias.loc[l_ok, LOCATION_FEATURES]) if l_ok.any() else np.array([0.0])
        parent = scaling_params[primary_type]
        scaling_params[alias_type] = {
            "stuff_mean":     float(np.mean(s_preds)),
            "stuff_scale":    float(np.std(s_preds)) or parent["stuff_scale"],
            "location_mean":  float(np.mean(l_preds)),
            "location_scale": float(np.std(l_preds)) or parent["location_scale"],
        }
        print(f"  [{alias_type}] alias scaling → stuff_mean={scaling_params[alias_type]['stuff_mean']:.6f}  scale={scaling_params[alias_type]['stuff_scale']:.6f}")

    save_scaling(scaling_params)
    print(f"\nScaling params saved → models/scaling_params.json")
    print(f"Models saved → {MODELS_DIR}/")
    print("\nDone.")
