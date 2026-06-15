"""HTTP API. Every analytic gets its own endpoint under ``/api/analytics``.

A shared ``Filters`` dependency lets every endpoint accept the same query
parameters (``days``, ``country``, ``category``, ``device``, ``channel`` and
``limit``) so the dashboard can apply global filters uniformly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import queries
from ..db import Database, get_db
from ..queries import Filters

router = APIRouter(prefix="/api", tags=["analytics"])

# Canonical funnel ordering used to sort the conversion-funnel result.
_FUNNEL_ORDER = {
    "page_view": 0, "view_item": 1, "add_to_cart": 2,
    "begin_checkout": 3, "purchase": 4,
}


def get_filters(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    country: str | None = Query(None),
    category: str | None = Query(None),
    device: str | None = Query(None),
    channel: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
) -> Filters:
    return Filters(
        days=days, country=country, category=category,
        device=device, channel=channel, limit=limit,
    )


def _one(rows: list[dict]) -> dict:
    return rows[0] if rows else {}


# A catalogue describing every analytic — also drives the dashboard layout. #
ANALYTICS_CATALOG = [
    {"id": "kpis", "title": "Headline KPIs", "viz": "kpi"},
    {"id": "revenue-over-time", "title": "Revenue Over Time", "viz": "line"},
    {"id": "conversion-funnel", "title": "Conversion Funnel", "viz": "funnel"},
    {"id": "revenue-by-category", "title": "Revenue by Category", "viz": "doughnut"},
    {"id": "category-revenue-trend", "title": "Category Revenue Trend", "viz": "stacked"},
    {"id": "top-products", "title": "Top Products", "viz": "hbar"},
    {"id": "top-brands", "title": "Top Brands", "viz": "hbar"},
    {"id": "sales-by-country", "title": "Sales by Country", "viz": "bar"},
    {"id": "sales-by-device", "title": "Sales by Device", "viz": "pie"},
    {"id": "sales-by-channel", "title": "Marketing Channels", "viz": "bar"},
    {"id": "new-vs-returning", "title": "New vs Returning", "viz": "doughnut"},
    {"id": "aov-over-time", "title": "Avg Order Value Over Time", "viz": "line"},
    {"id": "cart-abandonment", "title": "Cart Abandonment", "viz": "gauge"},
    {"id": "hourly-traffic", "title": "Traffic by Hour", "viz": "bar"},
    {"id": "traffic-heatmap", "title": "Traffic Heatmap", "viz": "heatmap"},
    {"id": "session-metrics", "title": "Session Metrics", "viz": "stat"},
    {"id": "retention-cohort", "title": "Weekly Retention Cohorts", "viz": "cohort"},
    {"id": "recent-events", "title": "Recent Events", "viz": "table"},
]


@router.get("/analytics")
def list_analytics() -> dict:
    """Catalogue of all available analytics endpoints."""
    return {"analytics": ANALYTICS_CATALOG}


@router.get("/meta")
def meta(db: Database = Depends(get_db)) -> dict:
    """Distinct filter values + data date range for the dashboard controls."""
    return _one(db.query(queries.meta_filters()))


@router.get("/analytics/kpis")
def kpis(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> dict:
    return _one(db.query(queries.kpis(f)))


@router.get("/analytics/revenue-over-time")
def revenue_over_time(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.revenue_over_time(f))


@router.get("/analytics/revenue-by-category")
def revenue_by_category(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.revenue_by_category(f))


@router.get("/analytics/top-products")
def top_products(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.top_products(f))


@router.get("/analytics/top-brands")
def top_brands(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.top_brands(f))


@router.get("/analytics/conversion-funnel")
def conversion_funnel(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    rows = db.query(queries.conversion_funnel(f))
    rows.sort(key=lambda r: _FUNNEL_ORDER.get(r["stage"], 99))
    return rows


@router.get("/analytics/sales-by-country")
def sales_by_country(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.sales_by_country(f))


@router.get("/analytics/sales-by-device")
def sales_by_device(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.sales_by_device(f))


@router.get("/analytics/sales-by-channel")
def sales_by_channel(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.sales_by_channel(f))


@router.get("/analytics/traffic-heatmap")
def traffic_heatmap(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.traffic_heatmap(f))


@router.get("/analytics/new-vs-returning")
def new_vs_returning(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.new_vs_returning(f))


@router.get("/analytics/aov-over-time")
def aov_over_time(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.aov_over_time(f))


@router.get("/analytics/cart-abandonment")
def cart_abandonment(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> dict:
    return _one(db.query(queries.cart_abandonment(f)))


@router.get("/analytics/category-revenue-trend")
def category_revenue_trend(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.category_revenue_trend(f))


@router.get("/analytics/hourly-traffic")
def hourly_traffic(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    return db.query(queries.hourly_traffic(f))


@router.get("/analytics/session-metrics")
def session_metrics(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> dict:
    return _one(db.query(queries.session_metrics(f)))


@router.get("/analytics/retention-cohort")
def retention_cohort(
    f: Filters = Depends(get_filters), db: Database = Depends(get_db)
) -> list[dict]:
    # Cohorts only make sense over a longer window; default to 84 days (12 wk).
    if f.days < 84:
        f = Filters(**{**f.__dict__, "days": 84})
    return db.query(queries.retention_cohort(f))


@router.get("/analytics/recent-events")
def recent_events(f: Filters = Depends(get_filters), db: Database = Depends(get_db)) -> list[dict]:
    if f.limit < 20:
        f = Filters(**{**f.__dict__, "limit": 20})
    return db.query(queries.recent_events(f))
