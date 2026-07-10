"""
Step 6: Export platoon splits (pitcher × pitch_type × batter_hand) to Supabase.

Outputs two tables:
  platoon_grades         — model grades + outcome rates per pitcher/pitch/hand
  platoon_location_bins  — sparse hex-bin grid for the strike-zone visualizer

Run after 3_score_pitches.py.
Usage:
  python3 6_export_platoon_splits.py              # 2026 only
  python3 6_export_platoon_splits.py --season 2025
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env.local")

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

SCORED       = Path(__file__).parent / "data" / "scored_pitches.parquet"
NAMES_CSV    = Path(__file__).parent / "data" / "player_names.csv"

MIN_PITCHES  = 50    # min per pitcher/pitch_type/stand to include in grades
UPSERT_BATCH = 500

# Bin grid bounds
BIN_X  = np.linspace(-2.0, 2.0, 22)   # 21 bins
BIN_Z  = np.linspace(0.3,  4.7, 22)   # 21 bins


def load_names() -> dict[int, str]:
    if NAMES_CSV.exists():
        df = pd.read_csv(NAMES_CSV)
        return dict(zip(df["mlb_id"].astype(int), df["name"]))
    return {}


def get_outcome(desc: str) -> str:
    d = str(desc).lower()
    if "called_strike" in d:                    return "cs"
    if "swinging_strike" in d or "foul_tip" in d: return "whiff"
    if "foul" in d:                             return "foul"
    if "ball" in d or "blocked_ball" in d:      return "ball"
    if "hit_into_play" in d:                    return "in_play"
    return "other"


def upsert_batch(supabase, table: str, rows: list[dict], conflict: str) -> None:
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = rows[i : i + UPSERT_BATCH]
        supabase.table(table).upsert(chunk, on_conflict=conflict).execute()


def compute_grades(df: pd.DataFrame, season: int, names: dict) -> list[dict]:
    rows = []
    for (pitcher_id, pitch_type, stand), grp in df.groupby(["pitcher", "pitch_type", "stand"]):
        n = len(grp)
        if n < MIN_PITCHES:
            continue

        # Zone/outcome stats
        in_zone = (
            (grp["plate_x"].abs() <= 0.83) &
            (grp["plate_z"] >= 1.5) &
            (grp["plate_z"] <= 3.5)
        )
        called_strike = grp["outcome"] == "cs"
        whiff         = grp["outcome"] == "whiff"

        rows.append({
            "season":       season,
            "pitcher_id":   int(pitcher_id),
            "pitcher_name": names.get(int(pitcher_id), str(pitcher_id)),
            "pitcher_team": None,
            "pitch_type":   pitch_type,
            "stand":        stand,
            "n_pitches":    int(n),
            "stuff_plus":   round(float(grp["stuff_plus"].mean()),   2) if grp["stuff_plus"].notna().any()    else None,
            "loc_plus":     round(float(grp["location_plus"].mean()), 2) if grp["location_plus"].notna().any() else None,
            "pitching_plus":round(float(grp["pitching_plus"].mean()), 2) if grp["pitching_plus"].notna().any() else None,
            "avg_velo":     round(float(grp["release_speed"].mean()), 1) if grp["release_speed"].notna().any() else None,
            "zone_pct":     round(float(in_zone.mean() * 100), 1),
            "whiff_pct":    round(float(whiff.mean() * 100), 1),
            "cs_pct":       round(float(called_strike.mean() * 100), 1),
        })
    return rows


def compute_bins(df: pd.DataFrame, season: int) -> list[dict]:
    rows = []
    df = df.dropna(subset=["plate_x", "plate_z"])
    df["bx"] = np.digitize(df["plate_x"].values, BIN_X) - 1
    df["bz"] = np.digitize(df["plate_z"].values, BIN_Z) - 1
    # Clamp to valid range
    df = df[(df["bx"] >= 0) & (df["bx"] < 21) & (df["bz"] >= 0) & (df["bz"] < 21)]

    for (pitcher_id, pitch_type, stand), grp in df.groupby(["pitcher", "pitch_type", "stand"]):
        if len(grp) < MIN_PITCHES:
            continue
        for (bx, bz), cell in grp.groupby(["bx", "bz"]):
            n = len(cell)
            rows.append({
                "season":        season,
                "pitcher_id":    int(pitcher_id),
                "pitch_type":    pitch_type,
                "stand":         stand,
                "bin_x":         int(bx),
                "bin_z":         int(bz),
                "total_count":   int(n),
                "cs_count":      int((cell["outcome"] == "cs").sum()),
                "whiff_count":   int((cell["outcome"] == "whiff").sum()),
                "ball_count":    int((cell["outcome"] == "ball").sum()),
                "in_play_count": int((cell["outcome"] == "in_play").sum()),
                "foul_count":    int((cell["outcome"] == "foul").sum()),
            })
    return rows


def main(season: int) -> None:
    print(f"Loading scored pitches for season {season}...")
    df_all = pd.read_parquet(SCORED)
    df = df_all[df_all["game_year"] == season].copy()
    print(f"  {len(df):,} pitches")

    names = load_names()
    df["outcome"] = df["description"].apply(get_outcome)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # ── Grades ──────────────────────────────────────────────────────────────
    print("\nComputing platoon grades...")
    grade_rows = compute_grades(df, season, names)
    print(f"  {len(grade_rows)} rows (pitcher × pitch_type × stand)")

    print("  Upserting platoon_grades...")
    upsert_batch(supabase, "platoon_grades", grade_rows,
                 "season,pitcher_id,pitch_type,stand")
    print("  Done.")

    # ── Bins ────────────────────────────────────────────────────────────────
    print("\nComputing location bins...")
    bin_rows = compute_bins(df, season)
    print(f"  {len(bin_rows)} non-zero bins")

    print("  Upserting platoon_location_bins...")
    upsert_batch(supabase, "platoon_location_bins", bin_rows,
                 "season,pitcher_id,pitch_type,stand,bin_x,bin_z")
    print("  Done.")

    print(f"\nAll done — season {season} platoon splits exported to Supabase.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    main(args.season)
