"""Table definitions (DDL) for the analytics star schema.

Design notes / optimizations
-----------------------------
* The fact table ``events`` is a wide, denormalized clickstream table — the
  idiomatic ClickHouse pattern for analytics.
* ``LowCardinality(String)`` is used for every categorical column (event_type,
  category, brand, country, device, ...). This dictionary-encodes the values,
  which dramatically shrinks storage and speeds up GROUP BY / filtering.
* ``PARTITION BY toYYYYMM(event_date)`` lets time-bounded queries prune whole
  months of data.
* ``ORDER BY (event_type, event_date, user_id, session_id)`` matches the most
  common access pattern (filter by event_type + date range), so the primary
  index skips irrelevant granules.
* Data-skipping indexes (``minmax`` on product_id, ``bloom_filter`` on brand)
  accelerate point/needle lookups that the sort key doesn't cover.
* ``products`` and ``users`` are small dimension tables for JOIN-based
  analytics (top products by name, retention cohorts by signup date).
"""

from .db import Database

DB = "analytics"


def ddl_statements() -> list[str]:
    return [
        f"CREATE DATABASE IF NOT EXISTS {DB}",
        f"""
        CREATE TABLE IF NOT EXISTS {DB}.events
        (
            event_time   DateTime,
            event_date   Date DEFAULT toDate(event_time),
            event_type   LowCardinality(String),
            user_id      UInt32,
            session_id   UInt64,
            product_id   UInt32,
            category     LowCardinality(String),
            brand        LowCardinality(String),
            price        Float64,
            quantity     UInt16,
            revenue      Float64,
            country      LowCardinality(String),
            region       LowCardinality(String),
            device       LowCardinality(String),
            os           LowCardinality(String),
            browser      LowCardinality(String),
            channel      LowCardinality(String),
            is_new_user  UInt8,
            INDEX idx_product product_id TYPE minmax GRANULARITY 4,
            INDEX idx_brand   brand      TYPE bloom_filter(0.01) GRANULARITY 4
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(event_date)
        ORDER BY (event_type, event_date, user_id, session_id)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {DB}.products
        (
            product_id   UInt32,
            product_name String,
            category     LowCardinality(String),
            brand        LowCardinality(String),
            base_price   Float64,
            cost         Float64
        )
        ENGINE = MergeTree
        ORDER BY product_id
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {DB}.users
        (
            user_id             UInt32,
            signup_date         Date,
            country             LowCardinality(String),
            age_group           LowCardinality(String),
            gender              LowCardinality(String),
            acquisition_channel LowCardinality(String)
        )
        ENGINE = MergeTree
        ORDER BY user_id
        """,
    ]


def init_schema(db: Database) -> None:
    for stmt in ddl_statements():
        db.command(stmt)
