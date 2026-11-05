"""Activate only validated CSV datasets with a successful DB baseline."""

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from yongin_collector.csv_allowlist import CSV_CONTRACTS, ZIP_CSV_CONTRACTS
from yongin_collector.sources import SOURCES


ROOT = Path(__file__).resolve().parents[1]


def reviewed_ids() -> list[str]:
    return ([f"portal_csv_{portal_id}" for portal_id in CSV_CONTRACTS]
            + [f"portal_zip_{member_id}" for member_id in ZIP_CSV_CONTRACTS])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    dsn = os.getenv("SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    ids = reviewed_ids()
    if len(ids) != 57 or len(set(ids)) != len(ids) or any(i not in SOURCES for i in ids):
        raise ValueError("reviewed source registry is incomplete")
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        rows = conn.execute("""select d.dataset_id, d.active, d.last_success_at,
                              (select count(*) from collector.dataset_records r
                               where r.dataset_id=d.dataset_id and r.active) as row_count,
                              (select status from collector.collection_runs c
                               where c.dataset_id=d.dataset_id
                               order by c.started_at desc limit 1) as latest_status
                              from collector.datasets d where d.dataset_id = any(%s)""",
                            (ids,)).fetchall()
        by_id = {row[0]: row for row in rows}
        missing = set(ids) - set(by_id)
        if missing:
            raise ValueError(f"datasets not registered: {len(missing)}")
        unsafe = [dataset_id for dataset_id, row in by_id.items()
                  if not row[2] or row[3] < 1 or row[4] not in ("success", "no_change")]
        if unsafe:
            raise ValueError(f"datasets lack successful baseline: {unsafe}")
        inactive = [dataset_id for dataset_id in ids if not by_id[dataset_id][1]]
        print(f"reviewed={len(ids)} ready={len(rows)} inactive={len(inactive)}")
        if args.apply and inactive:
            with conn.transaction():
                conn.execute("""update collector.datasets set active=true, updated_at=now()
                                where dataset_id = any(%s)""", (inactive,))
            print(f"activated={len(inactive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
