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

-- ── Phase 2.5: odds cache ────────────────────────────────

CREATE TABLE IF NOT EXISTS race_odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    stadium_number INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    odds_json TEXT NOT NULL,             -- full OddsData as JSON
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(race_date, stadium_number, race_number)
);

-- ── Phase 2: 売る仕組み ──────────────────────────────────

CREATE TABLE IF NOT EXISTS race_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    stadium_number INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    grade TEXT NOT NULL,             -- 'S', 'A', 'B', 'C'
    top1_prob REAL NOT NULL,
    top2_prob REAL NOT NULL,
    top3_prob REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(race_date, stadium_number, race_number)
);

CREATE TABLE IF NOT EXISTS virtual_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date TEXT NOT NULL,
    stadium_number INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    bet_type TEXT NOT NULL,          -- "3連単", "2連単" etc.
    combination TEXT NOT NULL,      -- "1-3-2", "1=2" etc.
    bet_amount INTEGER NOT NULL DEFAULT 1000,
    payout INTEGER NOT NULL DEFAULT 0,
    is_hit INTEGER,                 -- NULL=未判定, 0=不的中, 1=的中
    grade TEXT NOT NULL DEFAULT '',  -- ベット時の推奨度
    model_prob REAL,                -- モデル推定確率
    market_odds REAL,               -- 市場オッズ
    ev REAL,                        -- 期待値 (prob × odds - 1)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tweet_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_type TEXT NOT NULL,        -- 'morning', 'hit', 'daily'
    race_date TEXT NOT NULL,
    stadium_number INTEGER,
    race_number INTEGER,
    tweet_id TEXT,                   -- X API返却ID
    tweet_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(race_date);
CREATE INDEX IF NOT EXISTS idx_predictions_lookup ON predictions(race_date, stadium_number, race_number);
CREATE INDEX IF NOT EXISTS idx_results_date ON results(race_date);
CREATE INDEX IF NOT EXISTS idx_results_lookup ON results(race_date, stadium_number, race_number);
CREATE INDEX IF NOT EXISTS idx_accuracy_date ON accuracy_log(race_date);
CREATE INDEX IF NOT EXISTS idx_race_grades_date ON race_grades(race_date);
CREATE INDEX IF NOT EXISTS idx_virtual_bets_date ON virtual_bets(race_date);
CREATE INDEX IF NOT EXISTS idx_virtual_bets_unchecked ON virtual_bets(is_hit) WHERE is_hit IS NULL;
CREATE INDEX IF NOT EXISTS idx_tweet_log_date ON tweet_log(race_date, tweet_type);
CREATE INDEX IF NOT EXISTS idx_race_odds_date ON race_odds(race_date);
CREATE INDEX IF NOT EXISTS idx_race_odds_lookup ON race_odds(race_date, stadium_number, race_number);
