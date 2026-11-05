"""Source discovery, official file download, and bounded API collection."""

import hashlib
import csv
import io
import re
import zipfile
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
API_REQUIRED_FIELDS = {"rdnmadr", "lnmadr", "referenceDate"}


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
    if extension == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
                    raise ValueError("XLSX workbook structure missing")
                if archive.testzip() is not None:
                    raise ValueError("XLSX archive contains corrupt data")
        except zipfile.BadZipFile as exc:
            raise ValueError("XLSX archive is invalid") from exc
    if extension == "zip":
        if len(content) > 50_000_000:
            raise ValueError("ZIP download exceeds size cap")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if not members or len(members) > 20:
                    raise ValueError("ZIP member count is invalid")
                if any(member.is_dir() or Path(member.filename).name != member.filename
                       or not member.filename.lower().endswith(".csv")
                       or member.file_size > 30_000_000 for member in members):
                    raise ValueError("ZIP contains an unsafe or non-CSV member")
                if sum(member.file_size for member in members) > 50_000_000:
                    raise ValueError("ZIP uncompressed size exceeds cap")
                if archive.testzip() is not None:
                    raise ValueError("ZIP archive contains corrupt data")
        except zipfile.BadZipFile as exc:
            raise ValueError("ZIP archive is invalid") from exc
    if extension == "xls" and not content.startswith(bytes.fromhex("D0CF11E0")):
        raise ValueError("XLS signature mismatch")
    if extension == "csv":
        head = content[:512].lstrip().lower()
        if head.startswith((b"<!doctype", b"<html", b"<script")):
            raise ValueError("HTML returned instead of CSV")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = content.decode("cp949")
        rows = csv.reader(io.StringIO(decoded, newline=""))
        header = next(rows, [])
        if len(header) < 2 or not any(True for _ in rows):
            raise ValueError("CSV header or data rows missing")
    if extension == "html" and b"<html" not in content[:4096].lower():
        raise ValueError("HTML signature mismatch")


def validate_large_csv_zip(content: bytes) -> None:
    """Permit reviewed large CSV-only archives with strict path and size bounds."""
    if len(content) > 50_000_000 or not content.startswith(b"PK\x03\x04"):
        raise ValueError("large ZIP exceeds compressed size cap or has wrong signature")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if not members or len(members) > 20:
                raise ValueError("large ZIP member count is invalid")
            if any(member.is_dir() or Path(member.filename).name != member.filename
                   or not member.filename.lower().endswith(".csv")
                   or member.file_size > 150_000_000 for member in members):
                raise ValueError("large ZIP contains unsafe or non-CSV member")
            if sum(member.file_size for member in members) > 500_000_000:
                raise ValueError("large ZIP uncompressed size exceeds cap")
            if archive.testzip() is not None:
                raise ValueError("large ZIP contains corrupt data")
    except zipfile.BadZipFile as exc:
        raise ValueError("large ZIP is invalid") from exc


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
               content_type=response.headers.get("content-type"),
               http_status=response.status_code)
    return {"source": source.source_id, "found": 1, "saved": 1, "unchanged": 0}


def collect_portal_file(source: Source, store: Store, client: httpx.Client,
                        refresh_existing: bool = False) -> dict:
    page = client.get(source.url)
    page.raise_for_status()
    candidates = discover_files(page.text, source.portal_id or "", source.max_files)
    if not candidates:
        raise ValueError("no downloadable file buttons; source may now be an external link")
    saved = unchanged = 0
    pending: list[dict] = []
    manifest = store.manifest(source.source_id)
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
        if extension not in {"csv", "xls", "xlsx", "zip"}:
            raise ValueError(f"unexpected file type: {extension or 'none'}")
        if extension == "zip" and source.allow_large_zip:
            validate_large_csv_zip(download.content)
        else:
            validate_download(download.content, extension)
        current_hash = hashlib.sha256(download.content).hexdigest()
        if store.known(source.source_id, candidate.item_id):
            previous = manifest["items"][candidate.item_id]
            if previous["sha256"] == current_hash:
                unchanged += 1
                continue
        pending.append({
            "item_id": candidate.item_id, "content": download.content,
            "extension": extension, "source_url": source.url,
            "original_filename": name,
            "reference_date": reference_date_from_name(name),
            "fingerprint": f"{attachment}:{file_no}",
            "content_type": download.headers.get("content-type"),
            "http_status": download.status_code,
        })
        saved += 1
    if pending:
        store.save_many(source.source_id, pending)
    return {"source": source.source_id, "found": len(candidates),
            "saved": saved, "unchanged": unchanged}


def collect_zip_member(source: Source, store: Store, client: httpx.Client,
                       refresh_existing: bool = False) -> dict:
    if not source.portal_id or not source.zip_marker:
        raise ValueError("ZIP member source is missing its reviewed selector")
    parent_id = f"portal_csv_{source.portal_id}"
    parent = Source(parent_id, "portal_file", source.url, source.portal_id,
                    allow_large_zip=source.allow_large_zip)
    if refresh_existing or not store.manifest(parent_id)["items"]:
        collect_portal_file(parent, store, client, refresh_existing=refresh_existing)
    archives = list(store.manifest(parent_id)["items"].values())
    if len(archives) != 1 or not archives[0]["filename"].endswith(".zip"):
        raise ValueError("expected one validated official ZIP archive")
    archive_meta = archives[0]
    archive_bytes = (store.raw / parent_id / archive_meta["filename"]).read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != archive_meta["sha256"]:
        raise ValueError("ZIP archive hash mismatch")
    if source.allow_large_zip:
        validate_large_csv_zip(archive_bytes)
    else:
        validate_download(archive_bytes, "zip")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        matches = [name for name in archive.namelist() if source.zip_marker in name]
        if len(matches) != 1:
            raise ValueError("reviewed CSV member selector is ambiguous or missing")
        member_name = matches[0]
        content = archive.read(member_name)
    validate_download(content, "csv")
    digest = hashlib.sha256(content).hexdigest()
    if store.known(source.source_id, "current", digest):
        return {"source": source.source_id, "found": 1, "saved": 0, "unchanged": 1}
    store.save(
        source_id=source.source_id, item_id="current", content=content,
        extension="csv", source_url=source.url,
        original_filename=member_name,
        reference_date=reference_date_from_name(member_name),
        fingerprint=digest, content_type="text/csv", http_status=200,
        response_metadata={"archive_sha256": archive_meta["sha256"],
                           "archive_source_id": parent_id,
                           "archive_original_filename": archive_meta["original_filename"],
                           "zip_member_name": member_name},
    )
    return {"source": source.source_id, "found": 1, "saved": 1, "unchanged": 0}


def _api_items(payload: dict) -> tuple[list[dict], int]:
    envelope = payload.get("response", payload)
    if not isinstance(envelope, dict):
        raise ValueError("unexpected API response schema")
    body = envelope.get("body")
    header = envelope.get("header")
    if not isinstance(body, dict) or not isinstance(header, dict):
        raise ValueError("unexpected API response schema")
    if str(header.get("resultCode")) not in {"00", "0"}:
        raise ValueError("API result code indicates failure")
    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("unexpected API items schema")
    return items, int(body.get("totalCount", len(items)))


def resolve_odcloud_api_url(source: Source, client: httpx.Client) -> str:
    """Resolve the current file UDDI against the portal's official OAS document."""

    if not source.portal_id:
        return source.url
    detail_url = f"{PORTAL}/data/{source.portal_id}/fileData.do"
    detail = client.get(detail_url)
    detail.raise_for_status()
    candidates = discover_files(detail.text, source.portal_id, source.max_files)
    if len(candidates) != 1:
        raise ValueError("expected exactly one current file for ODCLOUD API resolution")
    current_detail_id = candidates[0].detail_id
    oas_response = client.get(
        "https://infuser.odcloud.kr/oas/docs",
        params={"namespace": f"{source.portal_id}/v1"},
    )
    oas_response.raise_for_status()
    try:
        oas = oas_response.json()
    except ValueError as exc:
        raise ValueError("ODCLOUD OAS document is not JSON") from exc
    path = f"/{source.portal_id}/v1/{current_detail_id}"
    if (oas.get("host") != "api.odcloud.kr" or
            oas.get("basePath") != "/api" or
            "https" not in oas.get("schemes", []) or
            path not in oas.get("paths", {})):
        raise ValueError("current file is missing from the official ODCLOUD OAS")
    return f"https://api.odcloud.kr/api{path}"


def collect_api(source: Source, store: Store, client: httpx.Client,
                service_key: str, max_pages: int = 10) -> dict:
    if not service_key:
        raise ValueError("DATA_GO_KR_SERVICE_KEY is missing")
    saved = unchanged = found = fetched = 0
    expected_total: int | None = None
    pending: list[dict] = []
    field_names: set[str] = set()
    pages = 0
    for page_no in range(1, max_pages + 1):
        # The portal's address parameter does not perform a city substring
        # search. Fetch the bounded full snapshot and filter addresses locally.
        params = {"serviceKey": service_key, "pageNo": page_no,
                  "numOfRows": 1000, "type": "json"}
        response = client.get(source.url, params=params)
        response.raise_for_status()
        payload = response.json()
        if "OpenAPI_ServiceResponse" in payload:
            raise ValueError("public-data API authentication or quota error")
        items, total = _api_items(payload)
        if expected_total is None:
            expected_total = total
            required_pages = max(1, (total + 999) // 1000)
            if required_pages > max_pages:
                raise ValueError(
                    f"API result requires {required_pages} pages; configured cap is {max_pages}"
                )
        elif total != expected_total:
            raise ValueError("API totalCount changed during paginated collection")
        if not items:
            raise ValueError("API returned an empty page before its reported total")
        if any(not API_REQUIRED_FIELDS.issubset(item) for item in items):
            raise ValueError("API response is missing required facility fields")
        matched = [item for item in items if "용인시" in (
            str(item.get("rdnmadr", "")) + str(item.get("lnmadr", ""))
        )]
        page_fields = set().union(*(item.keys() for item in items))
        field_names.update(page_fields)
        found += len(matched)
        fetched += len(items)
        pages += 1
        # Preserve the original JSON response; never add the key to metadata.
        digest = hashlib.sha256(response.content).hexdigest()
        item_id = f"page_{page_no}"
        if store.known(source.source_id, item_id, digest):
            unchanged += 1
        else:
            reference_dates = sorted({
                str(item["referenceDate"]) for item in matched
                if item.get("referenceDate") not in (None, "")
            })
            pending.append({
                "item_id": item_id, "content": response.content,
                "extension": "json", "source_url": source.url,
                "reference_date": reference_dates[-1] if reference_dates else None,
                "fingerprint": digest,
                "content_type": response.headers.get("content-type"),
                "http_status": response.status_code,
                "response_metadata": {
                    "page_no": page_no, "record_count": len(items),
                    "yongin_record_count": len(matched),
                    "source_total_count": total,
                    "field_names": sorted(page_fields),
                    "reference_dates": reference_dates,
                    "address_filter": "용인시 (local match in rdnmadr or lnmadr)",
                },
            })
            saved += 1
        if page_no * 1000 >= total:
            break
    else:
        raise ValueError(f"API result exceeds {max_pages} pages; increase cap explicitly")
    if expected_total is not None and fetched != expected_total:
        raise ValueError(
            f"API pagination count mismatch: expected {expected_total}, received {fetched}"
        )
    if not found:
        raise ValueError("no Yongin records returned by complete API snapshot")
    if pending:
        store.save_many(source.source_id, pending)
    return {"source": source.source_id, "found": found, "saved": saved,
            "unchanged": unchanged, "pages": pages,
            "total_count": found, "source_total_count": expected_total,
            "field_count": len(field_names)}


def collect_odcloud_api(source: Source, store: Store, client: httpx.Client,
                        service_key: str, max_pages: int = 10) -> dict:
    """Collect a data.go.kr auto-converted JSON API without key-bearing URLs."""

    if not service_key:
        raise ValueError("DATA_GO_KR_SERVICE_KEY is missing")
    api_url = resolve_odcloud_api_url(source, client)
    required = set(source.required_fields)
    expected_total: int | None = None
    found = saved = unchanged = pages = 0
    field_names: set[str] = set()
    pending: list[dict] = []
    for page_no in range(1, max_pages + 1):
        response = client.get(
            api_url,
            params={"page": page_no, "perPage": 1000, "returnType": "JSON"},
            # ODCLOUD accepts the decoding key in this header. Keeping it out of
            # the URL prevents proxies and HTTP exception strings from logging it.
            headers={"Authorization": f"Infuser {service_key}"},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("ODCLOUD returned a non-JSON response") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("unexpected ODCLOUD response schema")
        items = payload["data"]
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("unexpected ODCLOUD data item schema")
        try:
            total = int(payload["totalCount"])
            current = int(payload["currentCount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("ODCLOUD response counts are missing or invalid") from exc
        if current != len(items):
            raise ValueError("ODCLOUD currentCount does not match data length")
        if expected_total is None:
            expected_total = total
            required_pages = max(1, (total + 999) // 1000)
            if required_pages > max_pages:
                raise ValueError(
                    f"ODCLOUD result requires {required_pages} pages; "
                    f"configured cap is {max_pages}"
                )
        elif total != expected_total:
            raise ValueError("ODCLOUD totalCount changed during collection")
        if page_no == 1 and not items:
            raise ValueError("ODCLOUD returned no records")
        if any(not required.issubset(item) for item in items):
            raise ValueError("ODCLOUD response is missing required vehicle fields")

        page_fields = set().union(*(item.keys() for item in items)) if items else set()
        field_names.update(page_fields)
        found += len(items)
        pages += 1
        digest = hashlib.sha256(response.content).hexdigest()
        item_id = f"page_{page_no}"
        if store.known(source.source_id, item_id, digest):
            unchanged += 1
        else:
            reference_dates = sorted({
                str(item["데이터기준일자"]) for item in items
                if item.get("데이터기준일자") not in (None, "")
            })
            pending.append({
                "item_id": item_id, "content": response.content,
                "extension": "json", "source_url": api_url,
                "reference_date": reference_dates[-1] if reference_dates else None,
                "fingerprint": digest,
                "content_type": response.headers.get("content-type"),
                "http_status": response.status_code,
                "response_metadata": {
                    "page_no": page_no, "record_count": len(items),
                    "total_count": total, "field_names": sorted(page_fields),
                    "reference_dates": reference_dates,
                },
            })
            saved += 1
        if found >= total:
            break
    else:
        raise ValueError(f"ODCLOUD result exceeds {max_pages} pages")
    if expected_total is None or found != expected_total:
        raise ValueError(
            f"ODCLOUD pagination count mismatch: expected {expected_total}, "
            f"received {found}"
        )
    if pending:
        store.save_many(source.source_id, pending)
    return {"source": source.source_id, "found": found, "saved": saved,
            "unchanged": unchanged, "pages": pages,
            "total_count": expected_total, "field_count": len(field_names)}


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
        if source.kind == "portal_zip_member":
            return collect_zip_member(source, store, client,
                                      refresh_existing=(mode == "daily"))
        if source.kind == "api":
            return collect_api(source, store, client, service_key or "")
        if source.kind == "odcloud_api":
            return collect_odcloud_api(source, store, client, service_key or "")
        raise ValueError("unsupported source kind")
