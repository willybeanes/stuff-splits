"""
Step 5: Calibrate our Stuff+/Location+/Pitching+ to match Fangraphs' scale.

Uses 2023+2024+2025 FG data (via fg-proxy) for a much larger calibration
sample (~900 pitcher-pitch_type pairs vs ~300 from 2025 alone), giving
significantly better per-pitch-type R² and lower MAE.

Run after 3_score_pitches.py (first pass, pre-calibration).
"""

import json
import os
import urllib.request
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from utils import load_player_names, load_scaling, save_scaling, PITCH_TYPES

SCORED       = "data/scored_pitches.parquet"
CALIB_PATH   = "models/calibration_params.json"
CALIB_SEASONS = [2023, 2024, 2025]   # years of FG data to calibrate against
MIN_PITCHES   = 100   # per pitcher-season for pitcher-level calibration
MIN_PT_ROWS   = 10    # per pitch-type match for per-type calibration (higher threshold with more data)

# Fangraphs pitch-type key mapping (their suffix → our pitch_type code)
FG_PT_MAP = {
    "FF": "FF", "SI": "SI", "FC": "FC", "SL": "SL",
    "ST": "ST", "CH": "CH", "CU": "CU", "KC": "KC",
    "FS": "FS", "SV": "SV",
}


# ── 1. Fetch Fangraphs leaderboard (via fg-proxy) ───────────────────────────

FG_PROXY = "https://fg-proxy.vercel.app/api/fangraphs"

def fetch_fangraphs_season(season: int, qual: int = 0) -> pd.DataFrame:
    qs = (
        f"pos=all&stats=pit&lg=all&qual={qual}"
        f"&season={season}&season1={season}"
        f"&month=0&type=36&pageitems=2000&pagenum=1"
    )
    url = f"{FG_PROXY}?{qs}"
    print(f"  Fetching {season} via fg-proxy...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    df = pd.DataFrame(data["data"])
    df["fg_season"] = season
    print(f"    {len(df)} pitchers")
    return df


def fetch_fangraphs(seasons: list[int] = CALIB_SEASONS, qual: int = 0) -> pd.DataFrame:
    print(f"Fetching Fangraphs data for {seasons}...")
    frames = [fetch_fangraphs_season(s, qual) for s in seasons]
    return pd.concat(frames, ignore_index=True)


def parse_fangraphs(df: pd.DataFrame) -> pd.DataFrame:
    """Extract MLBAM ID, season, and Stuff+/Loc+/Pitching+ columns (overall + per type)."""
    keep = ["xMLBAMID", "fg_season", "sp_stuff", "sp_location", "sp_pitching"]
    for pt in FG_PT_MAP:
        for metric in ["s", "l", "p"]:
            col = f"sp_{metric}_{pt}"
            if col in df.columns:
                keep.append(col)
    keep = [c for c in keep if c in df.columns]
    out = df[keep].copy()
    out = out.rename(columns={"xMLBAMID": "mlb_id", "fg_season": "season"})
    out["mlb_id"] = pd.to_numeric(out["mlb_id"], errors="coerce")
    out = out.dropna(subset=["mlb_id", "sp_stuff"])
    out["mlb_id"] = out["mlb_id"].astype(int)
    return out


# ── 2. Compute our pitcher-level grades from scored_pitches ─────────────────

def compute_our_grades(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        pitcher_grades: pitcher × season level grades (for joining to multi-year FG data)
        pt_grades:      pitcher × season × pitch_type level grades
    """
    train = scored[scored["game_year"].isin(CALIB_SEASONS)].copy()
    train = train.dropna(subset=["stuff_plus", "location_plus", "pitching_plus"])

    def wavg(grp):
        return pd.Series({
            "our_stuff":    grp["stuff_plus"].mean(),
            "our_loc":      grp["location_plus"].mean(),
            "our_pitching": grp["pitching_plus"].mean(),
            "n_pitches":    len(grp),
        })

    # Pitcher × season (so each year is a separate calibration point)
    pitcher = (
        train.groupby(["pitcher", "game_year"])
        .apply(wavg, include_groups=False)
        .reset_index()
        .rename(columns={"pitcher": "mlb_id", "game_year": "season"})
    )
    pitcher = pitcher[pitcher["n_pitches"] >= MIN_PITCHES]

    # Pitcher × season × pitch_type
    pt = (
        train.groupby(["pitcher", "game_year", "pitch_type"])
        .apply(wavg, include_groups=False)
        .reset_index()
        .rename(columns={"pitcher": "mlb_id", "game_year": "season"})
    )
    pt = pt[pt["n_pitches"] >= MIN_PITCHES // 5]

    return pitcher, pt


# ── 3. Fit calibration ───────────────────────────────────────────────────────

def fit_linear(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Fit y = a*x + b. Returns (a, b, r2)."""
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 10:
        return 1.0, 0.0, float("nan")
    reg = LinearRegression().fit(x.reshape(-1, 1), y)
    r2  = reg.score(x.reshape(-1, 1), y)
    return float(reg.coef_[0]), float(reg.intercept_), float(r2)


def calibrate(fg: pd.DataFrame, ours_pitcher: pd.DataFrame, ours_pt: pd.DataFrame):
    """
    Fits calibration at pitcher level (overall) and pitch-type level.
    Returns a dict of calibration params.
    """
    merged = fg.merge(ours_pitcher, on=["mlb_id", "season"], how="inner")
    print(f"\n  Pitcher-season matches: {len(merged)} across {merged['season'].nunique()} seasons")

    calib = {}

    for our_col, fg_col, label in [
        ("our_stuff",    "sp_stuff",    "Stuff+"),
        ("our_loc",      "sp_location", "Location+"),
        ("our_pitching", "sp_pitching", "Pitching+"),
    ]:
        x = merged[our_col].values
        y = merged[fg_col].values
        a, b, r2 = fit_linear(x, y)
        calib[f"overall_{our_col.split('_')[1]}"] = {"a": a, "b": b, "r2": r2}
        print(f"  {label:12s}  a={a:.4f}  b={b:+.2f}  R²={r2:.3f}  "
              f"(our mean={x.mean():.1f} → fg mean={y.mean():.1f})")

    # Per pitch-type calibration
    print("\n  Pitch-type level calibration:")
    pt_calib = {}
    for fg_pt, our_pt in FG_PT_MAP.items():
        for our_col, fg_suffix, label in [
            ("our_stuff",    "s", "Stuff+"),
            ("our_loc",      "l", "Loc+"),
            ("our_pitching", "p", "Pitching+"),
        ]:
            fg_col = f"sp_{fg_suffix}_{fg_pt}"
            if fg_col not in fg.columns:
                continue
            pt_subset = ours_pt[ours_pt["pitch_type"] == our_pt]
            merged_pt = fg[["mlb_id", "season", fg_col]].dropna().merge(
                pt_subset[["mlb_id", "season", our_col]], on=["mlb_id", "season"], how="inner"
            )
            if len(merged_pt) < MIN_PT_ROWS:
                continue
            a, b, r2 = fit_linear(merged_pt[our_col].values, merged_pt[fg_col].values)
            key = f"{our_pt}_{our_col.split('_')[1]}"
            pt_calib[key] = {"a": a, "b": b, "r2": r2, "n": len(merged_pt)}
            print(f"    {our_pt} {label:10s}  n={len(merged_pt):3d}  "
                  f"a={a:.4f}  b={b:+.2f}  R²={r2:.3f}")

    calib["pitch_type"] = pt_calib
    return calib, merged


# ── 4. Bake calibration into scaling_params ──────────────────────────────────

def apply_calibration_to_scaling(calib: dict) -> None:
    """
    Adjust scaling_params.json so our to_plus() naturally outputs FG-calibrated
    values. For each pitch type, if a per-type calibration exists use it,
    otherwise fall back to the overall calibration.

    to_plus() = 100 - ((raw - mean) / scale * 100)

    After applying linear transform y_fg = a * y_ours + b:
      y_fg = a * (100 - (raw - mean)/scale * 100) + b
           = (100*a + b) - a*(raw - mean)/scale * 100

    This is equivalent to new to_plus() with:
      new_mean  = mean  (unchanged — keeps the same inflection point)
      new_scale = scale / a
      new_offset = (100*a + b) - 100   (shift so average maps correctly)

    We store new_scale and an additive offset applied after to_plus().
    """
    scaling = load_scaling()
    pt_calib = calib.get("pitch_type", {})

    for pt, params in scaling.items():
        for metric, metric_word in [("stuff", "stuff"), ("location", "loc")]:
            # Calibration keys are "{PT}_stuff" / "{PT}_loc" (not "{PT}_s" / "{PT}_l")
            pt_key = f"{pt}_{metric_word}"
            c = pt_calib.get(pt_key)
            if c is None:
                # Fall back to overall (don't discard low-R² per-type fits)
                overall_key = f"overall_{metric_word}" if metric_word in ("stuff", "loc") else f"overall_{metric_word}"
                c = calib.get(f"overall_{metric_word}", calib.get("overall_stuff"))
            if c is None:
                continue
            a, b = c["a"], c["b"]
            # Adjust scale
            old_scale = params[f"{metric}_scale"]
            params[f"{metric}_scale"] = old_scale / a
            # Store offset (applied as post-hoc shift in scoring)
            params[f"{metric}_offset"] = (100 * a + b) - 100

    save_scaling(scaling)
    print("\n  Updated scaling_params.json with calibration offsets.")


# ── 5. Diagnostic plot ────────────────────────────────────────────────────────

def plot_calibration(merged: pd.DataFrame, outpath: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(14, 5))
        fig.patch.set_facecolor("#0d1117")

        pairs = [
            ("our_stuff",    "sp_stuff",    "Stuff+"),
            ("our_loc",      "sp_location", "Location+"),
            ("our_pitching", "sp_pitching", "Pitching+"),
        ]

        for ax, (our_col, fg_col, label) in zip(axes, pairs):
            x = merged[our_col].values
            y = merged[fg_col].values
            mask = np.isfinite(x) & np.isfinite(y)
            x, y = x[mask], y[mask]

            ax.set_facecolor("#0d1117")
            ax.scatter(x, y, c="#4A90D9", s=18, alpha=0.6, zorder=3)

            # Fit line
            a, b, r2 = fit_linear(x, y)
            xl = np.linspace(x.min(), x.max(), 100)
            ax.plot(xl, a*xl + b, c="#E8C53A", lw=1.5, zorder=4)

            # Identity line
            lo, hi = min(x.min(), y.min()), max(x.max(), y.max())
            ax.plot([lo, hi], [lo, hi], c="#555", lw=1, ls="--", zorder=2)

            ax.set_title(label, color="white", fontsize=11, fontweight="bold")
            ax.set_xlabel("Our model", color="#AAAAAA", fontsize=9)
            ax.set_ylabel("Fangraphs", color="#AAAAAA", fontsize=9)
            ax.tick_params(colors="#777")
            for spine in ax.spines.values():
                spine.set_edgecolor("#333")
            ax.text(0.05, 0.95, f"y = {a:.3f}x + {b:+.1f}\nR² = {r2:.3f}  n={len(x)}",
                    transform=ax.transAxes, va="top", color="#CCCCCC",
                    fontsize=8.5, fontfamily="monospace",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#111", alpha=0.8))

        plt.suptitle(f"Our Model vs Fangraphs Stuff+/Location+/Pitching+  ({CALIB_SEASONS}, pitcher-season level)",
                     color="white", fontsize=12, fontweight="bold")
        plt.tight_layout()
        plt.savefig(outpath, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        print(f"  Calibration plot → {outpath}")
    except Exception as e:
        print(f"  (Plot skipped: {e})")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Fetch Fangraphs (multi-year via fg-proxy)
    fg_raw = fetch_fangraphs(seasons=CALIB_SEASONS)
    fg     = parse_fangraphs(fg_raw)
    print(f"  Fangraphs pitcher-seasons with Stuff+: {len(fg)}")

    # Compute our grades
    print("\nLoading scored pitches...")
    scored = pd.read_parquet(SCORED)
    print(f"  {len(scored):,} pitches")

    ours_pitcher, ours_pt = compute_our_grades(scored)
    print(f"  Our pitcher-level grades: {len(ours_pitcher)} pitchers")
    print(f"  Our pitch-type-level grades: {len(ours_pt)} rows")

    # Calibrate
    print("\nFitting calibration...")
    calib, merged = calibrate(fg, ours_pitcher, ours_pt)

    # Save calibration params
    os.makedirs("models", exist_ok=True)
    with open(CALIB_PATH, "w") as f:
        json.dump(calib, f, indent=2)
    print(f"\n  Calibration params → {CALIB_PATH}")

    # Diagnostic plot
    os.makedirs("scripts/cache", exist_ok=True)
    plot_calibration(merged, "scripts/cache/calibration_vs_fangraphs.png")

    # Show top/bottom outliers so we can sanity-check
    names = load_player_names()
    merged["name"] = merged["mlb_id"].map(names)
    merged["stuff_resid"] = merged["sp_stuff"] - merged["our_stuff"]
    print("\n  Biggest our-vs-FG Stuff+ gaps (top 10):")
    top = merged.nlargest(10, "stuff_resid")[["name","our_stuff","sp_stuff","stuff_resid"]]
    print(top.to_string(index=False))
    print("\n  Biggest our-vs-FG Stuff+ gaps (bottom 10):")
    bot = merged.nsmallest(10, "stuff_resid")[["name","our_stuff","sp_stuff","stuff_resid"]]
    print(bot.to_string(index=False))

    print("\nDone. Run 3_score_pitches.py again (or add a re-score step) to apply calibration.")
