"""
Daily update: pull yesterday's Statcast for 2026, re-score, push platoon_grades to Supabase.

Designed to run in GitHub Actions (or locally) each morning after the previous
night's games are official. Incrementally appends to a cached 2026 parquet so
re-runs stay fast.

Usage:
  python3 daily_update.py              # auto-detects yesterday
  python3 daily_update.py 2026-06-24   # explicit date (for backfill)
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
import pybaseball
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env.local")

pybaseball.cache.enable()

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
DATA_DIR  = ROOT / "data"
MODELS    = ROOT / "models"
DATA_DIR.mkdir(exist_ok=True)

CACHE_2026 = DATA_DIR / "statcast_2026.parquet"   # separate 2026-only cache
SCORED     = DATA_DIR / "scored_pitches.parquet"

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# ── Feature lists (must match training) ───────────────────────────────────────
from utils import (
    PITCH_TYPES, STUFF_FEATURES, LOCATION_FEATURES,
    engineer_features, load_scaling, load_calibration, apply_calibration, to_plus,
)

MODEL_ALIAS: dict[str, str] = {"KC": "CU"}

KEEP_COLS = [
    "pitcher", "player_name", "game_date", "game_year",
    "pitch_type", "p_throws", "stand",
    "release_speed", "effective_speed", "release_spin_rate", "release_extension",
    "release_pos_x", "release_pos_z", "release_pos_y",
    "pfx_x", "pfx_z",
    "spin_axis", "arm_angle",
    "api_break_z_with_gravity", "api_break_x_arm",
    "plate_x", "plate_z",
    "sz_top", "sz_bot",
    "fielder_2",
    "balls", "strikes", "outs_when_up",
    "on_1b", "on_2b", "on_3b", "inning",
    "events", "description", "type",
    "estimated_woba_using_speedangle", "woba_value", "woba_denom",
    "delta_run_exp",
    "at_bat_number", "pitch_number",
    "game_pk",
]

MIN_PITCHES = 50
UPSERT_BATCH = 500


def pull_date(target_date: str) -> pd.DataFrame:
    """Pull one day of Statcast and keep relevant cols."""
    print(f"  Pulling Statcast for {target_date}…", flush=True)
    try:
        df = pybaseball.statcast(target_date, target_date, verbose=False)
    except Exception as e:
        print(f"  WARNING: pybaseball pull failed: {e}")
        return pd.DataFrame()
    if df is None or df.empty:
        print("  No data returned (off-day?).")
        return pd.DataFrame()
    existing = [c for c in KEEP_COLS if c in df.columns]
    df = df[existing].copy()
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date.astype(str)
    print(f"  {len(df):,} pitches pulled.")
    return df


def load_or_create_cache() -> pd.DataFrame:
    if CACHE_2026.exists():
        df = pd.read_parquet(CACHE_2026)
        print(f"  Loaded cached 2026 data: {len(df):,} pitches through "
              f"{df['game_date'].max()}.")
        return df
    return pd.DataFrame()


def append_new_rows(cached: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if new.empty:
        return cached
    if cached.empty:
        return new
    # Drop any existing rows for the same date(s) before appending
    dates_to_add = set(new["game_date"].unique())
    cached = cached[~cached["game_date"].isin(dates_to_add)]
    return pd.concat([cached, new], ignore_index=True)


def score_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = engineer_features(df.copy())
    scaling = load_scaling()
    calib   = load_calibration()

    df["stuff_plus"]    = np.nan
    df["location_plus"] = np.nan

    for pitch_type in PITCH_TYPES:
        mask = df["pitch_type"] == pitch_type
        if mask.sum() == 0:
            continue

        model_pt   = MODEL_ALIAS.get(pitch_type, pitch_type)
        stuff_path = MODELS / f"stuff_{model_pt}.pkl"
        loc_path   = MODELS / f"location_{model_pt}.pkl"
        if not stuff_path.exists() or not loc_path.exists():
            continue

        params  = scaling.get(pitch_type, scaling.get(model_pt, {}))
        s_mean  = params.get("stuff_mean", 0.0)
        s_scale = params.get("stuff_scale", 1.0) or 1.0
        l_mean  = params.get("location_mean", 0.0)
        l_scale = params.get("location_scale", 1.0) or 1.0

        s_ok = mask & df[STUFF_FEATURES].notna().all(axis=1)
        l_ok = mask & df[LOCATION_FEATURES].notna().all(axis=1)

        s_model = joblib.load(stuff_path)
        l_model = joblib.load(loc_path)

        if s_ok.any():
            s_raw = s_model.predict(df.loc[s_ok, STUFF_FEATURES])
            s_raw = apply_calibration(s_raw, pitch_type, "s", calib)
            df.loc[s_ok, "stuff_plus"] = to_plus(s_raw, s_mean, s_scale)

        if l_ok.any():
            l_raw = l_model.predict(df.loc[l_ok, LOCATION_FEATURES])
            l_raw = apply_calibration(l_raw, pitch_type, "l", calib)
            df.loc[l_ok, "location_plus"] = to_plus(l_raw, l_mean, l_scale)

    return df


def get_outcome(desc: str) -> str:
    d = str(desc).lower()
    if "called_strike"   in d:                        return "cs"
    if "swinging_strike" in d or "foul_tip" in d:     return "whiff"
    if "foul"            in d:                        return "foul"
    if "ball"            in d or "blocked_ball" in d: return "ball"
    if "hit_into_play"   in d:                        return "in_play"
    return "other"


def build_platoon_rows(df: pd.DataFrame, names: dict[int, str]) -> list[dict]:
    df = df[df["pitch_type"].notna() & df["stand"].notna()].copy()
    df["outcome"] = df["description"].apply(get_outcome)

    rows = []
    for (pid, pt, hand), g in df.groupby(["pitcher", "pitch_type", "stand"]):
        n = len(g)
        if n < MIN_PITCHES:
            continue
        s_vals = g["stuff_plus"].dropna()
        l_vals = g["location_plus"].dropna()
        p_vals = ((g["stuff_plus"].fillna(0) + g["location_plus"].fillna(0)) / 2).where(
            g["stuff_plus"].notna() & g["location_plus"].notna()
        ).dropna()

        oc = g["outcome"].value_counts()
        rows.append({
            "season":        2026,
            "pitcher_id":    int(pid),
            "pitcher_name":  names.get(int(pid), f"Player {pid}"),
            "pitcher_team":  g["p_throws"].iloc[0] if "p_throws" in g.columns else None,
            "pitch_type":    pt,
            "stand":         hand,
            "n_pitches":     n,
            "stuff_plus":    round(float(s_vals.mean()), 1) if len(s_vals) else None,
            "loc_plus":      round(float(l_vals.mean()), 1) if len(l_vals) else None,
            "pitching_plus": round(float(p_vals.mean()), 1) if len(p_vals) else None,
            "avg_velo":      round(float(g["release_speed"].mean()), 1) if "release_speed" in g else None,
            "whiff_pct":     round(oc.get("whiff", 0) / n * 100, 1),
            "cs_pct":        round(oc.get("cs",    0) / n * 100, 1),
            "zone_pct":      None,
        })
    return rows


def upsert_platoon(supabase, rows: list[dict]):
    conflict = "season,pitcher_id,pitch_type,stand"
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = rows[i:i + UPSERT_BATCH]
        supabase.table("platoon_grades").upsert(chunk, on_conflict=conflict).execute()
    print(f"  Upserted {len(rows)} platoon_grades rows.")


def load_names(df: pd.DataFrame) -> dict[int, str]:
    names: dict[int, str] = {}
    for _, row in df[["pitcher", "player_name"]].dropna().drop_duplicates().iterrows():
        try:
            names[int(row["pitcher"])] = row["player_name"]
        except (ValueError, TypeError):
            pass
    return names


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else str(date.today() - timedelta(days=1))
    print(f"\n=== Daily Platoon Update: {target} ===")

    # 1. Pull yesterday's data
    new_data = pull_date(target)

    # 2. Load existing 2026 cache and merge
    cached = load_or_create_cache()
    merged = append_new_rows(cached, new_data)

    if merged.empty:
        print("No 2026 data available — nothing to do.")
        return

    # 3. Save updated cache
    merged.to_parquet(CACHE_2026, index=False)
    print(f"  Cache updated: {len(merged):,} pitches through {merged['game_date'].max()}.")

    # 4. Score all 2026 pitches (models are fast)
    print("  Scoring 2026 pitches…", flush=True)
    scored = score_dataframe(merged)

    # 5. Export platoon_grades for 2026
    names = load_names(merged)
    print("  Building platoon rows…", flush=True)
    platoon_rows = build_platoon_rows(scored, names)
    print(f"  {len(platoon_rows)} rows (≥{MIN_PITCHES} pitches per cell).")

    if not platoon_rows:
        print("  No rows meet the minimum threshold — skipping upsert.")
        return

    # 6. Push to Supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    upsert_platoon(supabase, platoon_rows)
    print("Done.")


if __name__ == "__main__":
    main()
