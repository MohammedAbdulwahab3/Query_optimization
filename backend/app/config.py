"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file).
The most important one is ``CH_BACKEND`` which selects how we talk to
ClickHouse:

* ``embedded`` – use the in-process ``chdb`` engine. This is the ClickHouse
  query engine compiled as a Python library, so the SQL dialect is identical
  to a real server. It needs zero external services and is perfect for local
  "self-use" runs.
* ``server``   – connect to a real ``clickhouse-server`` over HTTP using the
  official ``clickhouse-connect`` driver. This is what ``docker-compose`` uses
  for a production-style deployment.

Both backends run the exact same analytics SQL.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which ClickHouse backend to use: "embedded" (chdb) or "server".
    ch_backend: str = "embedded"

    # --- clickhouse-server (used when ch_backend == "server") ---
    ch_host: str = "localhost"
    ch_port: int = 8123
    ch_user: str = "default"
    ch_password: str = ""

    # --- embedded chdb (used when ch_backend == "embedded") ---
    chdb_path: str = "./data/chdb"

    # Logical database that holds all tables (always fully-qualified in SQL).
    ch_database: str = "analytics"

    # --- seed / sample-data controls ---
    auto_seed: bool = True          # populate sample data on startup if empty
    seed_sessions: int = 500_000    # number of synthetic sessions to generate
    seed_users: int = 50_000        # size of the users dimension
    seed_products: int = 500        # size of the products dimension
    seed_days: int = 90             # spread events across the last N days

    # Where the bundled static frontend lives (relative to repo root).
    frontend_dir: str = "frontend"


@lru_cache
def get_settings() -> Settings:
    return Settings()
