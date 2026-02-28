CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    stadium_number INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    predicted_order TEXT NOT NULL,       -- JSON array e.g. [1,3,2,5,4,6]
    confidence REAL NOT NULL,
    recommended_bets TEXT NOT NULL,      -- JSON array
    analysis TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(race_date, stadium_number, race_number)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    stadium_number INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    actual_order TEXT,                   -- JSON array of boat numbers by finish
    weather_number INTEGER,
    wind INTEGER,
    wind_direction_number INTEGER,
    wave INTEGER,
    temperature REAL,
    water_temperature REAL,
    technique_number INTEGER,
    payouts_json TEXT,                   -- full payouts JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(race_date, stadium_number, race_number)
);

CREATE TABLE IF NOT EXISTS accuracy_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    stadium_number INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    predicted_1st INTEGER NOT NULL,
    actual_1st INTEGER,
    hit_1st INTEGER,                    -- 1 if predicted_1st == actual_1st
    predicted_trifecta TEXT NOT NULL,    -- "1-2-3"
    actual_trifecta TEXT,               -- "3-1-2"
    hit_trifecta INTEGER,               -- 1 if match
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(race_date, stadium_number, race_number)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(race_date);
CREATE INDEX IF NOT EXISTS idx_predictions_lookup ON predictions(race_date, stadium_number, race_number);
CREATE INDEX IF NOT EXISTS idx_results_date ON results(race_date);
CREATE INDEX IF NOT EXISTS idx_results_lookup ON results(race_date, stadium_number, race_number);
CREATE INDEX IF NOT EXISTS idx_accuracy_date ON accuracy_log(race_date);
