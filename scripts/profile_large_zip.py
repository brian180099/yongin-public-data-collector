"""Stream-validate large CSV members from preserved official ZIP files."""

import csv
import hashlib
import json
from pathlib import Path

from yongin_collector.store import Store


ROOT = Path(__file__).resolve().parents[1]
profiles = json.loads((ROOT / "data/state/portal_bulk_zip_profile.json").read_text(encoding="utf-8"))
store = Store()
results = {}
for source_id, old in profiles.items():
    if old.get("reason") not in ("over_30mb", "over_200k_rows"):
        continue
    artifacts = list(store.manifest(source_id)["items"].values())
    if len(artifacts) != 1:
        results[source_id] = {"status": "blocked", "reason": "manifest_ambiguous"}
        continue
    artifact = artifacts[0]
    path = store.raw / source_id / artifact["filename"]
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != artifact["sha256"]:
            results[source_id] = {"status": "blocked", "reason": "hash_mismatch"}
            continue
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle, strict=True)
                headers = [h.strip() for h in next(reader)]
                if len(headers) < 2 or any(not h for h in headers) or len(headers) != len(set(headers)):
                    raise ValueError("invalid_headers")
                count = 0
                for row in reader:
                    if len(row) != len(headers) or all(not value.strip() for value in row):
                        raise ValueError("row_width_or_empty_record")
                    count += 1
            results[source_id] = {"status": "ready", "rows": count,
                                  "headers": headers, "encoding": encoding,
                                  "bytes": path.stat().st_size,
                                  "portal_id": old["portal_id"],
                                  "member_name": old["member_name"]}
            break
        except UnicodeDecodeError:
            continue
        except (ValueError, csv.Error, StopIteration) as exc:
            results[source_id] = {"status": "blocked", "reason": str(exc)[:100]}
            break
    else:
        results[source_id] = {"status": "blocked", "reason": "unsupported_encoding"}
    print(source_id, results[source_id]["status"], results[source_id].get("rows", 0), flush=True)
out = ROOT / "data/state/portal_large_zip_profile.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
