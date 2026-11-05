"""Stream-validate and publish large City CSV baselines to local PostgreSQL only."""

import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb

from yongin_collector.pipeline import _canonical_hash
from yongin_collector.store import Store, atomic_write


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/state/portal_large_publication_local.json"
PROFILE = ROOT / "data/state/portal_large_profile.json"
ZIP_PROFILE = ROOT / "data/state/portal_large_zip_profile.json"
IRREGULAR_PROFILE = ROOT / "data/state/portal_irregular_profile.json"
INVENTORY = ROOT / "data/state/portal_search_inventory.json"


def publish(dataset_id: str, profile: dict, source: dict, dsn: str) -> dict:
    artifacts = list(Store().manifest(dataset_id)["items"].values())
    if len(artifacts) != 1:
        raise ValueError("raw manifest is ambiguous")
    artifact = artifacts[0]
    path = Store().raw / dataset_id / artifact["filename"]
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != artifact["sha256"]:
            raise ValueError("raw hash mismatch")
    reference = date.fromisoformat(artifact["reference_date"]) if artifact.get("reference_date") else None
    with psycopg.connect(dsn) as conn:
        conn.execute("""insert into collector.datasets (
            dataset_id, display_name, domain, provider, portal_url, access_method,
            source_url, update_frequency, full_snapshot, active, unique_key_columns,
            required_columns, reference_date_column, check_interval_days, metadata
        ) values (%s,%s,'기타',%s,%s,'file',%s,'검증 중',true,false,%s,%s,null,90,%s)
        on conflict (dataset_id) do nothing""",
        (dataset_id, source["title"], source["provider"], source["url"], source["url"],
         ["__content_hash_occurrence"], ["__content_hash_occurrence"],
         Jsonb({"key_strategy": "content_hash_occurrence", "large_streaming": True,
                "scope": "용인시 제공 파일데이터 CSV", "profile_rows": profile["rows"],
                "header_repaired": bool(profile.get("header_repaired")),
                "skipped_empty_rows": profile.get("skipped_empty_rows", 0),
                **({"portal_id": source["portal_id"], "member_name": profile["member_name"],
                    "large_archive": True} if "member_name" in profile else {})})))
        current = conn.execute("select count(*) from collector.dataset_records where dataset_id=%s and active",
                               (dataset_id,)).fetchone()[0]
        if current:
            if current != profile["rows"]:
                raise ValueError("existing row count differs from reviewed profile")
            return {"status": "existing", "rows": current}
    with psycopg.connect(dsn, autocommit=True) as conn:
        run_id = conn.execute("""insert into collector.collection_runs(dataset_id,trigger_type,status)
                                 values (%s,'manual','running') returning run_id""",
                              (dataset_id,)).fetchone()[0]
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                locked = conn.execute("select pg_try_advisory_xact_lock(hashtext(%s))", (dataset_id,)).fetchone()[0]
                if not locked:
                    raise ValueError("concurrent dataset load")
                if conn.execute("select exists(select 1 from collector.dataset_records where dataset_id=%s)",
                                (dataset_id,)).fetchone()[0]:
                    raise ValueError("dataset already has records")
                conn.execute("""create temporary table staging (
                    record_key text primary key, payload jsonb not null, payload_hash char(64) not null
                ) on commit drop""")
                occurrences: Counter[str] = Counter()
                count = 0
                with path.open("r", encoding=profile["encoding"], newline="") as handle:
                    reader = csv.reader(handle, strict=True)
                    original_headers = next(reader)
                    headers = ([name.strip() for name in original_headers]
                               if not profile.get("header_repaired") else profile["headers"])
                    if (headers != profile["headers"] or
                            ("original_headers" in profile and original_headers != profile["original_headers"])):
                        raise ValueError("headers changed since profile")
                    skipped_empty = 0
                    with conn.cursor().copy("copy staging(record_key,payload,payload_hash) from stdin") as copy:
                        for row in reader:
                            if not row or all(not value.strip() for value in row):
                                if profile.get("skipped_empty_rows", 0):
                                    skipped_empty += 1
                                    continue
                                raise ValueError("unexpected empty record")
                            if len(row) != len(headers):
                                raise ValueError("row structure changed since profile")
                            payload = {key: value.strip() or None for key, value in zip(headers, row)}
                            digest = _canonical_hash(payload)
                            occurrences[digest] += 1
                            copy.write_row((f"{digest}:{occurrences[digest]}", Jsonb(payload), digest))
                            count += 1
                if count != profile["rows"] or skipped_empty != profile.get("skipped_empty_rows", 0):
                    raise ValueError("row count changed since profile")
                conn.execute("""insert into collector.dataset_records (
                    dataset_id,record_key,payload,payload_hash,reference_date,active,
                    first_seen_run_id,last_changed_run_id,last_seen_run_id
                ) select %s,record_key,payload,payload_hash,%s,true,%s,%s,%s from staging""",
                (dataset_id, reference, run_id, run_id, run_id))
                conn.execute("""insert into collector.change_history (
                    run_id,dataset_id,record_key,change_type,new_payload
                ) select %s,%s,record_key,'baseline',payload from staging""", (run_id, dataset_id))
                conn.execute("""insert into collector.raw_artifacts (
                    run_id,dataset_id,sha256,byte_count,content_type,original_filename,
                    collected_at,reference_date,local_path
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (dataset_id,sha256) do nothing""",
                (run_id, dataset_id, artifact["sha256"], artifact["byte_count"],
                 artifact.get("content_type"), artifact.get("original_filename"),
                 artifact["collected_at"], reference, f"raw/{dataset_id}/{artifact['filename']}"))
                quality = {"passed": True, "encoding": profile["encoding"],
                           "column_count": len(headers), "record_count": count,
                           "duplicate_row_count": sum(x - 1 for x in occurrences.values()),
                           "key_strategy": "content_hash_occurrence", "streamed": True,
                           "skipped_empty_rows": skipped_empty,
                           "header_repaired": bool(profile.get("header_repaired")),
                           "headers": headers}
                conn.execute("""update collector.collection_runs set status='success',
                    is_baseline=true, finished_at=now(), collected_at=%s, reference_date=%s,
                    source_record_count=%s, baseline_count=%s, raw_sha256=%s,
                    raw_path=%s, quality_summary=%s where run_id=%s""",
                    (artifact["collected_at"], reference, count, count, artifact["sha256"],
                     f"raw/{dataset_id}/{artifact['filename']}", Jsonb(quality), run_id))
                conn.execute("""update collector.datasets set last_success_at=now(),
                    next_check_at=now()+make_interval(days=>check_interval_days), updated_at=now()
                    where dataset_id=%s""", (dataset_id,))
        return {"status": "success", "rows": count, "duplicate_rows": quality["duplicate_row_count"]}
    except Exception as exc:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("""update collector.collection_runs set status='failed',
                finished_at=now(), error_code=%s, error_message=%s where run_id=%s""",
                (type(exc).__name__, str(exc)[:200], run_id))
        return {"status": "failed", "error_code": type(exc).__name__, "message": str(exc)[:200]}


def main() -> None:
    dsn = dotenv_values(ROOT / ".runtime/local-host.env").get("WRITER_URL")
    if not dsn:
        raise RuntimeError("local writer URL missing")
    with psycopg.connect(dsn) as conn:
        if conn.execute("select session_user").fetchone()[0] != "yongin_collector_login":
            raise RuntimeError("local writer account required")
    inventory = {x["portal_id"]: x for x in json.loads(INVENTORY.read_text(encoding="utf-8"))["datasets"]}
    profiles = json.loads(PROFILE.read_text(encoding="utf-8"))
    if ZIP_PROFILE.exists():
        profiles.update(json.loads(ZIP_PROFILE.read_text(encoding="utf-8")))
    if IRREGULAR_PROFILE.exists():
        profiles.update(json.loads(IRREGULAR_PROFILE.read_text(encoding="utf-8")))
    prior = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for key, profile in sorted(profiles.items(), key=lambda item: item[1].get("rows", 0)):
        if profile["status"] != "ready" or prior.get(key, {}).get("status") in ("success", "existing"):
            continue
        portal_id = profile.get("portal_id", key.removeprefix("portal_csv_"))
        source = inventory[portal_id].copy()
        if source["provider"] != "경기도 용인시":
            raise ValueError("provider mismatch")
        dataset_id = key if key.startswith(("portal_csv_", "portal_zip_")) else f"portal_csv_{key}"
        if "member_name" in profile:
            member_name = profile["member_name"]
            try:
                display_name = member_name.encode("cp437").decode("cp949")
            except (UnicodeError, LookupError):
                display_name = member_name
            source["title"] += " / " + display_name
        result = publish(dataset_id, profile, source, dsn)
        prior[key] = result
        atomic_write(STATE, (json.dumps(prior, ensure_ascii=False, indent=2) + "\n").encode())
        print(key, result["status"], result.get("rows", 0), flush=True)


if __name__ == "__main__":
    main()
