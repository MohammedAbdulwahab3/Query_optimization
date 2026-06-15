#!/usr/bin/env python3
"""Smoke-test every analytics query against the configured backend.

Usage (from repo root):

    python scripts/verify.py

Honours the same env vars as the app (CH_BACKEND, SEED_* etc.). Defaults to a
small embedded dataset in /tmp so it runs fast and standalone.
"""

import os
import sys
import time

# Make the backend package importable and default to a quick embedded run.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("CH_BACKEND", "embedded")
os.environ.setdefault("CHDB_PATH", "/tmp/verify_chdb")
os.environ.setdefault("SEED_SESSIONS", "50000")
os.environ.setdefault("SEED_USERS", "8000")
os.environ.setdefault("SEED_PRODUCTS", "300")

from app import queries  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db  # noqa: E402
from app.queries import Filters  # noqa: E402
from app.schema import init_schema  # noqa: E402
from app.seed import seed_all  # noqa: E402

ANALYTICS = [
    "kpis", "revenue_over_time", "revenue_by_category", "top_products", "top_brands",
    "conversion_funnel", "sales_by_country", "sales_by_device", "sales_by_channel",
    "traffic_heatmap", "new_vs_returning", "aov_over_time", "cart_abandonment",
    "category_revenue_trend", "hourly_traffic", "session_metrics", "retention_cohort",
    "recent_events",
]


def main() -> int:
    settings = get_settings()
    db = init_db(settings)
    init_schema(db)
    print("seed:", seed_all(db, settings))

    f = Filters(days=90, limit=10)
    failures = 0
    for name in ANALYTICS:
        sql = getattr(queries, name)(f)
        try:
            t = time.time()
            rows = db.query(sql)
            dt = round((time.time() - t) * 1000)
            print(f"OK   {name:24s} rows={len(rows):4d} {dt:5d}ms")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name:24s} -> {exc}")

    db.query(queries.meta_filters())
    print("\n%d/%d analytics passed" % (len(ANALYTICS) - failures, len(ANALYTICS)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
