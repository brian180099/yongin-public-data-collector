"""Save official files for newly discovered Yongin City CSV-badged datasets."""

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

from yongin_collector.collect import collect_portal_file
from yongin_collector.csv_allowlist import CSV_ALLOWLIST
from yongin_collector.sources import Source
from yongin_collector.store import Store


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data" / "state" / "portal_search_inventory.json"
STATUS = ROOT / "data" / "state" / "portal_bulk_collection.json"


def collect(row: dict) -> dict:
    portal_id = row["portal_id"]
    source_id = f"portal_csv_{portal_id}"
    source = Source(source_id, "portal_file", row["url"], portal_id)
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            result = collect_portal_file(source, Store(), client)
        items = list(Store().manifest(source_id)["items"].values())
        extensions = sorted({Path(i["filename"]).suffix.lower() for i in items})
        return {"portal_id": portal_id, "status": "saved", "extensions": extensions, **result}
    except (httpx.HTTPError, ValueError, KeyError, OSError, csv.Error, RuntimeError) as exc:
        return {"portal_id": portal_id, "status": "failed", "reason": type(exc).__name__,
                "message": str(exc)[:160] if not isinstance(exc, httpx.HTTPError) else "HTTP request failed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    rows = json.loads(INVENTORY.read_text(encoding="utf-8"))["datasets"]
    selected = [row for row in rows if "CSV" in row["extensions"]
                and row["provider"] == "경기도 용인시" and row["portal_id"] not in CSV_ALLOWLIST]
    if args.limit:
        selected = selected[:args.limit]
    prior = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {"results": {}}
    results = prior["results"]
    selected = [row for row in selected if results.get(row["portal_id"], {}).get("status") != "saved"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect, row): row["portal_id"] for row in selected}
        for index, future in enumerate(as_completed(futures), 1):
            item = future.result()
            results[item["portal_id"]] = item
            if index % 10 == 0 or index == len(selected):
                STATUS.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(),
                                              "results": results}, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
                print(f"processed={index}/{len(selected)} saved={sum(v['status']=='saved' for v in results.values())} failed={sum(v['status']=='failed' for v in results.values())}", flush=True)


if __name__ == "__main__":
    main()
