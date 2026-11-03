"""Source discovery, official file download, and bounded API collection."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .sources import Source
from .store import Store


PORTAL = "https://www.data.go.kr"
TIMEOUT = httpx.Timeout(30.0, connect=8.0)
FILE_CALL = re.compile(
    r"fileDetailObj\.fn_fileDataDown\('([^']+)',\s*'([^']+)',\s*'([^']*)',"
    r"\s*'([^']+)',\s*'([^']+)'\)"
)
DATE_IN_NAME = re.compile(r"(?<!\d)(20\d{6})(?!\d)")


@dataclass(frozen=True)
class FileCandidate:
    portal_id: str
    detail_id: str
    attachment_id: str
    file_no: str
    history_no: str

    @property
    def item_id(self) -> str:
        return f"{self.detail_id}:{self.file_no}:{self.history_no}"


def discover_files(html: str, portal_id: str, limit: int) -> list[FileCandidate]:
    seen: dict[str, FileCandidate] = {}
    for groups in FILE_CALL.findall(html):
        candidate = FileCandidate(*groups)
        if candidate.portal_id == portal_id:
            seen[candidate.item_id] = candidate
    if len(seen) > limit:
        raise ValueError(f"file count exceeds configured limit {limit}")
    return list(seen.values())


def validate_download(content: bytes, extension: str) -> None:
    if not content:
        raise ValueError("empty download")
    if extension == "xlsx" and not content.startswith(b"PK\x03\x04"):
        raise ValueError("XLSX signature mismatch")
    if extension == "xls" and not content.startswith(bytes.fromhex("D0CF11E0")):
        raise ValueError("XLS signature mismatch")
    if extension == "csv":
        head = content[:512].lstrip().lower()
        if head.startswith((b"<!doctype", b"<html", b"<script")):
            raise ValueError("HTML returned instead of CSV")
    if extension == "html" and b"<html" not in content[:4096].lower():
        raise ValueError("HTML signature mismatch")


def filename_from_response(response: httpx.Response, fallback: str) -> str:
    header = response.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)', header, re.I)
    return Path(match.group(1)).name if match else fallback


def reference_date_from_name(name: str) -> str | None:
    match = DATE_IN_NAME.search(name)
    if not match:
        return None
    value = match.group(1)
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def collect_page(source: Source, store: Store, client: httpx.Client) -> dict:
    response = client.get(source.url)
    response.raise_for_status()
    validate_download(response.content, "html")
    digest = hashlib.sha256(response.content).hexdigest()
    if store.known(source.source_id, "current", digest):
        return {"source": source.source_id, "found": 1, "saved": 0, "unchanged": 1}
    store.save(source_id=source.source_id, item_id="current", content=response.content,
               extension="html", source_url=source.url, fingerprint=digest,
               content_type=response.headers.get("content-type"))
    return {"source": source.source_id, "found": 1, "saved": 1, "unchanged": 0}


def collect_portal_file(source: Source, store: Store, client: httpx.Client,
                        refresh_existing: bool = False) -> dict:
    page = client.get(source.url)
    page.raise_for_status()
    candidates = discover_files(page.text, source.portal_id or "", source.max_files)
    if not candidates:
        raise ValueError("no downloadable file buttons; source may now be an external link")
    saved = unchanged = 0
    for candidate in candidates:
        if not refresh_existing and store.known(source.source_id, candidate.item_id):
            unchanged += 1
            continue
        params = {"publicDataPk": candidate.portal_id,
                  "publicDataDetailPk": candidate.detail_id,
                  "atchFileId": candidate.attachment_id,
                  "fileDetailSn": candidate.file_no,
                  "publicDataHistSn": candidate.history_no,
                  "publicDataTyCode": "PR0051"}
        info_response = client.get(f"{PORTAL}/tcs/dss/selectFileDataDownload.do",
                                   params=params, headers={"Referer": source.url})
        info_response.raise_for_status()
        info = info_response.json()
        if info.get("status") is not True:
            raise ValueError("portal did not authorize file download")
        attachment = info["atchFileId"]
        file_no = info["fileDetailSn"]
        limit_response = client.post(f"{PORTAL}/cmm/cmm/check-limit.json",
                                     data={"atchFileId": attachment, "fileDetailSn": file_no},
                                     headers={"Referer": source.url})
        limit_response.raise_for_status()
        if limit_response.json().get("needCaptcha"):
            raise ValueError("portal requires a human CAPTCHA for this file")
        label = info.get("dataSetFileDetailInfo", {}).get("dataNm") or "download"
        download = client.get(f"{PORTAL}/cmm/cmm/fileDownload.do",
                              params={"atchFileId": attachment, "fileDetailSn": file_no,
                                      "dataNm": label}, headers={"Referer": source.url})
        download.raise_for_status()
        name = filename_from_response(download, label)
        extension = Path(name).suffix.lower().lstrip(".")
        if extension not in {"csv", "xls", "xlsx"}:
            raise ValueError(f"unexpected file type: {extension or 'none'}")
        validate_download(download.content, extension)
        current_hash = hashlib.sha256(download.content).hexdigest()
        if store.known(source.source_id, candidate.item_id):
            previous = store.manifest(source.source_id)["items"][candidate.item_id]
            if previous["sha256"] == current_hash:
                unchanged += 1
                continue
        store.save(source_id=source.source_id, item_id=candidate.item_id,
                   content=download.content, extension=extension, source_url=source.url,
                   original_filename=name, reference_date=reference_date_from_name(name),
                   fingerprint=f"{attachment}:{file_no}",
                   content_type=download.headers.get("content-type"))
        saved += 1
    return {"source": source.source_id, "found": len(candidates),
            "saved": saved, "unchanged": unchanged}


def _api_items(payload: dict) -> tuple[list[dict], int]:
    body = payload.get("response", {}).get("body", {})
    header = payload.get("response", {}).get("header", {})
    if str(header.get("resultCode", "00")) not in {"00", "0"}:
        raise ValueError("API result code indicates failure")
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("unexpected API items schema")
    return items, int(body.get("totalCount", len(items)))


def collect_api(source: Source, store: Store, client: httpx.Client,
                service_key: str, max_pages: int = 10) -> dict:
    if not service_key:
        raise ValueError("DATA_GO_KR_SERVICE_KEY is missing")
    saved = unchanged = found = 0
    for page_no in range(1, max_pages + 1):
        # The source API documents rdnmadr as a filter. Reject non-Yongin
        # records as well, in case server-side filter semantics change.
        params = {"serviceKey": service_key, "pageNo": page_no,
                  "numOfRows": 1000, "type": "json", "rdnmadr": "경기도 용인시"}
        response = client.get(source.url, params=params)
        response.raise_for_status()
        payload = response.json()
        if "OpenAPI_ServiceResponse" in payload:
            raise ValueError("public-data API authentication or quota error")
        items, total = _api_items(payload)
        if not items:
            if page_no == 1:
                raise ValueError("no Yongin records returned by API")
            break
        if any("용인시" not in str(item.get("rdnmadr", "")) for item in items):
            raise ValueError("API returned records outside Yongin or missing addresses")
        found += len(items)
        # Preserve the original JSON response; never add the key to metadata.
        digest = hashlib.sha256(response.content).hexdigest()
        item_id = f"page_{page_no}"
        if store.known(source.source_id, item_id, digest):
            unchanged += 1
        else:
            store.save(source_id=source.source_id, item_id=item_id,
                       content=response.content, extension="json",
                       source_url=source.url, fingerprint=digest,
                       content_type=response.headers.get("content-type"))
            saved += 1
        if page_no * 1000 >= total:
            break
    else:
        raise ValueError(f"API result exceeds {max_pages} pages; increase cap explicitly")
    return {"source": source.source_id, "found": found, "saved": saved,
            "unchanged": unchanged}


def collect(source: Source, store: Store, service_key: str | None,
            mode: str = "daily") -> dict:
    # httpx INFO logs include request URLs, including the service key.
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "YonginPublicDataCollector/0.1"}) as client:
        if source.kind == "page":
            return collect_page(source, store, client)
        if source.kind == "portal_file":
            return collect_portal_file(source, store, client,
                                       refresh_existing=(mode == "daily"))
        if source.kind == "api":
            return collect_api(source, store, client, service_key or "")
        raise ValueError("unsupported source kind")
