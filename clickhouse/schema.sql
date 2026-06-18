-- ============================================================================
-- Telecom CDR Analytics — ClickHouse schema
-- ============================================================================
-- Lawful-interception analytics demo (INSA Ethiopia internal).
-- SYNTHETIC DATA ONLY. Court/warrant authorization is OUT OF SCOPE here; the
-- `warrant_id` column below is a deliberate, currently-unused seam so an auth
-- layer can populate/filter on it later without reshaping the schema.
--
-- This file is idempotent: it can be re-run on startup. It creates:
--   1. the raw CDR table (MergeTree) with a projection ordered by callee_number
--   2. a per-number daily rollup (call count + total minutes)  [SummingMergeTree]
--   3. a per-number location rollup (map points / tower hits)  [SummingMergeTree]
--   4. materialized views that fan each CDR into both A-party and B-party rows
-- ============================================================================

CREATE DATABASE IF NOT EXISTS telecom;

-- ----------------------------------------------------------------------------
-- 1. Raw CDR fact table
-- ----------------------------------------------------------------------------
-- PARTITION BY month of call_start, ORDER BY (caller_number, call_start) so
-- A-party lookups are a primary-key range scan. The `proj_by_callee`
-- projection re-sorts the same data by callee_number, so a number is found
-- efficiently whether it appears as the A-party or the B-party of a call.
CREATE TABLE IF NOT EXISTS telecom.cdr
(
    record_id          UUID,
    caller_number      String,
    callee_number      String,
    subscriber_name    String,
    imsi               String,
    imei               String,
    device_model       LowCardinality(String),
    operator           LowCardinality(String),
    call_type          LowCardinality(String),   -- voice | sms | data | video
    direction          LowCardinality(String),   -- outgoing | incoming
    call_start         DateTime64(3),
    call_end           DateTime64(3),
    duration_sec       UInt32,
    call_result        LowCardinality(String),   -- answered | missed | busy | failed
    cell_id            String,
    lac_tac            String,
    latitude           Float64,
    longitude          Float64,
    location_name      LowCardinality(String),
    roaming_flag       UInt8,
    network_type       LowCardinality(String),   -- 2G | 3G | 4G | 5G
    registration_date  Date,
    charge_amount      Decimal(10, 4),
    data_volume_mb     Float64,
    ingest_timestamp   DateTime,
    warrant_id         String DEFAULT '',        -- UNUSED seam for the auth layer

    -- Find a number fast when it is the B-party (callee) of a call.
    PROJECTION proj_by_callee
    (
        SELECT *
        ORDER BY (callee_number, call_start)
    )
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(call_start)
ORDER BY (caller_number, call_start)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- 2. Per-number daily rollup  → fast call counts & total minutes
-- ----------------------------------------------------------------------------
-- One physical row per (number, day, operator). A number is counted once per
-- call it participates in, whether as caller or callee (see the two MVs below).
-- SummingMergeTree collapses the partial aggregates produced per insert block.
CREATE TABLE IF NOT EXISTS telecom.cdr_daily_rollup
(
    number             String,
    call_day           Date,
    operator           LowCardinality(String),
    call_count         UInt64,
    total_duration_sec UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(call_day)
ORDER BY (number, call_day, operator);

-- A-party (caller) contribution
CREATE MATERIALIZED VIEW IF NOT EXISTS telecom.cdr_daily_rollup_caller_mv
TO telecom.cdr_daily_rollup
AS
SELECT
    caller_number       AS number,
    toDate(call_start)  AS call_day,
    operator,
    count()             AS call_count,
    sum(duration_sec)   AS total_duration_sec
FROM telecom.cdr
GROUP BY number, call_day, operator;

-- B-party (callee) contribution
CREATE MATERIALIZED VIEW IF NOT EXISTS telecom.cdr_daily_rollup_callee_mv
TO telecom.cdr_daily_rollup
AS
SELECT
    callee_number       AS number,
    toDate(call_start)  AS call_day,
    operator,
    count()             AS call_count,
    sum(duration_sec)   AS total_duration_sec
FROM telecom.cdr
GROUP BY number, call_day, operator;


-- ----------------------------------------------------------------------------
-- 3. Per-number location rollup  → fast map points (tower hits)
-- ----------------------------------------------------------------------------
-- Pre-aggregated lat/lon hit counts per number so the dashboard map renders
-- without scanning raw CDRs. lat/lon are part of the key (one row per tower).
CREATE TABLE IF NOT EXISTS telecom.cdr_location_rollup
(
    number        String,
    cell_id       String,
    latitude      Float64,
    longitude     Float64,
    location_name LowCardinality(String),
    hits          UInt64
)
ENGINE = SummingMergeTree
ORDER BY (number, cell_id, latitude, longitude, location_name);

-- A-party (caller) location contribution
CREATE MATERIALIZED VIEW IF NOT EXISTS telecom.cdr_location_rollup_caller_mv
TO telecom.cdr_location_rollup
AS
SELECT
    caller_number AS number,
    cell_id,
    latitude,
    longitude,
    location_name,
    count()       AS hits
FROM telecom.cdr
GROUP BY number, cell_id, latitude, longitude, location_name;

-- B-party (callee) location contribution
CREATE MATERIALIZED VIEW IF NOT EXISTS telecom.cdr_location_rollup_callee_mv
TO telecom.cdr_location_rollup
AS
SELECT
    callee_number AS number,
    cell_id,
    latitude,
    longitude,
    location_name,
    count()       AS hits
FROM telecom.cdr
GROUP BY number, cell_id, latitude, longitude, location_name;
