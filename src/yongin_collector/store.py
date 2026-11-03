"""Immutable raw artifacts and a local manifest for change detection."""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
STATE = ROOT / "data" / "state"
KST = ZoneInfo("Asia/Seoul")
SAFE_ID = re.compile(r"^[a-z0-9_]+$")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(payload)
        temp_path = Path(temp.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


class Store:
    def __init__(self, raw: Path = RAW, state: Path = STATE):
        self.raw = raw
        self.state = state

    def manifest(self, source_id: str) -> dict:
        path = self.state / f"{source_id}.json"
        if not path.exists():
            return {"source_id": source_id, "items": {}, "last_checked_at": None,
                    "last_error": None}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_manifest(self, source_id: str, manifest: dict) -> None:
        atomic_write(self.state / f"{source_id}.json",
                     (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())

    def record_error(self, source_id: str, message: str) -> None:
        state = self.manifest(source_id)
        state["last_checked_at"] = datetime.now(KST).isoformat()
        state["last_error"] = message
        self.save_manifest(source_id, state)

    def record_checked(self, source_id: str) -> None:
        state = self.manifest(source_id)
        state["last_checked_at"] = datetime.now(KST).isoformat()
        state["last_error"] = None
        self.save_manifest(source_id, state)

    def known(self, source_id: str, item_id: str, fingerprint: str | None = None) -> bool:
        entry = self.manifest(source_id)["items"].get(item_id)
        if not entry or (fingerprint is not None and entry.get("fingerprint") != fingerprint):
            return False
        path = self.raw / source_id / entry["filename"]
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]

    def save(self, *, source_id: str, item_id: str, content: bytes, extension: str,
             source_url: str, original_filename: str | None = None,
             reference_date: str | None = None, fingerprint: str | None = None,
             content_type: str | None = None) -> str:
        if not SAFE_ID.fullmatch(source_id) or not SAFE_ID.fullmatch(extension):
            raise ValueError("unsafe source id or extension")
        if not content:
            raise ValueError("empty response")
        digest = hashlib.sha256(content).hexdigest()
        collected = datetime.now(KST).isoformat()
        name = f"{digest}.{extension}"
        path = self.raw / source_id / name
        if not path.exists():
            atomic_write(path, content)
        metadata = {"source_id": source_id, "item_id": item_id,
                    "source_url": source_url, "original_filename": original_filename,
                    "collected_at": collected, "reference_date": reference_date,
                    "content_type": content_type, "byte_count": len(content),
                    "sha256": digest, "fingerprint": fingerprint, "filename": name}
        atomic_write(path.with_name(f"{digest}.metadata.json"),
                     (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode())
        state = self.manifest(source_id)
        state["items"][item_id] = metadata
        state["last_checked_at"] = collected
        state["last_error"] = None
        self.save_manifest(source_id, state)
        return name
