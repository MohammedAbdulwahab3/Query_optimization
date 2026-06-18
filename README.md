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
- [ ] Ingest (synthetic generator, dual-write)
- [ ] Go Fiber API
- [ ] React dashboard
- [ ] docker-compose wiring + run instructions

## Quick start

> _Coming as the stack is wired up._ The goal: `docker compose up` brings up
> clickhouse, memgraph, redis, api, web, and the ingest job seeds ~500k
> synthetic calls across ~2000 subscribers on startup.

See `clickhouse/schema.sql` for the data model (documented inline).
