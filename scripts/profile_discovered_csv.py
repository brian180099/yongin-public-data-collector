"""Profile saved new CSVs without altering originals or the database."""

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from yongin_collector.store import Store


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "data" / "state" / "portal_bulk_collection.json"
PROFILE = ROOT / "data" / "state" / "portal_bulk_profile.json"


def profile(source_id: str) -> dict:
    items = list(Store().manifest(source_id)["items"].values())
    if len(items) != 1 or not items[0]["filename"].endswith(".csv"):
        return {"status": "blocked", "reason": "not_one_direct_csv"}
    metadata = items[0]
    raw = (Store().raw / source_id / metadata["filename"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        return {"status": "blocked", "reason": "hash_mismatch"}
    if len(raw) > 30_000_000:
        return {"status": "blocked", "reason": "over_30mb"}
    try:
        try:
            decoded = raw.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            decoded = raw.decode("cp949")
            encoding = "cp949"
        reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        headers = [s.strip() for s in next(reader)]
        if len(headers) < 2 or any(not x for x in headers) or len(headers) != len(set(headers)):
            raise ValueError("invalid_headers")
        count = 0
        blank_lines = 0
        hashes = Counter()
        for row in reader:
            if not row:
                blank_lines += 1
                continue
            if len(row) != len(headers):
                raise ValueError("row_width_mismatch")
            if all(not value.strip() for value in row):
                raise ValueError("empty_row")
            count += 1
            hashes[hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).digest()] += 1
            if count > 200_000:
                raise ValueError("over_200k_rows")
        if not count:
            raise ValueError("no_rows")
        return {"status": "ready", "rows": count, "columns": len(headers),
                "duplicate_rows": sum(v - 1 for v in hashes.values()),
                "blank_lines_skipped": blank_lines,
                "encoding": encoding, "headers": headers, "bytes": len(raw)}
    except (ValueError, UnicodeError, csv.Error) as exc:
        return {"status": "blocked", "reason": str(exc)[:100]}


def main() -> None:
    statuses = json.loads(STATUS.read_text(encoding="utf-8"))["results"]
    results = {}
    for portal_id, status in statuses.items():
        if status["status"] == "saved":
            results[portal_id] = profile(f"portal_csv_{portal_id}")
    PROFILE.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ready", sum(x["status"] == "ready" for x in results.values()),
          "blocked", sum(x["status"] == "blocked" for x in results.values()),
          "rows", sum(x.get("rows", 0) for x in results.values()),
          "duplicate_rows", sum(x.get("duplicate_rows", 0) for x in results.values()))


if __name__ == "__main__":
    main()
