"""Shared helpers for the pitch quality model pipeline."""

import json
import os
import pandas as pd
import numpy as np

# ── Pitch type config ───────────────────────────────────────────────────────

PITCH_TYPES = ["FF", "SI", "FC", "SL", "ST", "CH", "CU", "KC", "FS", "SV"]

PITCH_LABELS = {
    "FF": "4-Seam Fastball",
    "SI": "Sinker",
    "FC": "Cutter",
    "SL": "Slider",
    "ST": "Sweeper",
    "CH": "Changeup",
    "CU": "Curveball",
    "KC": "Knuckle-Curve",
    "FS": "Splitter",
    "KN": "Knuckleball",
    "FO": "Forkball",
    "SC": "Screwball",
    "CS": "Slow Curve",
    "EP": "Eephus",
    "PO": "Pitchout",
    "UN": "Unknown",
}

STUFF_FEATURES = [
    "release_speed",
    "effective_speed",
    "release_spin_rate",
    "release_extension",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "p_throws_enc",
    "stand_enc",
    # derived
    "velo_diff",        # pitch speed minus pitcher's fastball velo (key for offspeed)
    "spin_per_velo",    # spin_rate / release_speed — proxy for active spin efficiency
    "break_total",      # sqrt(pfx_x² + pfx_z²) — total movement magnitude
    "break_angle",      # atan2(pfx_z, pfx_x) — movement direction
    "arm_slot_angle",   # atan2(release_pos_z, |release_pos_x|) — release-point arm slot proxy
    # Statcast-native features (added after research into FG model inputs)
    "spin_axis_sin",    # sin(spin_axis_rad) — circular encoding avoids 0°/360° discontinuity
    "spin_axis_cos",    # cos(spin_axis_rad) — paired with sin for full spin direction
    "arm_angle",        # official Statcast arm angle (degrees; 0=submarine, 90=over-top)
    "is_starter",       # 1=starter, 0=reliever — corrects max-effort velocity inflation in relievers
]

LOCATION_FEATURES = STUFF_FEATURES + [
    "plate_x",
    "plate_z",
    "plate_x_rel",
    "in_zone",
    "zone_x_from_center",
    "zone_z_from_center",
    "sz_height",
]

MIN_PITCHES_MODEL   = 500   # min pitches per type to train a model
MIN_PITCHES_PITCHER = 100   # min pitches per pitcher/type for leaderboard
MIN_PITCHES_BATTERY = 50    # min pitches per battery/type for battery leaderboard
MIN_PITCHES_CATCHER = 100   # min pitches per catcher/type for catcher leaderboard


# ── Player name lookup ──────────────────────────────────────────────────────

_player_cache: dict[int, str] = {}

def load_player_names(path: str = "data/player_names.csv") -> dict[int, str]:
    global _player_cache
    if _player_cache:
        return _player_cache
    if os.path.exists(path):
        df = pd.read_csv(path)
        _player_cache = dict(zip(df["mlb_id"].astype(int), df["name"]))
    return _player_cache

def player_name(mlb_id: int, fallback: str = "") -> str:
    names = load_player_names()
    return names.get(int(mlb_id), fallback or str(mlb_id))


# ── Feature engineering ─────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["p_throws_enc"] = (df["p_throws"] == "R").astype(int)
    df["stand_enc"]    = (df["stand"]    == "R").astype(int)

    # Plate location relative to batter handedness
    df["plate_x_rel"] = np.where(
        df["stand"] == "L", -df["plate_x"], df["plate_x"]
    )

    sz_mid_z = (df["sz_top"] + df["sz_bot"]) / 2
    df["zone_x_from_center"] = df["plate_x"]
    df["zone_z_from_center"] = df["plate_z"] - sz_mid_z
    df["sz_height"]           = df["sz_top"] - df["sz_bot"]

    df["in_zone"] = (
        (df["plate_x"].abs() <= 0.83) &
        (df["plate_z"] >= df["sz_bot"]) &
        (df["plate_z"] <= df["sz_top"])
    ).fillna(False).astype(int)

    # ── Velocity differential vs pitcher's own fastball ──────────────────────
    # Per-pitcher mean velocity of FF/SI pitches. Falls back to overall mean.
    fb_mask = df["pitch_type"].isin(["FF", "SI"])
    fb_velo  = (
        df[fb_mask]
        .groupby("pitcher")["release_speed"]
        .mean()
        .rename("fb_velo")
    )
    df = df.join(fb_velo, on="pitcher")
    # Where pitcher has no FF/SI (e.g. pure reliever), use their overall mean
    pitcher_mean = df.groupby("pitcher")["release_speed"].transform("mean")
    df["fb_velo"] = df["fb_velo"].fillna(pitcher_mean)
    df["velo_diff"] = df["release_speed"] - df["fb_velo"]

    # ── Spin efficiency proxy ─────────────────────────────────────────────────
    df["spin_per_velo"] = df["release_spin_rate"] / df["release_speed"].replace(0, np.nan)

    # ── Movement features ─────────────────────────────────────────────────────
    df["break_total"] = np.sqrt(df["pfx_x"] ** 2 + df["pfx_z"] ** 2)
    df["break_angle"] = np.arctan2(df["pfx_z"], df["pfx_x"])

    # ── Arm slot angle (release-point proxy, kept as fallback) ───────────────
    df["arm_slot_angle"] = np.arctan2(
        df["release_pos_z"],
        df["release_pos_x"].abs()
    )

    # ── Spin axis — circular encoding (avoids 0°/360° discontinuity) ─────────
    if "spin_axis" in df.columns:
        spin_rad = np.deg2rad(df["spin_axis"].astype(float))
        df["spin_axis_sin"] = np.sin(spin_rad)
        df["spin_axis_cos"] = np.cos(spin_rad)
    else:
        df["spin_axis_sin"] = np.nan
        df["spin_axis_cos"] = np.nan

    # ── Arm angle — use Statcast official if present ──────────────────────────
    if "arm_angle" not in df.columns:
        df["arm_angle"] = np.rad2deg(df["arm_slot_angle"])

    # ── Starter/reliever flag ─────────────────────────────────────────────────
    # Per-pitcher-season: fraction of game appearances entered in inning 1.
    # Starters almost always enter in inning 1; relievers rarely do.
    if "game_pk" in df.columns and "inning" in df.columns:
        entry_inning = (
            df.groupby(["pitcher", "game_pk"])["inning"]
            .min()
            .rename("entry_inning")
        )
        appearance = df[["pitcher", "game_pk", "game_year"]].drop_duplicates()
        appearance = appearance.join(entry_inning, on=["pitcher", "game_pk"])
        pct_start = (
            appearance.groupby(["pitcher", "game_year"])
            .apply(lambda g: (g["entry_inning"] == 1).mean(), include_groups=False)
            .rename("pct_starts")
        )
        df = df.join(
            pct_start.reset_index().set_index(["pitcher", "game_year"])["pct_starts"],
            on=["pitcher", "game_year"],
        )
        df["is_starter"] = (df["pct_starts"] >= 0.5).astype(float)
        df = df.drop(columns=["pct_starts"])
    else:
        df["is_starter"] = np.nan

    return df


# ── Scaling helpers ─────────────────────────────────────────────────────────

SCALING_PATH     = "models/scaling_params.json"
CALIBRATION_PATH = "models/calibration_params.json"

def load_scaling() -> dict:
    if os.path.exists(SCALING_PATH):
        with open(SCALING_PATH) as f:
            return json.load(f)
    return {}

def save_scaling(params: dict) -> None:
    os.makedirs("models", exist_ok=True)
    with open(SCALING_PATH, "w") as f:
        json.dump(params, f, indent=2)

def load_calibration() -> dict:
    if os.path.exists(CALIBRATION_PATH):
        with open(CALIBRATION_PATH) as f:
            return json.load(f)
    return {}

def apply_calibration(
    values: np.ndarray,
    pitch_type: str,
    metric: str,       # "s" = stuff, "l" = location
    calib: dict,
) -> np.ndarray:
    """Apply linear y_fg = a*y_ours + b. Falls back to overall if no per-type fit."""
    if not calib:
        return values
    # Calibration params are keyed as "{PT}_stuff" / "{PT}_loc", not "{PT}_s" / "{PT}_l"
    metric_word = "stuff" if metric == "s" else "loc"
    pt_key = f"{pitch_type}_{metric_word}"
    c = calib.get("pitch_type", {}).get(pt_key)
    # Only fall back to overall if no per-type entry at all (don't discard low-R² fits)
    if c is None:
        overall_key = "overall_stuff" if metric == "s" else "overall_loc"
        c = calib.get(overall_key)
    if c is None:
        return values
    return values * c["a"] + c["b"]

def to_plus(raw_preds: np.ndarray, mean_rv: float, scale: float) -> np.ndarray:
    """
    Convert raw run-value predictions to a +/- metric.
    Lower run value allowed = better for pitcher → inverted so higher = better.
    100 = league average for that pitch type.
    scale ≈ std of league predictions, calibrated so 1 SD ≈ 15 pts.
    """
    return 100.0 - ((raw_preds - mean_rv) / scale * 100.0)


# ── Run value fallback ──────────────────────────────────────────────────────

# Linear weights (2024 calibration, close enough)
LINEAR_WEIGHTS = {
    "home_run":       1.376,
    "triple":         1.051,
    "double":         0.764,
    "single":         0.475,
    "walk":           0.311,
    "hit_by_pitch":   0.340,
    "sac_fly":        0.000,
    "field_error":    0.475,
}

def compute_run_value_fallback(df: pd.DataFrame) -> pd.Series:
    """
    Approximate run value per pitch from woba columns when delta_run_exp is absent.
    This is a rough proxy: woba_value * woba_weight, zeroed for non-events.
    """
    rv = pd.Series(0.0, index=df.index)
    for event, weight in LINEAR_WEIGHTS.items():
        mask = df["events"] == event
        rv[mask] = weight
    # Strikes and balls via description
    rv[df["description"].str.contains("strike", case=False, na=False)] -= 0.05
    rv[df["description"].str.contains("ball",   case=False, na=False)] += 0.05
    return rv
