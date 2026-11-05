"""Review files with unnamed columns or empty padding records without changing raw bytes."""

import csv
import hashlib
import json
from pathlib import Path

from yongin_collector.store import Store


ROOT = Path(__file__).resolve().parents[1]
direct = json.loads((ROOT / "data/state/portal_bulk_profile.json").read_text(encoding="utf-8"))
members = json.loads((ROOT / "data/state/portal_bulk_zip_profile.json").read_text(encoding="utf-8"))
large = json.loads((ROOT / "data/state/portal_large_profile.json").read_text(encoding="utf-8"))
targets = {f"portal_csv_{key}": value for key, value in direct.items()
           if value.get("reason") in ("invalid_headers", "empty_row", "row_width_or_empty_record")}
targets.update({key: value for key, value in members.items()
                if value.get("reason") in ("invalid_headers", "empty_row", "row_width_or_empty_record")})
targets.update({f"portal_csv_{key}": value for key, value in large.items()
                if value.get("reason") == "row_width_or_empty_record"})
# Previously held allowlist files have their original bytes in the same raw
# store. Recheck them with the content-occurrence key strategy; their earlier
# key/date rules must not silently discard rows.
legacy_held = ("15014158", "3078101", "15138028", "15154681", "15138075",
               "15154714", "15136677", "15154460", "15154453")
targets.update({f"portal_csv_{key}": {} for key in legacy_held})
store = Store()
results = {}
for source_id, old in targets.items():
    items = list(store.manifest(source_id)["items"].values())
    if len(items) != 1:
        results[source_id] = {"status": "blocked", "reason": "manifest_ambiguous"}
        continue
    path = store.raw / source_id / items[0]["filename"]
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != items[0]["sha256"]:
            results[source_id] = {"status": "blocked", "reason": "hash_mismatch"}
            continue
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle, strict=True)
                original = next(reader)
                if len(original) < 2:
                    raise ValueError("too_few_headers")
                headers = []
                for index, raw in enumerate(original, 1):
                    name = raw.strip() or f"__unnamed_column_{index}"
                    if name in headers:
                        name += f"__column_{index}"
                    headers.append(name)
                count = blank = 0
                for row in reader:
                    if not row or all(not value.strip() for value in row):
                        blank += 1
                        continue
                    if len(row) != len(headers):
                        raise ValueError("row_width_mismatch")
                    count += 1
                if not count:
                    raise ValueError("no_nonempty_rows")
            results[source_id] = {"status": "ready", "rows": count,
                                  "headers": headers, "original_headers": original,
                                  "encoding": encoding, "skipped_empty_rows": blank,
                                  "header_repaired": headers != [x.strip() for x in original],
                                  "bytes": path.stat().st_size}
            if source_id in members:
                results[source_id]["portal_id"] = members[source_id]["portal_id"]
                results[source_id]["member_name"] = members[source_id]["member_name"]
            break
        except UnicodeDecodeError:
            continue
        except (ValueError, csv.Error, StopIteration) as exc:
            results[source_id] = {"status": "blocked", "reason": str(exc)[:100]}
            break
    else:
        results[source_id] = {"status": "blocked", "reason": "unsupported_encoding"}
    print(source_id, results[source_id]["status"], results[source_id].get("rows", 0),
          results[source_id].get("skipped_empty_rows", 0), flush=True)
out = ROOT / "data/state/portal_irregular_profile.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
