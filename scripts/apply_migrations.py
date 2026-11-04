"""Check or apply versioned collector migrations without printing credentials."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="apply pending migrations; default is read-only check")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    dsn = (os.getenv("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        print("SUPABASE_DB_URL is missing")
        return 2

    with psycopg.connect(dsn, connect_timeout=15, autocommit=True) as connection:
        if args.apply:
            connection.execute("create schema if not exists collector")
            connection.execute("""
                create table if not exists collector.schema_migrations (
                  migration_name text primary key,
                  sha256 char(64) not null,
                  applied_at timestamptz not null default now()
                )
            """)
        existing: dict[str, str] = {}
        schema_exists = connection.execute("""
            select exists(
              select 1 from information_schema.tables
              where table_schema = 'collector'
                and table_name = 'schema_migrations'
            )
        """).fetchone()[0]
        if schema_exists:
            existing = dict(connection.execute(
                "select migration_name, sha256 from collector.schema_migrations"
            ).fetchall())

        pending = 0
        for path in migration_files():
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            recorded = existing.get(path.name)
            if recorded and recorded != digest:
                print(f"modified applied migration: {path.name}")
                return 3
            if recorded:
                print(f"applied: {path.name}")
                continue
            pending += 1
            if not args.apply:
                print(f"pending: {path.name}")
                continue
            connection.execute(payload.decode("utf-8"))
            connection.execute(
                "insert into collector.schema_migrations(migration_name, sha256) "
                "values (%s, %s)", (path.name, digest)
            )
            print(f"applied: {path.name}")
        print(f"pending_count={0 if args.apply else pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
