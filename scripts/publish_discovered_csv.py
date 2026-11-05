"""Register and publish structurally validated City CSVs without dropping duplicates."""

import argparse
import hashlib
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb

from yongin_collector.pipeline import run_collection
from yongin_collector.store import Store, atomic_write


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data" / "state" / "portal_search_inventory.json"
PROFILE = ROOT / "data" / "state" / "portal_bulk_profile.json"
ZIP_PROFILE = ROOT / "data" / "state" / "portal_bulk_zip_profile.json"
STATUS = ROOT / "data" / "state" / "portal_bulk_publication.json"
LOCAL_STATUS = ROOT / "data" / "state" / "portal_bulk_publication_local.json"


def eligible() -> list[tuple[dict, dict]]:
    rows = {x["portal_id"]: x for x in json.loads(INVENTORY.read_text(encoding="utf-8"))["datasets"]}
    profiles = json.loads(PROFILE.read_text(encoding="utf-8"))
    candidates = []
    store = Store()
    for portal_id, profile in profiles.items():
        if profile["status"] != "ready":
            continue
        source = rows[portal_id]
        if source["provider"] != "경기도 용인시" or "CSV" not in source["extensions"]:
            raise ValueError("inventory provider or extension mismatch")
        source_id = f"portal_csv_{portal_id}"
        items = list(store.manifest(source_id)["items"].values())
        if len(items) != 1 or not items[0]["filename"].endswith(".csv"):
            raise ValueError("raw manifest mismatch")
        raw = (store.raw / source_id / items[0]["filename"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != items[0]["sha256"]:
            raise ValueError("raw hash mismatch")
        candidates.append(({**source, "source_id": source_id}, profile))
    if ZIP_PROFILE.exists():
        for source_id, profile in json.loads(ZIP_PROFILE.read_text(encoding="utf-8")).items():
            if profile["status"] != "ready":
                continue
            source = rows[profile["portal_id"]]
            items = list(store.manifest(source_id)["items"].values())
            if len(items) != 1 or not items[0]["filename"].endswith(".csv"):
                raise ValueError("ZIP member manifest mismatch")
            if items[0].get("response", {}).get("archive_source_id") != f"portal_csv_{profile['portal_id']}":
                raise ValueError("ZIP provenance mismatch")
            parent = list(store.manifest(f"portal_csv_{profile['portal_id']}")["items"].values())
            if len(parent) != 1:
                raise ValueError("ZIP parent manifest mismatch")
            with zipfile.ZipFile(store.raw / f"portal_csv_{profile['portal_id']}" / parent[0]["filename"]) as archive:
                large_archive = sum(member.file_size for member in archive.infolist()) > 50_000_000
            raw = (store.raw / source_id / items[0]["filename"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != items[0]["sha256"]:
                raise ValueError("ZIP member hash mismatch")
            candidates.append(({**source, "source_id": source_id,
                                "large_archive": large_archive,
                                "title": source["title"] + " / " + profile["member_name"]}, profile))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--local", action="store_true", help="publish to the local PostgreSQL copy")
    args = parser.parse_args()
    candidates = eligible()
    selected = sorted(((s, p) for s, p in candidates if p["rows"] <= args.max_rows),
                      key=lambda item: item[1]["rows"])
    print(f"ready={len(candidates)} selected={len(selected)} rows={sum(p['rows'] for _, p in selected)}")
    if not args.apply:
        return
    secret = dotenv_values(ROOT / ".runtime" / ("local-host.env" if args.local else "collector.env"))
    dsn = secret.get("WRITER_URL" if args.local else "SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError("collector writer URL is missing")
    os.environ["SUPABASE_DB_URL"] = dsn
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        if conn.execute("select session_user").fetchone()[0] != "yongin_collector_login":
            raise RuntimeError("collector writer account required")
        with conn.transaction():
            for source, profile in candidates:
                source_id = source["source_id"]
                conn.execute("""insert into collector.datasets (
                    dataset_id, display_name, domain, provider, portal_url,
                    access_method, source_url, update_frequency, full_snapshot,
                    active, unique_key_columns, required_columns,
                    reference_date_column, check_interval_days, metadata
                ) values (%s,%s,'기타',%s,%s,'file',%s,'검증 중',true,
                          false,%s,%s,null,90,%s)
                on conflict (dataset_id) do nothing""",
                (source_id, source["title"], source["provider"], source["url"], source["url"],
                 ["__content_hash_occurrence"], ["__content_hash_occurrence"],
                 Jsonb({"key_strategy": "content_hash_occurrence", "scope": "용인시 제공 파일데이터 CSV",
                        "searched_keywords": source["keywords"], "profile_rows": profile["rows"],
                        "duplicate_rows_preserved": profile["duplicate_rows"],
                        **({"portal_id": source["portal_id"], "member_name": profile["member_name"],
                            "large_archive": source["large_archive"]}
                           if "member_name" in profile else {})})))
    status_path = LOCAL_STATUS if args.local else STATUS
    if args.local and not status_path.exists() and STATUS.exists():
        remote = json.loads(STATUS.read_text(encoding="utf-8"))["results"]
        with psycopg.connect(dsn) as conn:
            counts = dict(conn.execute("""select dataset_id, count(*) from collector.dataset_records
                                          where active and dataset_id = any(%s) group by dataset_id""",
                                       (list(remote),)).fetchall())
        copied = {key: value for key, value in remote.items()
                  if value["status"] in ("success", "no_change") and counts.get(key) == value["rows"]}
        atomic_write(status_path, (json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(),
                                              "results": copied}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    prior = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {"results": {}}
    results = prior["results"]
    pending = [(s, p) for s, p in selected if results.get(s["source_id"], {}).get("status") not in ("success", "no_change")]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_collection, s["source_id"], reuse_collected=True): (s, p)
                   for s, p in pending}
        for index, future in enumerate(as_completed(futures), 1):
            source, profile = futures[future]
            source_id = source["source_id"]
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = {"status": "failed", "error_code": type(exc).__name__,
                           "error_message": "publication failed before a run result"}
            results[source_id] = {"status": outcome["status"], "rows": profile["rows"],
                                  "error_code": outcome.get("error_code"),
                                  "error_message": outcome.get("error_message")}
            atomic_write(status_path, (json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(),
                                              "results": results}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            if index % 10 == 0 or outcome["status"] == "failed" or index == len(pending):
                print(f"processed={index}/{len(pending)} success={sum(x['status'] in ('success','no_change') for x in results.values())} failed={sum(x['status']=='failed' for x in results.values())}", flush=True)


if __name__ == "__main__":
    main()
