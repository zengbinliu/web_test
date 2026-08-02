"""Shared database configuration for schema discovery and SQL execution."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url


DEMO_ROOT = Path(__file__).resolve().parent
ENV_PATH = DEMO_ROOT / ".env"

load_dotenv(ENV_PATH, override=False)


def get_database_url() -> URL:
    """Return a SQLAlchemy URL from DATABASE_URL or legacy DB_* variables."""
    configured_url = os.getenv("DATABASE_URL", "").strip()
    if configured_url:
        return make_url(configured_url)

    driver_name = os.getenv("DB_DIALECT", "mysql+mysqlconnector").strip()
    database = os.getenv("DB_NAME", "").strip()
    if not database:
        raise RuntimeError("未配置 DATABASE_URL 或 DB_NAME")

    if driver_name.startswith("sqlite"):
        if database != ":memory:":
            database_path = Path(database)
            if not database_path.is_absolute():
                database_path = (DEMO_ROOT / database_path).resolve()
            database = str(database_path)
        return URL.create(drivername=driver_name, database=database)

    raw_port = os.getenv("DB_PORT", "").strip()
    return URL.create(
        drivername=driver_name,
        username=os.getenv("DB_USER") or None,
        password=os.getenv("DB_PASSWORD") or None,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(raw_port) if raw_port else None,
        database=database,
    )


def create_database_engine():
    return create_engine(get_database_url(), pool_pre_ping=True)


def get_configured_schema() -> Optional[str]:
    return os.getenv("DB_SCHEMA", "").strip() or None


def get_backend_name() -> str:
    return get_database_url().get_backend_name()


def get_sqlglot_dialect(backend_name: Optional[str] = None) -> Optional[str]:
    backend = (backend_name or get_backend_name()).lower()
    return {
        "mysql": "mysql",
        "mariadb": "mysql",
        "postgresql": "postgres",
        "sqlite": "sqlite",
        "mssql": "tsql",
        "oracle": "oracle",
        "duckdb": "duckdb",
        "snowflake": "snowflake",
        "bigquery": "bigquery",
    }.get(backend)


def get_dialect_label(backend_name: Optional[str] = None) -> str:
    backend = (backend_name or get_backend_name()).lower()
    return {
        "mysql": "MySQL",
        "mariadb": "MariaDB",
        "postgresql": "PostgreSQL",
        "sqlite": "SQLite",
        "mssql": "SQL Server",
        "oracle": "Oracle",
        "duckdb": "DuckDB",
        "snowflake": "Snowflake",
        "bigquery": "BigQuery",
    }.get(backend, backend)
