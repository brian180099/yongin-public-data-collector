"""Read an approved, allowlisted portal application without exposing its key."""

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
from urllib.parse import urlparse

from dotenv import set_key


APPLICATION_TITLES = {
    "public_facilities": "공공시설개방정보",
}


@dataclass(frozen=True)
class ApprovedApplication:
    source_id: str
    endpoint: str
    key: str


def parse_approved_application(source_id: str, visible_text: str,
                               page_url: str) -> ApprovedApplication:
    """Accept only the expected approved API detail, never a different application."""
    if source_id not in APPLICATION_TITLES:
        raise ValueError("source is not enabled for portal application sync")
    if urlparse(page_url).hostname not in {"www.data.go.kr", "data.go.kr"}:
        raise ValueError("application detail is not on the official portal")
    title = APPLICATION_TITLES[source_id]
    normalized = re.sub(r"\s+", " ", visible_text)
    if title not in normalized:
        raise ValueError("application title does not match the allowlisted source")
    if not re.search(r"처리상태\s*[:：]?\s*승인\b", normalized):
        raise ValueError("application is not visibly approved")
    endpoint_match = re.search(
        r"End\s*Point\s*[:：]?\s*(https://[^\s<>]+)", normalized, re.I
    )
    if not endpoint_match:
        raise ValueError("approved application has no visible endpoint")
    endpoint = endpoint_match.group(1).rstrip(".,")
    parsed_endpoint = urlparse(endpoint)
    if (parsed_endpoint.hostname not in {"api.data.go.kr", "apis.data.go.kr",
                                         "api.odcloud.kr"} or parsed_endpoint.username or
            parsed_endpoint.password or parsed_endpoint.query or parsed_endpoint.fragment):
        raise ValueError("endpoint host is not an expected public-data API host")
    key_match = re.search(r"일반\s*인증키\s*[:：]?\s*([A-Za-z0-9%._~-]{20,})",
                          normalized)
    if not key_match:
        raise ValueError("approved application has no visible general key")
    return ApprovedApplication(source_id, endpoint, key_match.group(1))


def save_approved_application(application: ApprovedApplication, runtime_dir: Path,
                              expected_endpoint: str) -> dict:
    """Keep credentials in ignored local files; never return the secret."""
    if application.source_id not in APPLICATION_TITLES:
        raise ValueError("source is not enabled for portal application sync")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    env_path = runtime_dir / "collector.env"
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
    set_key(str(env_path), "DATA_GO_KR_SERVICE_KEY", application.key)
    if os.name != "nt":
        env_path.chmod(0o600)
    status = {
        "source": application.source_id,
        "status": "approved_key_saved_call_unverified",
        "endpoint_matches_collector": application.endpoint == expected_endpoint,
        "endpoint": application.endpoint,
    }
    metadata_path = runtime_dir / "portal_application_status.json"
    metadata_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return status
