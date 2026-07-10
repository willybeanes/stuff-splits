"""
Step 3: Score all pitches (2025 + 2026) with trained models.
Outputs data/scored_pitches.parquet.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: F401 — needed for joblib unpickling

from utils import (
    PITCH_TYPES, STUFF_FEATURES, LOCATION_FEATURES,
    engineer_features, load_scaling, load_calibration, apply_calibration, to_plus,
)

COMBINED = "data/statcast_2023_2026.parquet"
SCORED   = "data/scored_pitches.parquet"
MODELS   = "models"

# KC is pooled into CU model during training (frequently mis-tagged by Statcast)
MODEL_ALIAS: dict[str, str] = {"KC": "CU"}


if __name__ == "__main__":
    print("Loading data...")
    df = pd.read_parquet(COMBINED)
    print(f"  {len(df):,} total pitches")

    df = engineer_features(df)
    scaling = load_scaling()
    calib   = load_calibration()
    if calib:
        print("  Calibration params found — will align to Fangraphs scale.")
    else:
        print("  No calibration params — run 5_calibrate_to_fangraphs.py to align to Fangraphs.")

    df["stuff_plus"]    = np.nan
    df["location_plus"] = np.nan

    for pitch_type in PITCH_TYPES:
        mask = df["pitch_type"] == pitch_type
        n = mask.sum()
        if n == 0:
            continue

        model_pt = MODEL_ALIAS.get(pitch_type, pitch_type)
        stuff_path = f"{MODELS}/stuff_{model_pt}.pkl"
        loc_path   = f"{MODELS}/location_{model_pt}.pkl"
        if not os.path.exists(stuff_path) or not os.path.exists(loc_path):
            print(f"  [{pitch_type}] No model found — skipping")
            continue

        if model_pt not in scaling:
            print(f"  [{pitch_type}] No scaling params — skipping")
            continue

        # Use pitch-type-specific scaling if available (e.g. KC has own mean/scale
        # even though it shares the CU model), otherwise fall back to parent model's params
        params = scaling.get(pitch_type, scaling[model_pt])
        stuff_model = joblib.load(stuff_path)
        loc_model   = joblib.load(loc_path)

        df_pt = df[mask].copy()

        # Stuff — score where all features present
        stuff_feat_ok = df_pt[STUFF_FEATURES].notna().all(axis=1)
        if stuff_feat_ok.any():
            X_s = df_pt.loc[stuff_feat_ok, STUFF_FEATURES]
            raw = stuff_model.predict(X_s)
            vals = to_plus(raw, params["stuff_mean"], params["stuff_scale"])
            vals = apply_calibration(vals, pitch_type, "s", calib)
            df.loc[df_pt[stuff_feat_ok].index, "stuff_plus"] = vals

        # Location — score where all features present
        loc_feat_ok = df_pt[LOCATION_FEATURES].notna().all(axis=1)
        if loc_feat_ok.any():
            X_l = df_pt.loc[loc_feat_ok, LOCATION_FEATURES]
            raw = loc_model.predict(X_l)
            vals = to_plus(raw, params["location_mean"], params["location_scale"])
            vals = apply_calibration(vals, pitch_type, "l", calib)
            df.loc[df_pt[loc_feat_ok].index, "location_plus"] = vals

        scored = mask.sum()
        s_ok   = int(stuff_feat_ok.sum())
        l_ok   = int(loc_feat_ok.sum())
        print(f"  [{pitch_type}] {scored:,} pitches → Stuff scored: {s_ok:,} | Loc scored: {l_ok:,}")

    # Pitching+ = average of Stuff+ and Location+
    df["pitching_plus"] = df[["stuff_plus", "location_plus"]].mean(axis=1)

    graded = df["pitching_plus"].notna().sum()
    print(f"\n{graded:,} pitches with pitching_plus ({graded/len(df)*100:.1f}%)")
    print(f"League avg Stuff+: {df['stuff_plus'].mean():.1f}")
    print(f"League avg Loc+:   {df['location_plus'].mean():.1f}")
    print(f"League avg Pitch+: {df['pitching_plus'].mean():.1f}")

    df.to_parquet(SCORED, index=False)
    print(f"\nSaved → {SCORED}")
    print("Done.")
