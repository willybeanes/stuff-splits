"""
Step 4: Aggregate scored pitches into leaderboard CSVs.
Also produces the article-specific battery × pitch type breakdowns for
Colin Rea, Keider Montero, and Logan Gilbert.
"""

import os
import numpy as np
import pandas as pd

from utils import (
    PITCH_LABELS, MIN_PITCHES_PITCHER, MIN_PITCHES_BATTERY, MIN_PITCHES_CATCHER,
    load_player_names,
)

SCORED   = "data/scored_pitches.parquet"
EXPORTS  = "data/exports"
os.makedirs(EXPORTS, exist_ok=True)

# Article pitcher IDs
ARTICLE_PITCHERS = {
    607067: "Colin Rea",
    672456: "Keider Montero",
    669302: "Logan Gilbert",
}


def agg_grades(group: pd.DataFrame) -> pd.Series:
    """Pitch-count-weighted mean of model grades."""
    n = len(group)
    return pd.Series({
        "n_pitches":    n,
        "stuff_plus":   group["stuff_plus"].mean(),
        "location_plus":group["location_plus"].mean(),
        "pitching_plus":group["pitching_plus"].mean(),
        "avg_velo":     group["release_speed"].mean(),
        "avg_spin":     group["release_spin_rate"].mean(),
        "avg_ivb":      (group["pfx_z"] * 12).mean(),   # pfx_z feet → inches
        "avg_hb":       (group["pfx_x"] * 12).mean(),
    })


if __name__ == "__main__":
    print("Loading scored pitches...")
    df = pd.read_parquet(SCORED)
    print(f"  {len(df):,} pitches")

    player_names = load_player_names()

    def name(mlb_id, col=None):
        if pd.isna(mlb_id):
            return "Unknown"
        mid = int(mlb_id)
        if mid in player_names:
            return player_names[mid]
        # Fall back to player_name column if available
        if col is not None:
            matches = df.loc[df["pitcher"] == mid, "player_name"].dropna()
            if not matches.empty:
                return matches.iloc[0]
        return str(mid)

    df["pitcher_name"] = df["pitcher"].apply(lambda x: name(x, "pitcher"))
    df["catcher_name"] = df["fielder_2"].apply(lambda x: name(x) if pd.notna(x) else "Unknown")
    df["pitch_label"]  = df["pitch_type"].map(PITCH_LABELS).fillna(df["pitch_type"])

    # ── 1. Pitcher × pitch type leaderboard ─────────────────────────────────
    print("\nBuilding pitcher × pitch type leaderboard...")
    grp1 = (
        df.groupby(["pitcher", "pitcher_name", "pitch_type", "pitch_label", "game_year"])
        .apply(agg_grades, include_groups=False)
        .reset_index()
        .rename(columns={"pitcher": "pitcher_id", "game_year": "season"})
    )
    grp1 = grp1[grp1["n_pitches"] >= MIN_PITCHES_PITCHER]
    grp1 = grp1.sort_values(["season", "pitcher_name", "pitch_type"])
    path1 = f"{EXPORTS}/pitcher_pitch_type_leaderboard.csv"
    grp1.to_csv(path1, index=False)
    print(f"  Exported {len(grp1):,} rows → {path1}")

    # ── 2. Battery × pitch type leaderboard ─────────────────────────────────
    print("\nBuilding battery × pitch type leaderboard...")
    df_with_catcher = df[df["fielder_2"].notna()].copy()
    df_with_catcher["catcher_id"] = df_with_catcher["fielder_2"].astype(int)

    grp2 = (
        df_with_catcher.groupby([
            "pitcher", "pitcher_name", "catcher_id", "catcher_name",
            "pitch_type", "pitch_label", "game_year"
        ])
        .apply(agg_grades, include_groups=False)
        .reset_index()
        .rename(columns={"pitcher": "pitcher_id", "game_year": "season"})
    )
    grp2 = grp2[grp2["n_pitches"] >= MIN_PITCHES_BATTERY]
    grp2 = grp2.sort_values(["season", "pitcher_name", "pitch_type", "n_pitches"], ascending=[True, True, True, False])
    path2 = f"{EXPORTS}/battery_splits_leaderboard.csv"
    grp2.to_csv(path2, index=False)
    print(f"  Exported {len(grp2):,} rows → {path2}")

    # ── 3. Catcher × pitch type leaderboard ─────────────────────────────────
    print("\nBuilding catcher × pitch type leaderboard...")
    grp3 = (
        df_with_catcher.groupby(["catcher_id", "catcher_name", "pitch_type", "pitch_label", "game_year"])
        .agg(
            n_pitches    =("pitching_plus", "count"),
            location_plus=("location_plus", "mean"),
            pitching_plus=("pitching_plus", "mean"),
        )
        .reset_index()
        .rename(columns={"game_year": "season"})
    )
    grp3 = grp3[grp3["n_pitches"] >= MIN_PITCHES_CATCHER]
    grp3 = grp3.sort_values(["season", "catcher_name", "pitch_type"])
    path3 = f"{EXPORTS}/catcher_pitch_type_leaderboard.csv"
    grp3.to_csv(path3, index=False)
    print(f"  Exported {len(grp3):,} rows → {path3}")

    # ── 4. ARTICLE: Three pitchers × catcher × pitch type (2026) ────────────
    print("\nBuilding article battery × pitch type breakdown (2026)...")
    df_art = df_with_catcher[
        (df_with_catcher["game_year"] == 2026) &
        (df_with_catcher["pitcher"].isin(ARTICLE_PITCHERS))
    ].copy()

    art = (
        df_art.groupby(["pitcher", "pitcher_name", "catcher_id", "catcher_name", "pitch_type", "pitch_label"])
        .apply(agg_grades, include_groups=False)
        .reset_index()
        .rename(columns={"pitcher": "pitcher_id"})
    )
    art = art[art["n_pitches"] >= 20]  # lower bar for article focus
    art = art.sort_values(["pitcher_name", "catcher_name", "pitch_type"])
    path_art = f"{EXPORTS}/article_battery_pitch_type.csv"
    art.to_csv(path_art, index=False)
    print(f"  Exported {len(art):,} rows → {path_art}")

    # Print article table to console
    print("\n" + "="*90)
    print("ARTICLE: Pitch-type model grades by battery (2026, min 20 pitches)")
    print("="*90)
    for pitcher_id, pitcher_name in ARTICLE_PITCHERS.items():
        sub = art[art["pitcher_id"] == pitcher_id].copy()
        if sub.empty:
            print(f"\n{pitcher_name}: no data")
            continue

        catchers = sub["catcher_name"].unique()
        print(f"\n── {pitcher_name} ──")
        print(f"  {'Pitch Type':<18} {'Catcher':<22} {'N':>5} {'Stuff+':>7} {'Loc+':>7} {'Pitch+':>7} {'Velo':>6} {'Spin':>6} {'IVB':>6} {'HB':>6}")
        print(f"  {'-'*85}")
        for pt in sorted(sub["pitch_type"].unique()):
            pt_rows = sub[sub["pitch_type"] == pt].sort_values("n_pitches", ascending=False)
            for _, row in pt_rows.iterrows():
                def f(v, d=1): return f"{v:.{d}f}" if pd.notna(v) else " —"
                print(f"  {row['pitch_label']:<18} {row['catcher_name']:<22} {int(row['n_pitches']):>5} "
                      f"{f(row['stuff_plus']):>7} {f(row['location_plus']):>7} {f(row['pitching_plus']):>7} "
                      f"{f(row['avg_velo']):>6} {f(row['avg_spin'],0):>6} {f(row['avg_ivb']):>6} {f(row['avg_hb']):>6}")

    print("\n\nDone. All exports in data/exports/")
