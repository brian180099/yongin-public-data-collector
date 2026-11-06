"""Small process-local pool for read-only Supabase analysis connections."""

from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


@lru_cache(maxsize=4)
def analysis_pool(dsn: str) -> ConnectionPool:
    """Reuse TLS/database sessions while keeping transactions request-scoped."""
    return ConnectionPool(
        conninfo=dsn,
        min_size=0,
        max_size=4,
        timeout=10,
        kwargs={"connect_timeout": 10, "row_factory": dict_row},
        open=True,
        name="yongin-analysis",
    )
