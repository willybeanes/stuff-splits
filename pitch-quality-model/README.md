# Pitch Quality Model

Builds Stuff+ and Location+ style metrics for MLB pitchers from 2025–2026 Statcast data, broken down by **pitch type** and **catcher**. Powers the Battery Splits leaderboard.

## Setup

```bash
cd pitch-quality-model
pip install -r requirements.txt
```

## Run in order

### Step 1 — Pull data
```bash
python 1_pull_data.py
```
Pulls all 2025 and 2026 Statcast data via pybaseball (monthly chunks, cached as parquet). Builds a player name lookup from pitcher names in the data + MLB Stats API for catcher IDs. Outputs:
- `data/raw/statcast_YYYY-MM-DD_YYYY-MM-DD.parquet` (one per month)
- `data/statcast_2025_2026.parquet` (combined)
- `data/player_names.csv`

### Step 2 — Train models
```bash
python 2_build_model.py
```
Trains two XGBoost models per pitch type (FF, SI, FC, SL, ST, CH, CU, KC) using 2025 data only:
- **Stuff model**: predicts run value from physical pitch characteristics only (velo, spin, movement, release)
- **Location model**: same features + plate location (adds framing/command signal)

Outputs:
- `models/stuff_{PITCH_TYPE}.pkl`
- `models/location_{PITCH_TYPE}.pkl`
- `models/scaling_params.json` (mean/scale per pitch type for normalization)

### Step 3 — Score all pitches
```bash
python 3_score_pitches.py
```
Applies trained models to all 2025+2026 pitches. Outputs:
- `data/scored_pitches.parquet` — full pitch-level data with `stuff_plus`, `location_plus`, `pitching_plus` columns

### Step 4 — Export leaderboards
```bash
python 4_export_leaderboards.py
```
Aggregates into CSV exports ready for Supabase import. Outputs:

| File | Description |
|---|---|
| `pitcher_pitch_type_leaderboard.csv` | Pitcher × pitch type × season (min 100 pitches) |
| `battery_splits_leaderboard.csv` | Pitcher × catcher × pitch type × season (min 50 pitches) |
| `catcher_pitch_type_leaderboard.csv` | Catcher × pitch type × season (min 100 pitches received) |
| `article_battery_pitch_type.csv` | Colin Rea, Keider Montero, Logan Gilbert — all catchers × pitch types (min 20 pitches) |

Also prints the article table to console.

## How it works

**Target variable**: `delta_run_exp` (Statcast run value per pitch). If unavailable, falls back to a wOBA-based proxy.

**Scaling**: `plus_metric = 100 − ((raw_prediction − league_mean) / league_std × 100)`
- 100 = league average for that pitch type
- Higher = better for the pitcher
- Stuff+ and Location+ averaged → Pitching+

**Key design choices**:
- Separate model per pitch type (fastball movement means something different than slider movement)
- Train on 2025 only → score 2026 as out-of-sample
- Catcher ID (`fielder_2`) is kept in the scored data — the battery splits are a groupby at export time, not baked into the model
- Location model minus Stuff model = the catcher's framing contribution at the pitch level

## Importing to Supabase

Each CSV has clean column names and is directly importable via the Supabase dashboard Table Editor → Import CSV, or via:

```bash
psql $DATABASE_URL -c "\copy battery_splits_leaderboard FROM 'data/exports/battery_splits_leaderboard.csv' CSV HEADER"
```
