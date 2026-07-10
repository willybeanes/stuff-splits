-- Platoon splits: pitcher × pitch_type × batter_hand model grades
CREATE TABLE IF NOT EXISTS platoon_grades (
  id            BIGSERIAL PRIMARY KEY,
  season        INTEGER NOT NULL,
  pitcher_id    INTEGER NOT NULL,
  pitcher_name  TEXT    NOT NULL,
  pitcher_team  TEXT,
  pitch_type    TEXT    NOT NULL,   -- FF, SI, SL, CH, CU, etc.
  stand         CHAR(1) NOT NULL,   -- 'L' or 'R'
  n_pitches     INTEGER NOT NULL,
  stuff_plus    NUMERIC(7,2),
  loc_plus      NUMERIC(7,2),
  pitching_plus NUMERIC(7,2),
  avg_velo      NUMERIC(5,1),
  zone_pct      NUMERIC(5,1),       -- %
  whiff_pct     NUMERIC(5,1),       -- %
  cs_pct        NUMERIC(5,1),       -- called strike %
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(season, pitcher_id, pitch_type, stand)
);

CREATE INDEX IF NOT EXISTS idx_pg_season     ON platoon_grades(season);
CREATE INDEX IF NOT EXISTS idx_pg_pitcher    ON platoon_grades(pitcher_id);
CREATE INDEX IF NOT EXISTS idx_pg_pitch_type ON platoon_grades(pitch_type);
CREATE INDEX IF NOT EXISTS idx_pg_stand      ON platoon_grades(stand);

-- Hex-bin pitch location data for the visualizer
-- Grid: 21 cols (X: -2.0→2.0) × 21 rows (Z: 0.3→4.7)
-- Only non-zero bins are stored (sparse).
CREATE TABLE IF NOT EXISTS platoon_location_bins (
  id           BIGSERIAL PRIMARY KEY,
  season       INTEGER  NOT NULL,
  pitcher_id   INTEGER  NOT NULL,
  pitch_type   TEXT     NOT NULL,
  stand        CHAR(1)  NOT NULL,
  bin_x        SMALLINT NOT NULL,   -- 0–20 (col index)
  bin_z        SMALLINT NOT NULL,   -- 0–20 (row index)
  total_count  SMALLINT NOT NULL DEFAULT 0,
  cs_count     SMALLINT NOT NULL DEFAULT 0,   -- called strike
  whiff_count  SMALLINT NOT NULL DEFAULT 0,   -- swinging strike / foul tip
  ball_count   SMALLINT NOT NULL DEFAULT 0,
  in_play_count SMALLINT NOT NULL DEFAULT 0,
  foul_count   SMALLINT NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(season, pitcher_id, pitch_type, stand, bin_x, bin_z)
);

CREATE INDEX IF NOT EXISTS idx_plb_lookup
  ON platoon_location_bins(season, pitcher_id, pitch_type);
