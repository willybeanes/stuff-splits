"""
Step 1: Pull raw Statcast pitch data for 2023-2026.
Caches monthly chunks as parquet, then combines into one file.
"""

import os
import pandas as pd
import pybaseball
from datetime import date

pybaseball.cache.enable()

RAW_DIR     = "data/raw"
COMBINED    = "data/statcast_2023_2026.parquet"
NAMES_PATH  = "data/player_names.csv"

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

KEEP_COLS = [
    "pitcher", "player_name", "game_date", "game_year",
    "pitch_type", "p_throws", "stand",
    "release_speed", "effective_speed", "release_spin_rate", "release_extension",
    "release_pos_x", "release_pos_z", "release_pos_y",
    "pfx_x", "pfx_z",
    "spin_axis",          # 0–360° spin direction — captures spin efficiency & movement direction
    "arm_angle",          # official Statcast arm angle (degrees, 0=submarine, 90=over-top)
    "api_break_z_with_gravity",  # total vertical drop at plate (for gravity-adjusted IVB)
    "api_break_x_arm",    # horizontal break from arm-side perspective
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

# Month ranges to pull
SEASONS = {
    2023: [
        ("2023-03-30", "2023-04-30"),
        ("2023-05-01", "2023-05-31"),
        ("2023-06-01", "2023-06-30"),
        ("2023-07-01", "2023-07-31"),
        ("2023-08-01", "2023-08-31"),
        ("2023-09-01", "2023-10-01"),
    ],
    2024: [
        ("2024-03-20", "2024-04-30"),
        ("2024-05-01", "2024-05-31"),
        ("2024-06-01", "2024-06-30"),
        ("2024-07-01", "2024-07-31"),
        ("2024-08-01", "2024-08-31"),
        ("2024-09-01", "2024-09-29"),
    ],
    2025: [
        ("2025-03-27", "2025-04-30"),
        ("2025-05-01", "2025-05-31"),
        ("2025-06-01", "2025-06-30"),
        ("2025-07-01", "2025-07-31"),
        ("2025-08-01", "2025-08-31"),
        ("2025-09-01", "2025-09-30"),
        ("2025-10-01", "2025-10-05"),
    ],
    2026: [
        ("2026-03-26", "2026-04-30"),
        ("2026-05-01", "2026-05-31"),
        ("2026-06-01", "2026-06-22"),
    ],
}

def pull_chunk(start: str, end: str, season: int) -> pd.DataFrame | None:
    chunk_path = os.path.join(RAW_DIR, f"statcast_{start}_{end}.parquet")
    if os.path.exists(chunk_path):
        print(f"  [cached] {start} → {end}")
        return pd.read_parquet(chunk_path)

    print(f"  Pulling {start} → {end}...")
    try:
        df = pybaseball.statcast(start_dt=start, end_dt=end, verbose=False)
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

    if df is None or df.empty:
        print(f"  No data returned.")
        return None

    # Keep only columns that exist
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols].copy()
    df["game_year"] = season
    df.to_parquet(chunk_path, index=False)
    print(f"  Saved {len(df):,} pitches → {chunk_path}")
    return df


def build_player_names(df: pd.DataFrame) -> None:
    """Build pitcher name table from the data itself, supplement catchers via MLB API."""
    import requests

    records = []

    # Pitchers — we have names in the data
    pitcher_names = (
        df[["pitcher", "player_name"]]
        .dropna()
        .drop_duplicates("pitcher")
        .rename(columns={"pitcher": "mlb_id", "player_name": "name"})
    )
    pitcher_names["mlb_id"] = pitcher_names["mlb_id"].astype(int)
    records.append(pitcher_names)

    # Catchers — need to look up by fielder_2 IDs
    catcher_ids = df["fielder_2"].dropna().astype(int).unique()
    known_ids   = set(pitcher_names["mlb_id"].tolist())
    unknown_ids = [i for i in catcher_ids if i not in known_ids]

    print(f"  Looking up {len(unknown_ids)} catcher names from MLB API...")
    catcher_rows = []
    for mlb_id in unknown_ids:
        try:
            url = f"https://statsapi.mlb.com/api/v1/people/{mlb_id}?fields=people,id,fullName"
            r = requests.get(url, timeout=5)
            people = r.json().get("people", [])
            if people:
                catcher_rows.append({"mlb_id": mlb_id, "name": people[0]["fullName"]})
        except Exception:
            pass

    if catcher_rows:
        records.append(pd.DataFrame(catcher_rows))

    all_names = pd.concat(records, ignore_index=True).drop_duplicates("mlb_id")
    all_names.to_csv(NAMES_PATH, index=False)
    print(f"  Saved {len(all_names):,} player names → {NAMES_PATH}")


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Check if all chunks already exist (skip pull if so)
    all_chunks_cached = all(
        os.path.exists(os.path.join(RAW_DIR, f"statcast_{s}_{e}.parquet"))
        for ranges in SEASONS.values() for s, e in ranges
    )
    if os.path.exists(COMBINED) and all_chunks_cached:
        print(f"Combined file already exists: {COMBINED}")
        print("Delete it to re-run. Loading for name lookup...")
        df_all = pd.read_parquet(COMBINED)
    else:
        chunks = []
        for season, ranges in SEASONS.items():
            print(f"\n=== {season} ===")
            for start, end in ranges:
                chunk = pull_chunk(start, end, season)
                if chunk is not None:
                    chunks.append(chunk)

        if not chunks:
            raise RuntimeError("No data pulled.")

        df_all = pd.concat(chunks, ignore_index=True)

        # Basic cleanup
        df_all["game_date"] = pd.to_datetime(df_all["game_date"])
        df_all["fielder_2"] = pd.to_numeric(df_all["fielder_2"], errors="coerce")

        # Drop pitches with no pitch type
        df_all = df_all[df_all["pitch_type"].notna() & (df_all["pitch_type"] != "")]

        df_all.to_parquet(COMBINED, index=False)
        print(f"\nCombined: {len(df_all):,} pitches → {COMBINED}")

    if not os.path.exists(NAMES_PATH):
        print("\nBuilding player name lookup...")
        build_player_names(df_all)

    print("\nDone. Pitch type breakdown:")
    print(df_all.groupby(["game_year", "pitch_type"]).size().unstack(fill_value=0).to_string())
