# Telecom CDR Analytics Platform

A polyglot, docker-compose monorepo demo of a **lawful-interception CDR (Call
Detail Record) analytics tool** — built as an INSA Ethiopia internal demo.

> ⚠️ **Demo / educational build.** All data is **synthetic** (generated with
> Faker). Court/warrant authorization is **out of scope** for this build and
> will be added later as an auth layer — the code leaves clean seams for it (a
> pass-through auth middleware stub on every API route, and an unused
> `warrant_id` column on the CDR table).

## Architecture

One synthetic ingest stream fans out to two stores; a Go API reads both (with a
Redis cache) and serves a React analyst dashboard.

```
                 ┌─────────────────────────────────────────────┐
  ingest (Py) ──▶│  ClickHouse   raw CDRs + rollups (counts,    │
   Faker, dual   │               minutes, map points)           │
   write         │  Memgraph     contact graph (shared devices, │
                 │               co-located towers)             │
                 └───────────────┬───────────────┬─────────────┘
                                 │               │
                        ┌────────▼───────────────▼────────┐
   React (Vite +  ◀────▶│  Go (Fiber) REST API + Redis cache│
   TanStack Query)      │  /search /graph /timeline         │
                        └───────────────────────────────────┘
```

| Component   | Tech | Role |
|-------------|------|------|
| `clickhouse/` | ClickHouse | raw 26-col CDR table + pre-aggregated rollups + callee projection |
| `ingest/`     | Python (Faker) | synthetic CDR generator, dual-write to ClickHouse + Memgraph |
| `api/`        | Go (Fiber) + Redis | REST API over both stores, parameterized queries, auth stub |
| `web/`        | React + Vite + TanStack Query | analyst dashboard (profile, Leaflet map, force-graph, timeline) |

## Status

Built incrementally; each layer verified before the next.

- [x] **ClickHouse schema + rollups** (`clickhouse/schema.sql`) — verified
- [x] **Ingest** — synthetic generator, dual-write (`ingest/`) — verified
- [x] **Go Fiber API** — `/search` `/graph` `/timeline`, Redis cache, auth stub (`api/`) — verified
- [ ] React dashboard
- [ ] docker-compose wiring + run instructions

### API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /search/:number` | profile (name, operator, device, IMEI, IMSI, reg date) + call count + total minutes + map points |
| `GET /graph/:number?depth=1\|2` | contact network (force-graph nodes/links) + shared devices + co-located towers |
| `GET /timeline/:number?page=&page_size=&from=&to=` | paginated call records with date-range filter |
| `GET /health` | health check |

All queries are **parameterized** (`?` bindings for ClickHouse, `$param` for
Cypher). A short-TTL Redis cache fronts every result. A pass-through
**auth middleware stub** guards every route — the seam for warrant checks.

## Quick start

> _Coming as the stack is wired up._ The goal: `docker compose up` brings up
> clickhouse, memgraph, redis, api, web, and the ingest job seeds ~500k
> synthetic calls across ~2000 subscribers on startup.

See `clickhouse/schema.sql` for the data model (documented inline).
