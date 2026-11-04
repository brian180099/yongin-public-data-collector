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
DATA_ROOT = Path(os.getenv("YONGIN_DATA_DIR", ROOT / "data")).resolve()
RAW = DATA_ROOT / "raw"
STATE = DATA_ROOT / "state"
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
                    "last_error": None, "runs": []}
        state = json.loads(path.read_text(encoding="utf-8"))
        # Keep manifests written by older collector versions readable.
        state.setdefault("items", {})
        state.setdefault("runs", [])
        state.setdefault("last_checked_at", None)
        state.setdefault("last_error", None)
        return state

    def save_manifest(self, source_id: str, manifest: dict) -> None:
        atomic_write(self.state / f"{source_id}.json",
                     (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())

    def record_error(self, source_id: str, message: str) -> None:
        state = self.manifest(source_id)
        checked_at = datetime.now(KST).isoformat()
        state["last_checked_at"] = checked_at
        state["last_error"] = message
        state["runs"].append({"checked_at": checked_at, "status": "failed",
                              "error": message})
        self.save_manifest(source_id, state)

    def record_checked(self, source_id: str, result: dict | None = None) -> None:
        state = self.manifest(source_id)
        checked_at = datetime.now(KST).isoformat()
        state["last_checked_at"] = checked_at
        state["last_error"] = None
        run = {"checked_at": checked_at, "status": "success"}
        if result is not None:
            run["result"] = result
        state["runs"].append(run)
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
             content_type: str | None = None, http_status: int | None = None,
             response_metadata: dict | None = None) -> str:
        return self.save_many(source_id, [{
            "item_id": item_id, "content": content, "extension": extension,
            "source_url": source_url, "original_filename": original_filename,
            "reference_date": reference_date, "fingerprint": fingerprint,
            "content_type": content_type, "http_status": http_status,
            "response_metadata": response_metadata,
        }])[0]

    def save_many(self, source_id: str, artifacts: list[dict]) -> list[str]:
        """Write a validated batch and publish its manifest in one final step.

        A network or format failure must be detected before this method is called.
        If an artifact write fails, the previous manifest remains authoritative.
        """
        if not SAFE_ID.fullmatch(source_id):
            raise ValueError("unsafe source id")
        prepared: list[tuple[Path, bytes, dict]] = []
        collected = datetime.now(KST).isoformat()
        for artifact in artifacts:
            extension = artifact["extension"]
            content = artifact["content"]
            if not SAFE_ID.fullmatch(extension):
                raise ValueError("unsafe extension")
            if not content:
                raise ValueError("empty response")
            digest = hashlib.sha256(content).hexdigest()
            name = f"{digest}.{extension}"
            metadata = {
                "source_id": source_id, "item_id": artifact["item_id"],
                "source_url": artifact["source_url"],
                "original_filename": artifact.get("original_filename"),
                "collected_at": collected,
                "reference_date": artifact.get("reference_date"),
                "content_type": artifact.get("content_type"),
                "http_status": artifact.get("http_status"),
                "byte_count": len(content), "sha256": digest,
                "fingerprint": artifact.get("fingerprint"), "filename": name,
            }
            if artifact.get("response_metadata") is not None:
                metadata["response"] = artifact["response_metadata"]
            prepared.append((self.raw / source_id / name, content, metadata))

        # Raw bytes and sidecar metadata are immutable artifacts. The manifest is
        # updated only after every artifact in the batch is safely present.
        for path, content, metadata in prepared:
            if not path.exists():
                atomic_write(path, content)
            atomic_write(path.with_name(f"{metadata['sha256']}.metadata.json"),
                         (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode())
        state = self.manifest(source_id)
        for _, _, metadata in prepared:
            state["items"][metadata["item_id"]] = metadata
        self.save_manifest(source_id, state)
        return [metadata["filename"] for _, _, metadata in prepared]
