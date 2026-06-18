"""
Ingest orchestration: generate synthetic CDRs and dual-write them to
ClickHouse (batched inserts) and Memgraph (batched MERGE/CREATE).

Runs on `docker compose up`. Idempotent: if ClickHouse already holds CDRs and
FORCE_RESEED is not set, it exits without reseeding.

All configuration is via environment variables (see defaults below).
"""

from __future__ import annotations

import os
from datetime import datetime

from generator import (
    build_cells,
    build_subscribers,
    generate_cdrs,
    _rng,
    _faker,
)
from writers import ClickHouseWriter, MemgraphWriter


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def main() -> None:
    # --- config ---
    ch_host = env("CLICKHOUSE_HOST", "clickhouse")
    ch_port = int(env("CLICKHOUSE_PORT", "8123"))
    ch_user = env("CLICKHOUSE_USER", "default")
    ch_pass = env("CLICKHOUSE_PASSWORD", "")
    ch_db = env("CLICKHOUSE_DATABASE", "telecom")

    mg_uri = env("MEMGRAPH_URI", "bolt://memgraph:7687")
    mg_user = env("MEMGRAPH_USER", "")
    mg_pass = env("MEMGRAPH_PASSWORD", "")

    n_subscribers = int(env("NUM_SUBSCRIBERS", "2000"))
    n_calls = int(env("NUM_CALLS", "500000"))
    batch_size = int(env("BATCH_SIZE", "50000"))
    seed = int(env("SEED", "42"))
    force = env("FORCE_RESEED", "false").lower() in ("1", "true", "yes")

    start_date = datetime.fromisoformat(env("START_DATE", "2026-03-20T00:00:00"))
    end_date = datetime.fromisoformat(env("END_DATE", "2026-06-18T00:00:00"))

    rng = _rng(seed)
    fake = _faker(seed)

    # --- connect ---
    print("[ingest] connecting to ClickHouse...")
    ch = ClickHouseWriter.connect_with_retry(ch_host, ch_port, ch_user, ch_pass, ch_db)

    existing = ch.cdr_count()
    if existing > 0 and not force:
        print(f"[ingest] ClickHouse already has {existing:,} CDRs; skipping CDR seed "
              f"(set FORCE_RESEED=true to override).")
        # Always make sure warrants exist, even on the skip path — otherwise an
        # older volume seeded before the auth layer would deny every number.
        ch.ensure_all_warrants()
        return

    print("[ingest] connecting to Memgraph...")
    mg = MemgraphWriter.connect_with_retry(mg_uri, mg_user, mg_pass)

    if force:
        print("[ingest] FORCE_RESEED: wiping stores...")
        ch.client.command(f"TRUNCATE TABLE IF EXISTS {ch_db}.cdr")
        ch.client.command(f"TRUNCATE TABLE IF EXISTS {ch_db}.warrants")
        mg.wipe()

    # --- build static dimensions ---
    print(f"[ingest] building {n_subscribers:,} subscribers + cells...")
    subscribers = build_subscribers(rng, n_subscribers)
    cells = build_cells(rng)
    by_number = {s.number: s for s in subscribers}

    # --- generate CDRs, stream-insert into ClickHouse, aggregate graph in memory ---
    print(f"[ingest] generating {n_calls:,} CDRs...")
    called: dict[tuple[str, str], dict] = {}      # (caller,callee) -> aggregates
    connected: dict[tuple[str, str], dict] = {}   # (number,cell_id) -> aggregates
    cell_meta: dict[str, dict] = {}

    batch: list[tuple] = []
    total = 0
    for row in generate_cdrs(rng, fake, subscribers, cells, n_calls, start_date, end_date):
        batch.append(row)

        caller, callee = row[1], row[2]
        call_type, call_start, duration = row[8], row[10], row[12]
        cell_id, lat, lon, loc = row[14], row[16], row[17], row[18]

        c = called.get((caller, callee))
        if c is None:
            called[(caller, callee)] = {
                "caller": caller, "callee": callee, "calls": 1,
                "total_duration": duration, "start": call_start.isoformat(),
                "duration": duration, "type": call_type,
            }
        else:
            c["calls"] += 1
            c["total_duration"] += duration

        cc = connected.get((caller, cell_id))
        if cc is None:
            connected[(caller, cell_id)] = {
                "number": caller, "cell_id": cell_id,
                "time": call_start.isoformat(), "connections": 1,
            }
        else:
            cc["connections"] += 1
            cc["time"] = call_start.isoformat()

        cell_meta.setdefault(
            cell_id, {"cell_id": cell_id, "lat": lat, "lon": lon, "location_name": loc}
        )

        if len(batch) >= batch_size:
            ch.insert_batch(batch)
            total += len(batch)
            print(f"[clickhouse] inserted {total:,}/{n_calls:,}")
            batch = []

    if batch:
        ch.insert_batch(batch)
        total += len(batch)
        print(f"[clickhouse] inserted {total:,}/{n_calls:,}")

    # --- write graph to Memgraph ---
    print("[memgraph] creating indexes...")
    mg.create_constraints()

    sub_rows = [
        {
            "number": s.number, "name": s.name, "imsi": s.imsi,
            "operator": s.operator, "reg_date": s.reg_date.isoformat(),
            "imei": s.device.imei, "model": s.device.model,
        }
        for s in subscribers
    ]
    _batched(mg.merge_subscribers, sub_rows, 1000, "subscribers+devices")
    _batched(mg.merge_cells, list(cell_meta.values()), 1000, "cells")
    _batched(mg.merge_called, list(called.values()), 5000, "CALLED edges")
    _batched(mg.merge_connected_at, list(connected.values()), 5000, "CONNECTED_AT edges")

    # --- seed warrants for every subscriber so no existing number is denied ---
    ch.ensure_all_warrants(force=force)

    # --- verify ---
    print("\n[verify] ClickHouse CDR count:", f"{ch.cdr_count():,}")
    print("[verify] Memgraph graph counts:", mg.counts())
    print("[verify] warrants seeded:", ch.warrant_count())
    mg.close()

    _print_sample_numbers(subscribers, called)
    print("[ingest] done.")


def _print_sample_numbers(subscribers, called) -> None:
    """Surface a few interesting numbers to search in the dashboard."""
    from collections import defaultdict

    # degree = how many distinct contacts a number has (good force-graphs)
    degree: dict[str, int] = defaultdict(int)
    for (a, b) in called:
        degree[a] += 1
        degree[b] += 1

    # numbers that share a handset (good for shared-device detection)
    imei_subs: dict[str, list] = defaultdict(list)
    for s in subscribers:
        imei_subs[s.device.imei].append(s)
    shared = [grp for grp in imei_subs.values() if len(grp) > 1]

    print("\n" + "=" * 64)
    print(" SAMPLE NUMBERS TO SEARCH IN THE DASHBOARD (http://localhost:3000)")
    print("=" * 64)

    top = sorted(subscribers, key=lambda s: degree.get(s.number, 0), reverse=True)[:5]
    print(" Well-connected subscribers (rich contact network):")
    for s in top:
        print(f"   {s.number}  {s.name:<22} {s.operator:<14} contacts≈{degree.get(s.number,0)}")

    if shared:
        print(" Shared-device pair (try either — they share one IMEI):")
        grp = max(shared, key=lambda g: sum(degree.get(x.number, 0) for x in g))
        for s in grp:
            print(f"   {s.number}  {s.name:<22} {s.operator:<14} IMEI {s.device.imei}")
    print("-" * 64)
    print(" Analyst login (auth is ON): agent.alem / insa-demo")
    print(" These targets have active warrants; other numbers return 403.")
    print("=" * 64 + "\n")


def _batched(fn, rows: list[dict], size: int, label: str) -> None:
    for i in range(0, len(rows), size):
        fn(rows[i:i + size])
        print(f"[memgraph] {label}: {min(i + size, len(rows)):,}/{len(rows):,}")


if __name__ == "__main__":
    main()
