"""All analytics SQL lives here — one function per analytic.

Every query is written to be ClickHouse-friendly:
* time ranges always filter on ``event_date`` so the engine prunes partitions;
* aggregate-then-join (filter & aggregate the big fact table first, join the
  small dimension afterwards);
* ``-If`` combinators (``sumIf``, ``countIf``, ``uniqExactIf``) compute several
  metrics in a single pass over the data instead of multiple scans;
* dates/timestamps are formatted to strings in SQL so output is identical
  across the embedded and server backends.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import DB

# Columns a caller is allowed to filter on, mapped to their SQL column.
_FILTERABLE = {
    "country": "country",
    "category": "category",
    "device": "device",
    "channel": "channel",
}


def _lit(value: str) -> str:
    """Escape a string value for safe inlining as a SQL literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


@dataclass
class Filters:
    days: int = 30
    country: str | None = None
    category: str | None = None
    device: str | None = None
    channel: str | None = None
    limit: int = 10

    def where(self, extra: str | None = None) -> str:
        conds = [f"event_date >= today() - {int(self.days)}"]
        for field, column in _FILTERABLE.items():
            value = getattr(self, field)
            if value:
                conds.append(f"{column} = {_lit(value)}")
        if extra:
            conds.append(extra)
        return "WHERE " + " AND ".join(conds)


# --------------------------------------------------------------------------- #
# Individual analytics queries
# --------------------------------------------------------------------------- #

def kpis(f: Filters) -> str:
    # Single pass computes every headline KPI using -If combinators. The
    # ``revenue`` output alias shadows the physical column, so the fact table is
    # aliased ``e`` and revenue is referenced as ``e.revenue`` inside aggregates.
    return f"""
        SELECT
            round(sum(e.revenue), 2)                                            AS revenue,
            countIf(e.event_type = 'purchase')                                  AS orders,
            uniqExact(e.user_id)                                                AS users,
            uniqExact(e.session_id)                                             AS sessions,
            round(countIf(e.event_type = 'purchase')
                  / nullIf(uniqExact(e.session_id), 0) * 100, 2)                AS conversion_rate,
            round(sum(e.revenue)
                  / nullIf(countIf(e.event_type = 'purchase'), 0), 2)           AS avg_order_value
        FROM {DB}.events AS e
        {f.where()}
    """


def revenue_over_time(f: Filters) -> str:
    return f"""
        SELECT
            toString(event_date)              AS date,
            round(sum(revenue), 2)            AS revenue,
            countIf(event_type = 'purchase')  AS orders
        FROM {DB}.events
        {f.where()}
        GROUP BY event_date
        ORDER BY event_date
    """


def revenue_by_category(f: Filters) -> str:
    return f"""
        SELECT
            category,
            round(sum(revenue), 2)            AS revenue,
            countIf(event_type = 'purchase')  AS orders
        FROM {DB}.events
        {f.where()}
        GROUP BY category
        ORDER BY revenue DESC
    """


def top_products(f: Filters) -> str:
    # Aggregate the fact table down to the top-N product ids first, then join
    # the (tiny) result to the products dimension to attach human names.
    return f"""
        SELECT
            t.product_id                AS product_id,
            p.product_name              AS product,
            t.revenue                   AS revenue,
            t.units                     AS units,
            t.views                     AS views
        FROM
        (
            SELECT
                product_id,
                round(sum(revenue), 2)              AS revenue,
                countIf(event_type = 'purchase')    AS units,
                countIf(event_type = 'view_item')   AS views
            FROM {DB}.events
            {f.where()}
            GROUP BY product_id
            ORDER BY revenue DESC
            LIMIT {int(f.limit)}
        ) AS t
        LEFT JOIN {DB}.products AS p ON t.product_id = p.product_id
        ORDER BY t.revenue DESC
    """


def top_brands(f: Filters) -> str:
    return f"""
        SELECT
            brand,
            round(sum(revenue), 2)            AS revenue,
            countIf(event_type = 'purchase')  AS orders
        FROM {DB}.events
        {f.where()}
        GROUP BY brand
        ORDER BY revenue DESC
        LIMIT {int(f.limit)}
    """


def conversion_funnel(f: Filters) -> str:
    return f"""
        SELECT
            event_type            AS stage,
            uniqExact(session_id) AS sessions,
            count()               AS events
        FROM {DB}.events
        {f.where("event_type IN ('page_view','view_item','add_to_cart','begin_checkout','purchase')")}
        GROUP BY event_type
    """


def sales_by_country(f: Filters) -> str:
    return f"""
        SELECT
            country,
            round(sum(revenue), 2)            AS revenue,
            countIf(event_type = 'purchase')  AS orders,
            uniqExact(user_id)                AS users
        FROM {DB}.events
        {f.where()}
        GROUP BY country
        ORDER BY revenue DESC
    """


def sales_by_device(f: Filters) -> str:
    return f"""
        SELECT
            device,
            uniqExact(session_id)             AS sessions,
            countIf(event_type = 'purchase')  AS orders,
            round(sum(revenue), 2)            AS revenue
        FROM {DB}.events
        {f.where()}
        GROUP BY device
        ORDER BY sessions DESC
    """


def sales_by_channel(f: Filters) -> str:
    return f"""
        SELECT
            channel,
            uniqExact(session_id)             AS sessions,
            countIf(event_type = 'purchase')  AS orders,
            round(sum(revenue), 2)            AS revenue,
            round(countIf(event_type = 'purchase')
                  / nullIf(uniqExact(session_id), 0) * 100, 2) AS conversion_rate
        FROM {DB}.events
        {f.where()}
        GROUP BY channel
        ORDER BY revenue DESC
    """


def traffic_heatmap(f: Filters) -> str:
    # Day-of-week (1=Mon..7=Sun) x hour-of-day activity grid.
    return f"""
        SELECT
            toDayOfWeek(event_time) AS dow,
            toHour(event_time)      AS hour,
            count()                 AS events
        FROM {DB}.events
        {f.where()}
        GROUP BY dow, hour
        ORDER BY dow, hour
    """


def new_vs_returning(f: Filters) -> str:
    return f"""
        SELECT
            if(is_new_user = 1, 'new', 'returning') AS segment,
            uniqExact(user_id)                       AS users,
            uniqExact(session_id)                    AS sessions,
            round(sum(revenue), 2)                   AS revenue
        FROM {DB}.events
        {f.where()}
        GROUP BY segment
        ORDER BY users DESC
    """


def aov_over_time(f: Filters) -> str:
    return f"""
        SELECT
            toString(event_date) AS date,
            round(sumIf(revenue, event_type = 'purchase')
                  / nullIf(countIf(event_type = 'purchase'), 0), 2) AS aov
        FROM {DB}.events
        {f.where()}
        GROUP BY event_date
        ORDER BY event_date
    """


def cart_abandonment(f: Filters) -> str:
    return f"""
        SELECT
            uniqExactIf(session_id, event_type = 'add_to_cart')  AS carts,
            uniqExactIf(session_id, event_type = 'purchase')     AS purchases,
            round((1 - uniqExactIf(session_id, event_type = 'purchase')
                       / nullIf(uniqExactIf(session_id, event_type = 'add_to_cart'), 0)) * 100, 2)
                                                                 AS abandonment_rate
        FROM {DB}.events
        {f.where()}
    """


def category_revenue_trend(f: Filters) -> str:
    # Revenue per category per day — the frontend pivots this into a stacked
    # time series.
    return f"""
        SELECT
            toString(event_date)   AS date,
            category,
            round(sum(revenue), 2) AS revenue
        FROM {DB}.events
        {f.where("event_type = 'purchase'")}
        GROUP BY event_date, category
        ORDER BY event_date
    """


def hourly_traffic(f: Filters) -> str:
    return f"""
        SELECT
            toHour(event_time)    AS hour,
            count()               AS events,
            uniqExact(session_id) AS sessions
        FROM {DB}.events
        {f.where()}
        GROUP BY hour
        ORDER BY hour
    """


def session_metrics(f: Filters) -> str:
    # Two-level aggregation: collapse to per-session stats, then average them.
    return f"""
        SELECT
            count()                                          AS total_sessions,
            round(avg(events_in_session), 2)                 AS avg_events_per_session,
            round(avg(duration_seconds), 1)                  AS avg_session_seconds,
            round(quantile(0.5)(duration_seconds), 1)        AS median_session_seconds
        FROM
        (
            SELECT
                session_id,
                count()                                                AS events_in_session,
                dateDiff('second', min(event_time), max(event_time))   AS duration_seconds
            FROM {DB}.events
            {f.where()}
            GROUP BY session_id
        )
    """


def retention_cohort(f: Filters) -> str:
    # Weekly signup cohorts vs. activity in subsequent weeks. This is the
    # heaviest analytic (fact x dimension join), bounded by the date filter so
    # only recent cohorts are scanned.
    return f"""
        SELECT
            toString(toMonday(u.signup_date))                                AS cohort_week,
            dateDiff('week', toMonday(u.signup_date), toMonday(e.event_date)) AS week_number,
            uniqExact(u.user_id)                                             AS users
        FROM {DB}.users AS u
        INNER JOIN {DB}.events AS e ON u.user_id = e.user_id
        WHERE u.signup_date >= today() - {int(f.days)}
          AND e.event_date  >= u.signup_date
        GROUP BY cohort_week, week_number
        HAVING week_number >= 0
        ORDER BY cohort_week, week_number
    """


def recent_events(f: Filters) -> str:
    return f"""
        SELECT
            toString(event_time)   AS time,
            event_type,
            user_id,
            product_id,
            category,
            brand,
            round(revenue, 2)      AS revenue,
            country,
            device,
            channel
        FROM {DB}.events
        {f.where()}
        ORDER BY event_time DESC
        LIMIT {int(f.limit)}
    """


def meta_filters() -> str:
    # Distinct filter values + the data's date range, for the dashboard UI.
    return f"""
        SELECT
            groupUniqArray(category) AS categories,
            groupUniqArray(country)  AS countries,
            groupUniqArray(device)   AS devices,
            groupUniqArray(channel)  AS channels,
            toString(min(event_date)) AS min_date,
            toString(max(event_date)) AS max_date
        FROM {DB}.events
    """
