# Architecture & Performance

Telecom CDR analytics platform — how data flows through the storage, backend,
and frontend levels, and what makes each query fast.

## System diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  INGEST (Python · Faker)                                                        │
│  generator.py → 500k synthetic CDRs / 2000 subscribers (Ethiopian geo)         │
│  dual-write, runs once on startup                                              │
└───────────────┬───────────────────────────────────────────┬──────────────────┘
                │ batched INSERT (HTTP 8123)                  │ UNWIND/MERGE (Bolt 7687)
                ▼                                             ▼
┌───────────────────────────────────────────┐   ┌───────────────────────────────┐
│  STORAGE A — ClickHouse (columnar OLAP)    │   │  STORAGE B — Memgraph (graph)  │
│                                            │   │  in-memory, Bolt               │
│  cdr  (MergeTree)                          │   │                                │
│   • PARTITION BY toYYYYMM(call_start)      │   │  (:Subscriber)-[:CALLED]->()   │
│   • ORDER BY (caller_number, call_start)   │   │  (:Subscriber)-[:USED]->(:Dev) │
│   • PROJECTION proj_by_callee  ◄── B-party │   │  (:Subscriber)-[:CONNECTED_AT] │
│   • LowCardinality cols, sparse PK index   │   │            ->(:Cell)           │
│                                            │   │  indexes: number, imei, cell   │
│  cdr_daily_rollup     (SummingMergeTree) ◄─┼── MVs fan each CDR into A+B rows   │
│  cdr_location_rollup  (SummingMergeTree) ◄─┘   │  CALLED aggregated per pair    │
│  warrants · audit_log (MergeTree)          │   │  (bounded edge count)          │
└───────────────┬────────────────────────────┘   └───────────────┬───────────────┘
                │ native protocol (9000)                          │ Bolt (7687)
                │  parameterized ? queries                        │  $param Cypher
                ▼                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  BACKEND — Go (Fiber / fasthttp)                                                │
│                                                                                │
│   requireAuth (JWT) ─► warrantGate (active-warrant check + audit) ─► handler   │
│                                                                                │
│   ClickHouse-backed: /search /timeline /flags /patterns /trajectory            │
│                      /colocation /alerts /audit                                 │
│   Memgraph-backed:   /graph /link                                              │
│                                                                                │
│        ┌───────────────── Redis (short-TTL result cache, 30s) ─────────────┐   │
│        │  key = route+params → JSON;  X-Cache: HIT/MISS                     │   │
│        └────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬────────────────────────────────────────────────┘
                                 │ HTTP/JSON  (nginx proxies /api → :8080)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND — React + Vite + TanStack Query (served by nginx)                     │
│  Login ─► Search │ Alerts │ Audit tabs                                          │
│  Profile · Leaflet map · react-force-graph · pattern heatmap · trajectory       │
│  playback · link panel · co-location · react-window virtualized timeline        │
│  TanStack Query: client cache + dedupe + bearer token                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Why each level is fast

### Storage A — ClickHouse (the analytical workhorse)
| Technique | Effect |
|-----------|--------|
| `PARTITION BY toYYYYMM` | date-range queries prune whole months |
| `ORDER BY (caller_number, call_start)` + sparse PK index (granularity 8192) | A-party lookups read only matching granules, not the table |
| `PROJECTION proj_by_callee` | same data re-sorted by callee → B-party lookups are *also* a range scan |
| `cdr_daily_rollup` (SummingMergeTree + 2 MVs) | call count / total minutes per number read from a tiny pre-aggregated table, not 500k rows |
| `cdr_location_rollup` | map points = **one row per tower**, not per call |
| `LowCardinality(String)` on operator/type/etc. | dictionary-encoded → less I/O, faster GROUP BY |

### Storage B — Memgraph (relationships)
- In-memory graph; **label+property indexes** on `Subscriber(number)`, `Device(imei)`, `Cell(cell_id)` make lookups O(1)-ish.
- `CALLED` edges are **aggregated per (caller, callee) pair** (not one edge per call), so the graph stays small (~tens of thousands of edges) and depth-1/2 traversals + BFS shortest-path are local and millisecond-scale.

### Backend — Go (Fiber)
- `fasthttp` core: high throughput, low per-request allocation.
- **Redis result cache** (30 s TTL) fronts every read → repeated/popular queries skip the datastore entirely.
- Connection pooling (clickhouse-go), parameterized queries, per-request timeouts.

### Frontend — React
- **TanStack Query** dedupes and caches requests client-side.
- **react-window** virtualizes the timeline (renders ~12 rows regardless of thousands).
- Pre-aggregated endpoints keep payloads tiny (map = #towers, not #calls).

## Performance characteristics

Two classes of query:

| Class | Endpoints | Data path | Cost |
|-------|-----------|-----------|------|
| **Point / range** (rollup- or index-backed) | `/search`, `/timeline`, `/graph`, `/link`, `/patterns`, `/trajectory`, `/flags` | rollup table, PK range, projection, or graph traversal | scales with *that number's* data, ~constant as the dataset grows |
| **Full-scan aggregation** | `/alerts`, `/colocation` | `UNION ALL` over the full table / temporal self-join | O(N) over all CDRs — heavier, but cached 30 s |

### Expected latencies
*Engineering estimates for ~500k CDRs on a single node — not benchmarked in this
build sandbox (Docker image pulls for the ClickHouse/Memgraph servers are
network-blocked here). Correctness of every query was verified against an
embedded ClickHouse engine (chdb).*

| Endpoint | Uncached (est.) | Cached |
|----------|------------------|--------|
| `/search`, `/timeline` | 5–30 ms | ~1–5 ms |
| `/graph`, `/link` (Memgraph) | 5–50 ms | ~1–5 ms |
| `/patterns`, `/trajectory`, `/flags` | 10–50 ms | ~1–5 ms |
| `/colocation` (temporal self-join) | 50–300 ms | ~1–5 ms |
| `/alerts` (dataset-wide) | 100–500 ms | ~1–5 ms |

### What was actually measured
- All schema DDL, rollups, the callee projection, and every endpoint's SQL run
  correctly on the embedded engine (up to ~16k rows in tests).
- Rollup totals equal the raw `caller+callee` aggregates (verified).
- `go build` / `go vet` / `go test` pass; `vite build` succeeds.

### Scaling notes
- ClickHouse scales to billions of rows; the rollups + projection keep
  per-number queries cheap **regardless of total size**.
- The two full-scan endpoints (`/alerts`, `/colocation`) are the first place to
  optimize at very large scale — e.g. a daily per-number behavior rollup
  (calls / contacts / night-ratio) and a data-skipping index on `cell_id`,
  which would turn both into index-backed reads. Today they rely on
  ClickHouse's columnar scan speed + the Redis cache.
