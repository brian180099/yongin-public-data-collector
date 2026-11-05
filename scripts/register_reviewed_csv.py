"""Register explicitly reviewed Yongin CSV contracts in collector.datasets."""

import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from yongin_collector.csv_allowlist import CSV_ALLOWLIST, CSV_CONTRACTS, ZIP_CSV_CONTRACTS
from yongin_collector.pipeline import prepare_csv_snapshot
from yongin_collector.store import Store

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    store = Store()
    eligible = []
    for portal_id, (name, domain) in CSV_ALLOWLIST.items():
        if portal_id not in CSV_CONTRACTS:
            continue
        source_id = f"portal_csv_{portal_id}"
        items = list(store.manifest(source_id)["items"].values())
        if len(items) != 1 or not items[0]["filename"].endswith(".csv"):
            raise ValueError(f"expected one validated CSV for {source_id}")
        key_columns, reference_column = CSV_CONTRACTS[portal_id]
        raw = (store.raw / source_id / items[0]["filename"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != items[0]["sha256"]:
            raise ValueError(f"raw hash mismatch for {source_id}")
        prepare_csv_snapshot(
            raw, unique_key_columns=list(key_columns),
            required_columns=list(key_columns) +
            ([reference_column] if reference_column else []),
            reference_date_column=reference_column,
        )
        eligible.append((source_id, portal_id, name, domain, key_columns, reference_column))
    for member_id, (portal_id, marker, key_columns, reference_column) in ZIP_CSV_CONTRACTS.items():
        source_id = f"portal_zip_{member_id}"
        items = list(store.manifest(source_id)["items"].values())
        if len(items) != 1 or not items[0]["filename"].endswith(".csv"):
            raise ValueError(f"expected one validated ZIP CSV for {source_id}")
        raw = (store.raw / source_id / items[0]["filename"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != items[0]["sha256"]:
            raise ValueError(f"raw hash mismatch for {source_id}")
        archive = items[0].get("response", {})
        if archive.get("archive_source_id") != f"portal_csv_{portal_id}":
            raise ValueError(f"ZIP archive provenance missing for {source_id}")
        prepare_csv_snapshot(
            raw, unique_key_columns=list(key_columns),
            required_columns=list(key_columns) + [reference_column],
            reference_date_column=reference_column,
        )
        name, domain = CSV_ALLOWLIST[portal_id]
        eligible.append((source_id, portal_id, f"{name} / {marker}", domain,
                         key_columns, reference_column))
    print(f"reviewed_csv_count={len(eligible)}")
    if not args.apply:
        return 0
    load_dotenv(ROOT / ".env")
    dsn = os.getenv("SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError("SUPABASE_DB_URL is missing")
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.transaction():
            for source_id, portal_id, name, domain, key_columns, reference_column in eligible:
                url = f"https://www.data.go.kr/data/{portal_id}/fileData.do"
                conn.execute("""insert into collector.datasets(
                    dataset_id, display_name, domain, provider, portal_url,
                    access_method, source_url, update_frequency, full_snapshot,
                    active, unique_key_columns, required_columns,
                    reference_date_column, check_interval_days, metadata
                ) values (%s,%s,%s,'경기도 용인시',%s,'file',%s,'검증 중',true,
                          false,%s,%s,%s,90,
                          '{"scope":"용인시 생활여가·문화·체육 CSV","contract":"원본 검사 완료; 예약 활성화 전 재검토"}'::jsonb)
                on conflict (dataset_id) do nothing""", (
                    source_id, name, domain, url, url,
                    list(key_columns), list(key_columns) +
                    ([reference_column] if reference_column else []), reference_column,
                ))
    print("registered=reviewed CSV datasets; automatic collection remains inactive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
