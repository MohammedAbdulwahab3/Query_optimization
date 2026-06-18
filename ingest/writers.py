"""
I/O writers for the ingest job: batched inserts into ClickHouse and batched
MERGE/CREATE into Memgraph. Kept separate from generator.py so the data
generation stays pure and testable.
"""

from __future__ import annotations

import time

import clickhouse_connect
from neo4j import GraphDatabase

from generator import CDR_COLUMNS


# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------

class ClickHouseWriter:
    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str = "telecom"):
        self.database = database
        self.client = clickhouse_connect.get_client(
            host=host, port=port, username=user, password=password,
        )

    @classmethod
    def connect_with_retry(cls, host, port, user, password, database="telecom",
                           attempts=30, delay=2.0):
        last = None
        for i in range(attempts):
            try:
                w = cls(host, port, user, password, database)
                w.client.command("SELECT 1")
                return w
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"[clickhouse] not ready ({i + 1}/{attempts}): {e}")
                time.sleep(delay)
        raise RuntimeError(f"ClickHouse unavailable: {last}")

    def cdr_count(self) -> int:
        try:
            r = self.client.query(f"SELECT count() FROM {self.database}.cdr")
            return int(r.result_rows[0][0])
        except Exception:  # noqa: BLE001 — table may not exist yet
            return 0

    def insert_batch(self, rows: list[tuple]) -> None:
        self.client.insert(
            table="cdr",
            data=rows,
            column_names=CDR_COLUMNS,
            database=self.database,
        )


# ---------------------------------------------------------------------------
# Memgraph (Bolt-compatible — use the neo4j driver)
# ---------------------------------------------------------------------------

class MemgraphWriter:
    def __init__(self, uri: str, user: str = "", password: str = ""):
        auth = (user, password) if user else None
        self.driver = GraphDatabase.driver(uri, auth=auth)

    @classmethod
    def connect_with_retry(cls, uri, user="", password="", attempts=30, delay=2.0):
        last = None
        for i in range(attempts):
            try:
                w = cls(uri, user, password)
                w.run("RETURN 1")
                return w
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"[memgraph] not ready ({i + 1}/{attempts}): {e}")
                time.sleep(delay)
        raise RuntimeError(f"Memgraph unavailable: {last}")

    def run(self, cypher: str, **params):
        with self.driver.session() as s:
            return s.run(cypher, **params).data()

    def close(self):
        self.driver.close()

    def wipe(self):
        self.run("MATCH (n) DETACH DELETE n")

    def create_constraints(self):
        # Indexes make the MERGE-by-key path fast; constraints keep nodes unique.
        for stmt in (
            "CREATE INDEX ON :Subscriber(number)",
            "CREATE INDEX ON :Device(imei)",
            "CREATE INDEX ON :Cell(cell_id)",
        ):
            try:
                self.run(stmt)
            except Exception as e:  # noqa: BLE001 — already exists
                print(f"[memgraph] index note: {e}")

    # --- batched writers (UNWIND a list of dict rows) ---

    def merge_subscribers(self, rows: list[dict]):
        self.run(
            """
            UNWIND $rows AS r
            MERGE (s:Subscriber {number: r.number})
            SET s.name = r.name, s.imsi = r.imsi,
                s.operator = r.operator, s.reg_date = r.reg_date
            MERGE (d:Device {imei: r.imei})
            SET d.model = r.model
            MERGE (s)-[:USED]->(d)
            """,
            rows=rows,
        )

    def merge_cells(self, rows: list[dict]):
        self.run(
            """
            UNWIND $rows AS r
            MERGE (c:Cell {cell_id: r.cell_id})
            SET c.lat = r.lat, c.lon = r.lon, c.location_name = r.location_name
            """,
            rows=rows,
        )

    def merge_called(self, rows: list[dict]):
        self.run(
            """
            UNWIND $rows AS r
            MATCH (a:Subscriber {number: r.caller})
            MATCH (b:Subscriber {number: r.callee})
            MERGE (a)-[e:CALLED]->(b)
            SET e.calls = r.calls, e.total_duration = r.total_duration,
                e.start = r.start, e.duration = r.duration, e.type = r.type
            """,
            rows=rows,
        )

    def merge_connected_at(self, rows: list[dict]):
        self.run(
            """
            UNWIND $rows AS r
            MATCH (s:Subscriber {number: r.number})
            MATCH (c:Cell {cell_id: r.cell_id})
            MERGE (s)-[e:CONNECTED_AT]->(c)
            SET e.time = r.time, e.connections = r.connections
            """,
            rows=rows,
        )

    def counts(self) -> dict:
        out = {}
        out["subscribers"] = self.run("MATCH (s:Subscriber) RETURN count(s) AS n")[0]["n"]
        out["devices"] = self.run("MATCH (d:Device) RETURN count(d) AS n")[0]["n"]
        out["cells"] = self.run("MATCH (c:Cell) RETURN count(c) AS n")[0]["n"]
        out["called"] = self.run("MATCH ()-[e:CALLED]->() RETURN count(e) AS n")[0]["n"]
        out["connected_at"] = self.run(
            "MATCH ()-[e:CONNECTED_AT]->() RETURN count(e) AS n"
        )[0]["n"]
        return out
