import hashlib
import json

import httpx

from yongin_collector.collect import (
    _api_items, collect_api, discover_files, validate_download,
)
from yongin_collector.sources import DEFAULT_SOURCE_IDS, Source
from yongin_collector.store import Store


def test_discovery_only_accepts_configured_portal_id():
    html = (
        "fileDetailObj.fn_fileDataDown('3038399', 'uddi:abc', '','1', '1')"
        "fileDetailObj.fn_fileDataDown('9999999', 'uddi:def', '','1', '1')"
    )
    found = discover_files(html, "3038399", 5)
    assert len(found) == 1
    assert found[0].item_id == "uddi:abc:1:1"


def test_store_preserves_bytes_and_skips_unchanged(tmp_path):
    store = Store(tmp_path / "raw", tmp_path / "state")
    original = b"name,city\npark,Yongin\n"
    name = store.save(source_id="parks", item_id="first", content=original,
                      extension="csv", source_url="https://example.org/file.csv",
                      reference_date="2026-11-01", fingerprint="version1")
    assert (tmp_path / "raw" / "parks" / name).read_bytes() == original
    assert store.known("parks", "first", "version1")
    assert not store.known("parks", "first", "version2")
    metadata = json.loads((tmp_path / "raw" / "parks" /
                           f"{hashlib.sha256(original).hexdigest()}.metadata.json").read_text())
    assert metadata["reference_date"] == "2026-11-01"
    assert metadata["collected_at"] != metadata["reference_date"]


def test_rejects_html_disguised_as_csv():
    try:
        validate_download(b"<!doctype html><html>error</html>", "csv")
    except ValueError as exc:
        assert "HTML" in str(exc)
    else:
        raise AssertionError("HTML error page must not be stored as CSV")


def test_mvp_allowlist_has_csv_file_and_api():
    assert DEFAULT_SOURCE_IDS == (
        "giheung_events", "library_new_books", "public_facilities"
    )
    validate_download("제목,장소\n행사,용인\n".encode("cp949"), "csv")


def test_api_rejects_other_city_before_storing(tmp_path):
    source = Source("public_facilities", "api", "https://example.org/api")
    payload = {"response": {"header": {"resultCode": "00"},
                            "body": {"items": [{"rdnmadr": "서울특별시"}],
                                     "totalCount": 1}}}
    def handler(request):
        return httpx.Response(200, json=payload)
    store = Store(tmp_path / "raw", tmp_path / "state")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            collect_api(source, store, client, "test-key")
        except ValueError as exc:
            assert "outside Yongin" in str(exc)
        else:
            raise AssertionError("non-Yongin record should be rejected")
    assert not (tmp_path / "raw" / "public_facilities").exists()


def test_api_item_shape():
    rows, count = _api_items({"response": {"body": {"items": {"item": {
        "rdnmadr": "경기도 용인시 수지구"}}, "totalCount": "1"}}})
    assert count == 1
    assert len(rows) == 1
