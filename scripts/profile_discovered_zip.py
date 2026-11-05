"""Preserve and validate each CSV member of newly discovered official ZIPs."""

import hashlib
import json
import zipfile
from pathlib import Path

from profile_discovered_csv import profile
from yongin_collector.collect import reference_date_from_name, validate_download
from yongin_collector.store import Store


ROOT = Path(__file__).resolve().parents[1]
statuses = json.loads((ROOT / "data/state/portal_bulk_collection.json").read_text(encoding="utf-8"))["results"]
store = Store()
results = {}
for portal_id, status in statuses.items():
    if status.get("extensions") != [".zip"]:
        continue
    parent_id = f"portal_csv_{portal_id}"
    artifacts = list(store.manifest(parent_id)["items"].values())
    if len(artifacts) != 1:
        raise ValueError("ZIP archive manifest is ambiguous")
    artifact = artifacts[0]
    path = store.raw / parent_id / artifact["filename"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("ZIP archive hash mismatch")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if archive.testzip() is not None or len(members) > 20:
            raise ValueError("ZIP integrity or member count failed")
        for index, member in enumerate(members, 1):
            source_id = f"portal_zip_{portal_id}_{index:02d}"
            if (member.is_dir() or Path(member.filename).name != member.filename
                    or not member.filename.lower().endswith(".csv")
                    or member.file_size > 150_000_000):
                results[source_id] = {"status": "blocked", "reason": "unsafe_member"}
                continue
            content = archive.read(member)
            try:
                validate_download(content, "csv")
                digest = hashlib.sha256(content).hexdigest()
                if not store.known(source_id, "current", digest):
                    store.save(source_id=source_id, item_id="current", content=content,
                               extension="csv", source_url=artifact["source_url"],
                               original_filename=member.filename,
                               reference_date=reference_date_from_name(member.filename),
                               fingerprint=digest, content_type="text/csv", http_status=200,
                               response_metadata={"archive_sha256": artifact["sha256"],
                                                  "archive_source_id": parent_id,
                                                  "zip_member_name": member.filename})
                results[source_id] = {**profile(source_id), "portal_id": portal_id,
                                      "member_name": member.filename}
            except (ValueError, UnicodeError) as exc:
                results[source_id] = {"status": "blocked", "reason": type(exc).__name__}

out = ROOT / "data/state/portal_bulk_zip_profile.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("members", len(results), "ready", sum(x["status"] == "ready" for x in results.values()),
      "rows", sum(x.get("rows", 0) for x in results.values()))
