"""Validated snapshot comparison and transactional Supabase publication."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .collect import collect
from .sources import SOURCES
from .store import Store


class PipelineError(RuntimeError):
    code = "PIPELINE_ERROR"


class QualityError(PipelineError):
    code = "QUALITY_FAILED"


class ConcurrentRunError(PipelineError):
    code = "CONCURRENT_RUN"


@dataclass(frozen=True)
class PreparedSnapshot:
    records: dict[str, dict[str, Any]]
    hashes: dict[str, str]
    reference_date: date | None
    quality: dict[str, Any]


def _db_url() -> str:
    value = (os.getenv("SUPABASE_DB_URL") or "").strip()
    if not value:
        raise PipelineError("SUPABASE_DB_URL is missing")
    return value


def _decode_csv(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise QualityError("CSV encoding is neither UTF-8 nor CP949")


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def prepare_csv_snapshot(content: bytes, *, unique_key_columns: list[str],
                         required_columns: list[str],
                         reference_date_column: str | None) -> PreparedSnapshot:
    text, encoding = _decode_csv(content)
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    missing_columns = sorted(set(required_columns) - set(headers))
    if missing_columns:
        raise QualityError(f"required columns missing: {', '.join(missing_columns)}")

    records: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    duplicate_keys: list[str] = []
    missing_required = 0
    reference_dates: set[date] = set()
    for raw in reader:
        row = {
            key.strip(): (value.strip() or None) if isinstance(value, str) else value
            for key, value in raw.items() if key is not None
        }
        if any(row.get(column) is None for column in required_columns):
            missing_required += 1
            continue
        key_parts = [str(row.get(column) or "") for column in unique_key_columns]
        if any(not value for value in key_parts):
            missing_required += 1
            continue
        record_key = "\x1f".join(key_parts)
        if record_key in records:
            duplicate_keys.append(record_key)
            continue
        if reference_date_column and row.get(reference_date_column):
            try:
                reference_dates.add(date.fromisoformat(str(row[reference_date_column])))
            except ValueError as exc:
                raise QualityError("reference date is not ISO YYYY-MM-DD") from exc
        for date_column in ("시작일", "종료일"):
            if row.get(date_column):
                try:
                    date.fromisoformat(str(row[date_column]))
                except ValueError as exc:
                    raise QualityError(f"{date_column} is not ISO YYYY-MM-DD") from exc
        records[record_key] = row
        hashes[record_key] = _canonical_hash(row)

    if missing_required:
        raise QualityError(f"required values missing in {missing_required} rows")
    if duplicate_keys:
        raise QualityError(f"duplicate record keys: {len(duplicate_keys)}")
    if not records:
        raise QualityError("snapshot contains no records")
    if len(reference_dates) > 1:
        raise QualityError("snapshot contains multiple reference dates")
    return PreparedSnapshot(
        records=records,
        hashes=hashes,
        reference_date=next(iter(reference_dates), None),
        quality={
            "passed": True,
            "encoding": encoding,
            "column_count": len(headers),
            "record_count": len(records),
            "duplicate_key_count": 0,
            "missing_required_count": 0,
            "headers": headers,
        },
    )


def compare_snapshot(snapshot: PreparedSnapshot,
                     previous: dict[str, dict[str, Any]], *,
                     full_snapshot: bool) -> dict[str, list[str]]:
    current_keys = set(snapshot.records)
    previous_active = {key for key, value in previous.items() if value["active"]}
    added = [
        key for key in current_keys
        if key not in previous or not previous[key]["active"]
    ]
    modified = [
        key for key in current_keys & previous_active
        if snapshot.hashes[key] != previous[key]["payload_hash"]
    ]
    unchanged = [
        key for key in current_keys & previous_active
        if snapshot.hashes[key] == previous[key]["payload_hash"]
    ]
    deleted = sorted(previous_active - current_keys) if full_snapshot else []
    return {
        "added": sorted(added), "modified": sorted(modified),
        "unchanged": sorted(unchanged), "deleted_candidate": deleted,
    }


def validate_deletion_rate(active_before: int, deleted_count: int) -> None:
    if (active_before and deleted_count > 5 and
            deleted_count / active_before > 0.30):
        raise QualityError(f"mass deletion blocked: {deleted_count}/{active_before}")


def _latest_artifact(store: Store, dataset_id: str) -> tuple[dict, Path]:
    items = list(store.manifest(dataset_id)["items"].values())
    if not items:
        raise PipelineError("collector produced no artifact")
    metadata = max(items, key=lambda item: item["collected_at"])
    path = store.raw / dataset_id / metadata["filename"]
    if not path.is_file():
        raise PipelineError("manifest artifact is missing")
    return metadata, path


def _safe_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, PipelineError):
        return exc.code, str(exc)[:500]
    if isinstance(exc, ValueError):
        return "SOURCE_VALIDATION_FAILED", str(exc)[:500]
    return type(exc).__name__.upper(), "collection failed; inspect local service logs"


def _create_run(dataset_id: str, trigger_type: str) -> str:
    with psycopg.connect(
        _db_url(), connect_timeout=15, autocommit=True, row_factory=dict_row
    ) as conn:
        row = conn.execute("""
            insert into collector.collection_runs(dataset_id, trigger_type, status)
            values (%s, %s, 'running') returning run_id
        """, (dataset_id, trigger_type)).fetchone()
        return str(row["run_id"])


def _mark_failed(run_id: str, exc: Exception) -> dict[str, Any]:
    code, message = _safe_error(exc)
    with psycopg.connect(_db_url(), connect_timeout=15, autocommit=True) as conn:
        conn.execute("""
            update collector.collection_runs
            set status = 'failed', finished_at = now(),
                error_code = %s, error_message = %s
            where run_id = %s
        """, (code, message, run_id))
    return {"run_id": run_id, "status": "failed", "error_code": code,
            "error_message": message}


def list_due_datasets(force: bool = False) -> list[dict[str, Any]]:
    with psycopg.connect(
        _db_url(), connect_timeout=15, row_factory=dict_row
    ) as conn:
        rows = conn.execute("""
            select dataset_id, display_name, access_method, update_frequency,
                   next_check_at, last_success_at
            from collector.datasets
            where active and (%s or next_check_at <= now())
            order by dataset_id
        """, (force,)).fetchall()
        return [dict(row) for row in rows]


def run_collection(dataset_id: str, trigger_type: str = "manual") -> dict[str, Any]:
    if trigger_type not in {"manual", "schedule", "retry"}:
        raise ValueError("invalid trigger type")
    with psycopg.connect(
        _db_url(), connect_timeout=15, row_factory=dict_row
    ) as conn:
        dataset = conn.execute(
            "select * from collector.datasets where dataset_id = %s",
            (dataset_id,),
        ).fetchone()
    if not dataset:
        raise KeyError(dataset_id)
    run_id = _create_run(dataset_id, trigger_type)
    try:
        if dataset_id not in SOURCES:
            raise PipelineError("dataset has no collector implementation")
        source = SOURCES[dataset_id]
        store = Store()
        result = collect(
            source, store, os.getenv("DATA_GO_KR_SERVICE_KEY"), mode="daily"
        )
        store.record_checked(dataset_id, result)
        metadata, path = _latest_artifact(store, dataset_id)
        raw = path.read_bytes()
        if source.kind != "portal_file" or path.suffix.lower() != ".csv":
            raise PipelineError("operational parser is not implemented for this source")
        snapshot = prepare_csv_snapshot(
            raw,
            unique_key_columns=list(dataset["unique_key_columns"]),
            required_columns=list(dataset["required_columns"]),
            reference_date_column=dataset["reference_date_column"],
        )

        with psycopg.connect(
            _db_url(), connect_timeout=15, row_factory=dict_row
        ) as conn:
            with conn.transaction():
                locked = conn.execute(
                    "select pg_try_advisory_xact_lock(hashtext(%s)) as locked",
                    (dataset_id,),
                ).fetchone()["locked"]
                if not locked:
                    raise ConcurrentRunError("another run holds the dataset lock")
                previous_rows = conn.execute("""
                    select record_key, payload, payload_hash, active
                    from collector.dataset_records where dataset_id = %s
                """, (dataset_id,)).fetchall()
                previous = {row["record_key"]: dict(row) for row in previous_rows}
                changes = compare_snapshot(
                    snapshot, previous, full_snapshot=dataset["full_snapshot"]
                )
                baseline = not previous
                active_before = sum(1 for value in previous.values() if value["active"])
                deleted_count = len(changes["deleted_candidate"])
                validate_deletion_rate(active_before, deleted_count)

                changed_keys = changes["added"] + changes["modified"]
                if baseline:
                    changed_keys = sorted(snapshot.records)
                examples: list[dict[str, Any]] = []
                upsert_rows: list[dict[str, Any]] = []
                history_rows: list[dict[str, Any]] = []
                for key in changed_keys:
                    change_type = "baseline" if baseline else (
                        "added" if key in changes["added"] else "modified"
                    )
                    old_payload = previous.get(key, {}).get("payload")
                    new_payload = snapshot.records[key]
                    upsert_rows.append({
                        "record_key": key, "payload": new_payload,
                        "payload_hash": snapshot.hashes[key],
                    })
                    history_rows.append({
                        "record_key": key, "change_type": change_type,
                        "old_payload": old_payload, "new_payload": new_payload,
                    })
                    if len(examples) < 5:
                        examples.append({"record_key": key, "change_type": change_type})

                if upsert_rows:
                    conn.execute("""
                        with incoming as (
                          select * from jsonb_to_recordset(%s::jsonb) as value(
                            record_key text, payload jsonb, payload_hash text
                          )
                        )
                        insert into collector.dataset_records(
                          dataset_id, record_key, payload, payload_hash,
                          reference_date, active, first_seen_run_id,
                          last_changed_run_id, last_seen_run_id
                        )
                        select %s, record_key, payload, payload_hash, %s,
                               true, %s, %s, %s
                        from incoming
                        on conflict (dataset_id, record_key) do update set
                          payload = excluded.payload,
                          payload_hash = excluded.payload_hash,
                          reference_date = excluded.reference_date,
                          active = true,
                          last_changed_run_id = excluded.last_changed_run_id,
                          last_seen_run_id = excluded.last_seen_run_id,
                          updated_at = now()
                    """, (
                        Jsonb(upsert_rows), dataset_id, snapshot.reference_date,
                        run_id, run_id, run_id,
                    ))
                    conn.execute("""
                        with incoming as (
                          select * from jsonb_to_recordset(%s::jsonb) as value(
                            record_key text, change_type text,
                            old_payload jsonb, new_payload jsonb
                          )
                        )
                        insert into collector.change_history(
                          run_id, dataset_id, record_key, change_type,
                          old_payload, new_payload
                        )
                        select %s, %s, record_key, change_type,
                               old_payload, new_payload
                        from incoming
                    """, (Jsonb(history_rows), run_id, dataset_id))

                if changes["unchanged"]:
                    conn.execute("""
                        update collector.dataset_records
                        set last_seen_run_id = %s
                        where dataset_id = %s and record_key = any(%s)
                    """, (run_id, dataset_id, changes["unchanged"]))
                deleted_keys = changes["deleted_candidate"]
                if deleted_keys:
                    conn.execute("""
                        update collector.dataset_records
                        set active = false, last_changed_run_id = %s, updated_at = now()
                        where dataset_id = %s and record_key = any(%s)
                    """, (run_id, dataset_id, deleted_keys))
                    delete_history = [
                        {"record_key": key, "old_payload": previous[key]["payload"]}
                        for key in deleted_keys
                    ]
                    conn.execute("""
                        with incoming as (
                          select * from jsonb_to_recordset(%s::jsonb) as value(
                            record_key text, old_payload jsonb
                          )
                        )
                        insert into collector.change_history(
                          run_id, dataset_id, record_key, change_type, old_payload
                        )
                        select %s, %s, record_key, 'delete_candidate', old_payload
                        from incoming
                    """, (Jsonb(delete_history), run_id, dataset_id))
                for key in deleted_keys:
                    if len(examples) < 5:
                        examples.append({
                            "record_key": key, "change_type": "delete_candidate"
                        })

                baseline_count = len(snapshot.records) if baseline else 0
                added_count = 0 if baseline else len(changes["added"])
                modified_count = 0 if baseline else len(changes["modified"])
                change_count = added_count + modified_count + deleted_count
                status = "success" if baseline or change_count else "no_change"
                relative_path = f"raw/{dataset_id}/{metadata['filename']}"
                conn.execute("""
                    insert into collector.raw_artifacts(
                      run_id, dataset_id, sha256, byte_count, content_type,
                      original_filename, collected_at, reference_date, local_path
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (dataset_id, sha256) do nothing
                """, (
                    run_id, dataset_id, metadata["sha256"], metadata["byte_count"],
                    metadata.get("content_type"), metadata.get("original_filename"),
                    metadata["collected_at"], snapshot.reference_date, relative_path,
                ))
                conn.execute("""
                    update collector.collection_runs set
                      status=%s, is_baseline=%s, finished_at=now(),
                      collected_at=%s, reference_date=%s, source_record_count=%s,
                      baseline_count=%s, added_count=%s, modified_count=%s,
                      deleted_candidate_count=%s, unchanged_count=%s,
                      raw_sha256=%s, raw_path=%s, quality_summary=%s,
                      change_examples=%s
                    where run_id=%s
                """, (
                    status, baseline, metadata["collected_at"], snapshot.reference_date,
                    len(snapshot.records), baseline_count, added_count,
                    modified_count, deleted_count, len(changes["unchanged"]),
                    metadata["sha256"], relative_path, Jsonb(snapshot.quality),
                    Jsonb(examples), run_id,
                ))
                conn.execute("""
                    update collector.datasets set
                      last_success_at=now(),
                      next_check_at=now() + make_interval(days => check_interval_days),
                      updated_at=now()
                    where dataset_id=%s
                """, (dataset_id,))

        return {
            "run_id": run_id, "dataset_id": dataset_id, "status": status,
            "is_baseline": baseline, "source_record_count": len(snapshot.records),
            "baseline_count": baseline_count, "added_count": added_count,
            "modified_count": modified_count,
            "deleted_candidate_count": deleted_count,
            "unchanged_count": len(changes["unchanged"]),
            "change_examples": examples,
        }
    except Exception as exc:
        return _mark_failed(run_id, exc)
