# ClickHouse E-commerce Analytics

A full-stack analytics platform: **FastAPI** + **ClickHouse**, with a large,
realistic e-commerce clickstream dataset, **18 optimized analytics — each
exposed as its own API endpoint** — and a single-page dashboard that
visualizes them all.

![Dashboard](docs/dashboard.png)

---

## Highlights

- **18 analytics, one endpoint each** under `/api/analytics/*` (KPIs, revenue
  trends, conversion funnel, retention cohorts, geo/device/channel breakdowns,
  traffic heatmap, and more).
- **Optimized ClickHouse SQL** — `LowCardinality` columns, monthly partitions,
  a tuned sort key, data-skipping indexes, `-If` aggregate combinators, and
  aggregate-then-join patterns.
- **Realistic sample data** — ~1M+ funnel-correlated events generated entirely
  inside ClickHouse via `INSERT … SELECT FROM numbers()` (seeds in under a
  second).
- **Two interchangeable backends, identical SQL:**
  - `embedded` — in-process [`chdb`](https://github.com/chdb-io/chdb) (ClickHouse
    as a Python library). **Zero external services** — great for self-use.
  - `server` — a real `clickhouse-server` over HTTP (used by Docker Compose).
- **Self-contained frontend** — vanilla JS + a vendored Chart.js (no CDN), served
  by FastAPI.

---

## Quick start

### Option A — zero dependencies (embedded engine)

No database to install. Uses `chdb` and seeds sample data on first launch.

```bash
./scripts/run_local.sh
# open http://localhost:8000
```

Or manually:

```bash
cd backend
pip install -r requirements.txt
CH_BACKEND=embedded uvicorn app.main:app --reload
```

### Option B — full deployment (Docker Compose)

Spins up a real `clickhouse-server` + the API/dashboard, and seeds ~1.1M events.

```bash
docker compose up --build
# open http://localhost:8000
```

The ClickHouse HTTP interface is also exposed on `localhost:8123` for ad-hoc
queries.

---

## Architecture

```
                    ┌──────────────────────────────────────┐
   Browser  ──────▶ │  FastAPI  (backend/app)               │
   (dashboard)      │  • /api/analytics/*  — 18 endpoints   │
                    │  • serves static dashboard at /       │
                    │            │                          │
                    │   db.py (pluggable)                   │
                    │      ├── EmbeddedDatabase  (chdb)      │
                    │      └── ServerDatabase    (HTTP) ─────┼──▶ clickhouse-server
                    └──────────────────────────────────────┘
```

Both database implementations satisfy the same `Database` interface and run the
**exact same SQL**, so switching is a single env var (`CH_BACKEND`).

### Data model (star schema)

| Table      | Role             | Notes |
|------------|------------------|-------|
| `events`   | fact (clickstream) | wide & denormalized; `MergeTree`, `PARTITION BY toYYYYMM(event_date)`, `ORDER BY (event_type, event_date, user_id, session_id)`, skip indexes on `product_id`/`brand` |
| `products` | dimension        | product names/categories/brands/prices |
| `users`    | dimension        | signup date + attributes (used for cohorts) |

Event types form a funnel: `page_view → view_item → add_to_cart →
begin_checkout → purchase`. The seeder assigns each session a weighted funnel
depth and explodes it with `arrayJoin`, so purchasers always have their
upstream events and the funnel/retention numbers are realistic.

---

## API

Interactive docs (Swagger UI) at **`/docs`**. Every endpoint accepts the same
optional query parameters:

| Param | Default | Description |
|-------|---------|-------------|
| `days` | `30` | lookback window (1–365) |
| `country`, `category`, `device`, `channel` | – | optional equality filters |
| `limit` | `10` | for top-N / table endpoints |

| Endpoint | Description |
|----------|-------------|
| `GET /api/analytics/kpis` | revenue, orders, users, sessions, conversion, AOV |
| `GET /api/analytics/revenue-over-time` | daily revenue & orders |
| `GET /api/analytics/revenue-by-category` | revenue per category |
| `GET /api/analytics/category-revenue-trend` | revenue per category per day |
| `GET /api/analytics/top-products` | top products by revenue (joins `products`) |
| `GET /api/analytics/top-brands` | top brands by revenue |
| `GET /api/analytics/conversion-funnel` | sessions per funnel stage |
| `GET /api/analytics/sales-by-country` | revenue/orders/users by country |
| `GET /api/analytics/sales-by-device` | sessions/orders/revenue by device |
| `GET /api/analytics/sales-by-channel` | marketing channel performance |
| `GET /api/analytics/new-vs-returning` | new vs returning split |
| `GET /api/analytics/aov-over-time` | average order value per day |
| `GET /api/analytics/cart-abandonment` | cart abandonment rate |
| `GET /api/analytics/hourly-traffic` | events/sessions per hour |
| `GET /api/analytics/traffic-heatmap` | day-of-week × hour activity |
| `GET /api/analytics/session-metrics` | events/session, session duration |
| `GET /api/analytics/retention-cohort` | weekly signup-cohort retention |
| `GET /api/analytics/recent-events` | latest raw events |
| `GET /api/meta` | distinct filter values + data date range |
| `GET /api/analytics` | machine-readable catalogue of all analytics |
| `GET /api/health` | health check |
| `POST /api/admin/reseed` | wipe & regenerate sample data |

Example:

```bash
curl "http://localhost:8000/api/analytics/kpis?days=90&country=Germany"
```

---

## Configuration

All settings come from environment variables (or a `.env` file — see
`.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CH_BACKEND` | `embedded` | `embedded` (chdb) or `server` |
| `CH_HOST` / `CH_PORT` / `CH_USER` / `CH_PASSWORD` | `localhost` / `8123` / `default` / – | server connection |
| `CHDB_PATH` | `./data/chdb` | on-disk store for embedded mode |
| `AUTO_SEED` | `true` | seed sample data on startup if empty |
| `SEED_SESSIONS` / `SEED_USERS` / `SEED_PRODUCTS` / `SEED_DAYS` | `500000` / `50000` / `500` / `90` | dataset size |

---

## Verify

Run every analytics query against a small embedded dataset:

```bash
python scripts/verify.py
```

---

## Project layout

```
backend/
  app/
    main.py        FastAPI app, startup seeding, static frontend
    config.py      env-driven settings
    db.py          pluggable ClickHouse backend (embedded | server)
    schema.py      table DDL
    seed.py        in-database sample-data generation
    queries.py     all optimized analytics SQL
    routers/analytics.py  one endpoint per analytic
  Dockerfile
  requirements.txt
frontend/
  index.html, styles.css, app.js, vendor/chart.umd.min.js
scripts/
  run_local.sh, verify.py
docker-compose.yml
```
