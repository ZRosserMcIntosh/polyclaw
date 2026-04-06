-- ============================================================================
-- PolyClaw — Supabase schema migration
-- ============================================================================
-- All tables prefixed with `polyclaw_` to share the database cleanly
-- with other projects (Redentor Tec, etc.)
--
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- ============================================================================

-- 1. Leaderboard snapshots
CREATE TABLE IF NOT EXISTS polyclaw_leaderboard_snapshots (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rank          INT NOT NULL,
    address       TEXT NOT NULL,
    tier          TEXT NOT NULL DEFAULT 'fish',
    score         DOUBLE PRECISION DEFAULT 0,
    trade_count   INT DEFAULT 0,
    total_volume_usd DOUBLE PRECISION DEFAULT 0,
    avg_trade_size   DOUBLE PRECISION DEFAULT 0,
    maker_ratio      DOUBLE PRECISION DEFAULT 0,
    trades_per_day   DOUBLE PRECISION DEFAULT 0,
    is_likely_bot    BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_polyclaw_lb_snapshot_time
    ON polyclaw_leaderboard_snapshots (snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_polyclaw_lb_address
    ON polyclaw_leaderboard_snapshots (address);


-- 2. Cross-exchange comparison snapshots
CREATE TABLE IF NOT EXISTS polyclaw_comparison_snapshots (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    polymarket_question TEXT,
    kalshi_title        TEXT,
    polymarket_yes_price DOUBLE PRECISION DEFAULT 0,
    kalshi_yes_price     DOUBLE PRECISION DEFAULT 0,
    price_diff           DOUBLE PRECISION DEFAULT 0,
    price_diff_pct       DOUBLE PRECISION DEFAULT 0,
    match_score          DOUBLE PRECISION DEFAULT 0,
    cheaper_on           TEXT DEFAULT '',
    has_arb              BOOLEAN DEFAULT FALSE,
    total_polymarket     INT DEFAULT 0,
    total_kalshi         INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_polyclaw_comp_snapshot_time
    ON polyclaw_comparison_snapshots (snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_polyclaw_comp_has_arb
    ON polyclaw_comparison_snapshots (has_arb) WHERE has_arb = TRUE;


-- 3. Copy-trade events
CREATE TABLE IF NOT EXISTS polyclaw_copytrade_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    wallet        TEXT NOT NULL,
    side          TEXT,            -- 'maker' or 'taker'
    price         DOUBLE PRECISION,
    size_usd      DOUBLE PRECISION,
    token_id      TEXT,
    market_slug   TEXT,
    transaction_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_polyclaw_ct_wallet
    ON polyclaw_copytrade_events (wallet);
CREATE INDEX IF NOT EXISTS idx_polyclaw_ct_detected
    ON polyclaw_copytrade_events (detected_at DESC);


-- 4. Market snapshots (Polymarket)
CREATE TABLE IF NOT EXISTS polyclaw_market_snapshots (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    condition_id  TEXT,
    question      TEXT,
    best_bid      DOUBLE PRECISION,
    best_ask      DOUBLE PRECISION,
    spread        DOUBLE PRECISION,
    midpoint      DOUBLE PRECISION,
    volume        DOUBLE PRECISION,
    volume_24h    DOUBLE PRECISION,
    liquidity     DOUBLE PRECISION,
    category      TEXT
);

CREATE INDEX IF NOT EXISTS idx_polyclaw_ms_snapshot_time
    ON polyclaw_market_snapshots (snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_polyclaw_ms_condition_id
    ON polyclaw_market_snapshots (condition_id);


-- 5. Enable Row Level Security (RLS) — permissive for now
-- You can tighten these later with proper auth policies
ALTER TABLE polyclaw_leaderboard_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE polyclaw_comparison_snapshots  ENABLE ROW LEVEL SECURITY;
ALTER TABLE polyclaw_copytrade_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE polyclaw_market_snapshots      ENABLE ROW LEVEL SECURITY;

-- Allow anon/service_role full access (tighten for prod)
CREATE POLICY "polyclaw_lb_all" ON polyclaw_leaderboard_snapshots
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "polyclaw_comp_all" ON polyclaw_comparison_snapshots
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "polyclaw_ct_all" ON polyclaw_copytrade_events
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "polyclaw_ms_all" ON polyclaw_market_snapshots
    FOR ALL USING (true) WITH CHECK (true);


-- Done! PolyClaw tables are ready.
-- Your Redentor Tec tables remain untouched.
SELECT 'PolyClaw schema created successfully ✅' AS status;
