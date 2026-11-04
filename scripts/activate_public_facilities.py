"""Enable the approved facility source only after a complete healthy DB run."""

from dotenv import load_dotenv
import os
import psycopg

from yongin_collector.store import ROOT


def main() -> int:
    load_dotenv(ROOT / ".runtime" / "collector.env")
    dsn = os.getenv("SUPABASE_DB_URL")
    if not dsn:
        raise SystemExit("collector database login is missing")
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.transaction():
            run = conn.execute("""
                select status, source_record_count, quality_summary
                from collector.collection_runs
                where dataset_id = 'public_facilities'
                order by started_at desc limit 1
            """).fetchone()
            count = conn.execute("""
                select count(*) from collector.dataset_records
                where dataset_id = 'public_facilities' and active
            """).fetchone()[0]
            pages = conn.execute("""
                select count(*) from collector.raw_artifacts
                where dataset_id = 'public_facilities'
            """).fetchone()[0]
            if (not run or run[0] not in ("success", "no_change") or
                    not run[2].get("passed") or count == 0 or
                    count != run[1] or pages < run[2].get("pages", 0)):
                raise SystemExit("facility source is not ready for scheduled collection")
            conn.execute("""
                update collector.datasets set active = true, updated_at = now()
                where dataset_id = 'public_facilities'
            """)
    print(f"public_facilities active=true, validated_records={count}, raw_pages={pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
