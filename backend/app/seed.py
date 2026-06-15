"""Sample-data generation.

All sample data is generated *inside* ClickHouse with ``INSERT ... SELECT FROM
numbers(N)``. This is the fastest possible way to create large, realistic
datasets — millions of rows are produced in well under a second without ever
shipping data over the wire.

Realism tricks
--------------
* Per-session attributes are derived from ``cityHash64(session_id, salt)`` so
  they are deterministic and stable (same session always looks the same).
* Each session is assigned a funnel ``depth`` (1..5) with a weighted
  distribution, then ``arrayJoin(range(1, depth + 1))`` explodes it into one
  row per funnel stage. This yields a realistic conversion funnel where every
  purchaser also has the upstream page_view / add_to_cart events.
* ``product_id`` deterministically maps to category / brand / price using the
  *same* formulas as the ``products`` dimension, so the star schema stays
  consistent and JOINs line up.
"""

from __future__ import annotations

import logging

from .config import Settings
from .db import Database
from .schema import DB

logger = logging.getLogger("app.seed")

# --- categorical dimensions (kept in sync between fact and dimension tables) ---
CATEGORIES = [
    "Electronics", "Apparel", "Home & Kitchen", "Beauty", "Sports",
    "Toys", "Grocery", "Books", "Automotive", "Garden",
]
BRANDS = [
    "Acme", "Globex", "Soylent", "Initech", "Umbrella", "Stark",
    "Wayne", "Wonka", "Hooli", "Pied Piper", "Vandelay", "Gekko",
]
COUNTRIES = [
    "United States", "United Kingdom", "Germany", "France", "India",
    "Brazil", "Canada", "Japan", "Australia", "Spain", "Italy", "Mexico",
]
REGIONS = [
    "North America", "Europe", "Europe", "Europe", "Asia",
    "South America", "North America", "Asia", "Oceania", "Europe", "Europe", "North America",
]
CHANNELS = ["organic", "paid_search", "social", "email", "direct", "referral"]
AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
GENDERS = ["female", "male", "other"]

STAGE_NAMES = ["page_view", "view_item", "add_to_cart", "begin_checkout", "purchase"]


def _arr(values: list[str]) -> str:
    """Render a Python list as a ClickHouse array literal."""
    escaped = ", ".join("'" + v.replace("'", "\\'") + "'" for v in values)
    return f"[{escaped}]"


# Deterministic product -> attribute formulas, reused by both fact & dimension.
_CATEGORY = f"({_arr(CATEGORIES)})[(product_id % {len(CATEGORIES)}) + 1]"
_BRAND = f"({_arr(BRANDS)})[(product_id * 7 % {len(BRANDS)}) + 1]"
_BASE_PRICE = "round(4.99 + (cityHash64(product_id) % 30000) / 100.0, 2)"


def is_empty(db: Database) -> bool:
    rows = db.query(f"SELECT count() AS c FROM {DB}.events")
    return not rows or int(rows[0]["c"]) == 0


def seed_products(db: Database, n: int) -> None:
    db.command(
        f"""
        INSERT INTO {DB}.products
        SELECT
            number + 1 AS product_id,
            concat({_CATEGORY}, ' ', {_BRAND}, ' #', toString(product_id)) AS product_name,
            {_CATEGORY} AS category,
            {_BRAND} AS brand,
            {_BASE_PRICE} AS base_price,
            round(base_price * (0.40 + (cityHash64(product_id, 2) % 30) / 100.0), 2) AS cost
        FROM numbers({int(n)})
        """
    )


def seed_users(db: Database, n: int) -> None:
    db.command(
        f"""
        INSERT INTO {DB}.users
        SELECT
            number + 1 AS user_id,
            today() - toIntervalDay(cityHash64(number, 11) % 730) AS signup_date,
            ({_arr(COUNTRIES)})[(cityHash64(number, 13) % {len(COUNTRIES)}) + 1] AS country,
            ({_arr(AGE_GROUPS)})[(cityHash64(number, 17) % {len(AGE_GROUPS)}) + 1] AS age_group,
            ({_arr(GENDERS)})[(cityHash64(number, 19) % {len(GENDERS)}) + 1] AS gender,
            ({_arr(CHANNELS)})[(cityHash64(number, 23) % {len(CHANNELS)}) + 1] AS acquisition_channel
        FROM numbers({int(n)})
        """
    )


def seed_events(db: Database, sessions: int, users: int, products: int, days: int) -> None:
    sessions, users, products, days = map(int, (sessions, users, products, days))
    db.command(
        f"""
        INSERT INTO {DB}.events
        (event_time, event_type, user_id, session_id, product_id, category, brand,
         price, quantity, revenue, country, region, device, os, browser, channel, is_new_user)
        SELECT
            session_start + toIntervalSecond(stage * (30 + cityHash64(session_id, stage) % 600)) AS event_time,
            ({_arr(STAGE_NAMES)})[stage] AS event_type,
            user_id,
            session_id,
            product_id,
            ({_arr(CATEGORIES)})[(product_id % {len(CATEGORIES)}) + 1] AS category,
            ({_arr(BRANDS)})[(product_id * 7 % {len(BRANDS)}) + 1] AS brand,
            price,
            quantity,
            if(stage = 5, round(price * quantity, 2), 0) AS revenue,
            ({_arr(COUNTRIES)})[country_idx + 1] AS country,
            ({_arr(REGIONS)})[country_idx + 1] AS region,
            device,
            multiIf(
                device = 'mobile',  (['iOS', 'Android'])[(cityHash64(session_id, 31) % 2) + 1],
                device = 'tablet',  (['iPadOS', 'Android'])[(cityHash64(session_id, 31) % 2) + 1],
                (['Windows', 'macOS', 'Linux'])[(cityHash64(session_id, 31) % 3) + 1]
            ) AS os,
            multiIf(
                device = 'mobile',  (['Safari', 'Chrome', 'Samsung Internet'])[(cityHash64(session_id, 37) % 3) + 1],
                (['Chrome', 'Firefox', 'Edge', 'Safari'])[(cityHash64(session_id, 37) % 4) + 1]
            ) AS browser,
            ({_arr(CHANNELS)})[(cityHash64(session_id, 5) % {len(CHANNELS)}) + 1] AS channel,
            if(cityHash64(session_id, 3) % 100 < 25, 1, 0) AS is_new_user
        FROM
        (
            SELECT
                number AS session_id,
                now() - toIntervalSecond(cityHash64(number, 99) % ({days} * 86400)) AS session_start,
                (cityHash64(number) % {users}) + 1 AS user_id,
                (cityHash64(number, 7) % {products}) + 1 AS product_id,
                {_BASE_PRICE} AS price,
                (cityHash64(number, 5) % 3) + 1 AS quantity,
                cityHash64(number, 13) % {len(COUNTRIES)} AS country_idx,
                multiIf(
                    cityHash64(number, 4) % 100 < 55, 'mobile',
                    cityHash64(number, 4) % 100 < 90, 'desktop',
                    'tablet'
                ) AS device,
                multiIf(
                    cityHash64(number, 2) % 100 < 40, 1,
                    cityHash64(number, 2) % 100 < 65, 2,
                    cityHash64(number, 2) % 100 < 82, 3,
                    cityHash64(number, 2) % 100 < 93, 4,
                    5
                ) AS depth,
                arrayJoin(range(1, depth + 1)) AS stage
            FROM numbers({sessions})
        )
        """
    )


def seed_all(db: Database, settings: Settings, force: bool = False) -> dict:
    """Seed every table. If ``force`` is False, only seeds when empty."""
    if not force and not is_empty(db):
        rows = db.query(f"SELECT count() AS c FROM {DB}.events")
        return {"seeded": False, "events": int(rows[0]["c"])}

    if force:
        for table in ("events", "products", "users"):
            db.command(f"TRUNCATE TABLE IF EXISTS {DB}.{table}")

    logger.info(
        "Seeding sample data: %s sessions, %s users, %s products over %s days",
        settings.seed_sessions, settings.seed_users, settings.seed_products, settings.seed_days,
    )
    seed_products(db, settings.seed_products)
    seed_users(db, settings.seed_users)
    seed_events(
        db,
        sessions=settings.seed_sessions,
        users=settings.seed_users,
        products=settings.seed_products,
        days=settings.seed_days,
    )
    rows = db.query(f"SELECT count() AS c FROM {DB}.events")
    count = int(rows[0]["c"])
    logger.info("Seed complete: %s events", count)
    return {"seeded": True, "events": count}
