"""Preserve large official CSV ZIPs after bounded archive validation."""

import json
import io
import zipfile
from pathlib import Path

import httpx

from yongin_collector.collect import PORTAL, discover_files, filename_from_response, reference_date_from_name
from yongin_collector.store import Store


for portal_id in ("15170162", "15170166", "15139630", "15139958"):
    url = f"{PORTAL}/data/{portal_id}/fileData.do"
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        candidates = discover_files(client.get(url).text, portal_id, 20)
        if len(candidates) != 1:
            print(portal_id, "candidate_count", len(candidates))
            continue
        candidate = candidates[0]
        info = client.get(f"{PORTAL}/tcs/dss/selectFileDataDownload.do", params={
            "publicDataPk": candidate.portal_id,
            "publicDataDetailPk": candidate.detail_id,
            "atchFileId": candidate.attachment_id,
            "fileDetailSn": candidate.file_no,
            "publicDataHistSn": candidate.history_no,
            "publicDataTyCode": "PR0051",
        }, headers={"Referer": url}).json()
        if info.get("status") is not True:
            print(portal_id, "download_not_authorized")
            continue
        attachment, file_no = info["atchFileId"], info["fileDetailSn"]
        gate = client.post(f"{PORTAL}/cmm/cmm/check-limit.json",
                           data={"atchFileId": attachment, "fileDetailSn": file_no},
                           headers={"Referer": url}).json()
        if gate.get("needCaptcha"):
            print(portal_id, "captcha")
            continue
        label = info.get("dataSetFileDetailInfo", {}).get("dataNm") or "download"
        response = client.get(f"{PORTAL}/cmm/cmm/fileDownload.do",
                              params={"atchFileId": attachment, "fileDetailSn": file_no,
                                      "dataNm": label}, headers={"Referer": url})
        response.raise_for_status()
        if not response.content.startswith(b"PK\x03\x04"):
            print(portal_id, "not_zip")
            continue
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            members = archive.infolist()
            if (len(response.content) > 50_000_000 or not members or len(members) > 20
                    or sum(x.file_size for x in members) > 500_000_000
                    or any(x.is_dir() or Path(x.filename).name != x.filename
                           or not x.filename.lower().endswith(".csv")
                           or x.file_size > 150_000_000 for x in members)
                    or archive.testzip() is not None):
                print(portal_id, "archive_validation_failed")
                continue
            source_id = f"portal_csv_{portal_id}"
            filename = filename_from_response(response, label)
            Store().save(source_id=source_id, item_id=candidate.item_id,
                         content=response.content, extension="zip", source_url=url,
                         original_filename=filename, reference_date=reference_date_from_name(filename),
                         fingerprint=f"{attachment}:{file_no}", content_type=response.headers.get("content-type"),
                         http_status=response.status_code)
            print(portal_id, "saved", len(members), sum(x.file_size for x in members))

status_path = Path(__file__).resolve().parents[1] / "data/state/portal_bulk_collection.json"
status = json.loads(status_path.read_text(encoding="utf-8"))
for portal_id in ("15170162", "15170166", "15139630", "15139958"):
    source_id = f"portal_csv_{portal_id}"
    if Store().manifest(source_id)["items"]:
        status["results"][portal_id] = {"portal_id": portal_id, "status": "saved", "extensions": [".zip"],
                                         "found": 1, "saved": 1, "unchanged": 0}
status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
