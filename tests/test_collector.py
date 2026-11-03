import hashlib
import json
from pathlib import Path
import sys

import httpx

from yongin_collector.collect import (
    _api_items, collect_api, collect_odcloud_api, collect_portal_file,
    discover_files, resolve_odcloud_api_url, validate_download,
)
from yongin_collector.cli import main
from yongin_collector.sources import DEFAULT_SOURCE_IDS, SOURCES, Source
from yongin_collector.store import Store


ROOT = Path(__file__).resolve().parents[1]


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


def test_rejects_pk_bytes_disguised_as_xlsx():
    try:
        validate_download(b"PK\x03\x04not-a-real-zip", "xlsx")
    except ValueError as exc:
        assert "XLSX" in str(exc)
    else:
        raise AssertionError("invalid ZIP bytes must not be stored as XLSX")


def test_mvp_allowlist_has_csv_file_and_api():
    assert DEFAULT_SOURCE_IDS == (
        "giheung_events", "library_new_books", "public_facilities",
        "vehicle_registrations", "vehicle_registrations_api",
    )
    assert SOURCES["vehicle_registrations"].portal_id == "3035912"
    assert SOURCES["vehicle_registrations_api"].application_url
    validate_download("제목,장소\n행사,용인\n".encode("cp949"), "csv")


def test_api_rejects_other_city_before_storing(tmp_path):
    source = Source("public_facilities", "api", "https://example.org/api")
    payload = {"response": {"header": {"resultCode": "00"},
                            "body": {"items": [{"rdnmadr": "서울특별시",
                                                 "lnmadr": "서울특별시",
                                                 "referenceDate": "2026-01-01"}],
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


def _portal_html(*detail_ids: str) -> str:
    return "".join(
        f"fileDetailObj.fn_fileDataDown('123', '{detail}', '','{number}', '1')"
        for number, detail in enumerate(detail_ids, start=1)
    )


def test_portal_file_initial_rerun_change_and_partial_failure(tmp_path):
    source = Source("files", "portal_file", "https://example.org/detail", "123")
    current = {"1": b"name,city\npark,Yongin\n"}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == source.url:
            return httpx.Response(200, text=_portal_html("detail-a"))
        if request.url.path.endswith("selectFileDataDownload.do"):
            number = request.url.params["fileDetailSn"]
            return httpx.Response(200, json={
                "status": True, "atchFileId": "attachment",
                "fileDetailSn": number,
                "dataSetFileDetailInfo": {"dataNm": f"sample_2026110{number}.csv"},
            })
        if request.url.path.endswith("check-limit.json"):
            return httpx.Response(200, json={"needCaptcha": False})
        if request.url.path.endswith("fileDownload.do"):
            number = request.url.params["fileDetailSn"]
            return httpx.Response(
                200, content=current[number],
                headers={"content-disposition":
                         f'attachment; filename="sample_2026110{number}.csv"'},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    store = Store(tmp_path / "raw", tmp_path / "state")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = collect_portal_file(source, store, client, refresh_existing=True)
        assert first == {"source": "files", "found": 1, "saved": 1, "unchanged": 0}
        first_hash = store.manifest("files")["items"]["detail-a:1:1"]["sha256"]

        rerun = collect_portal_file(source, store, client, refresh_existing=True)
        assert rerun["saved"] == 0
        assert rerun["unchanged"] == 1

        current["1"] = b"name,city\npool,Yongin\n"
        changed = collect_portal_file(source, store, client, refresh_existing=True)
        assert changed["saved"] == 1
        assert store.manifest("files")["items"]["detail-a:1:1"]["sha256"] != first_hash
        assert (tmp_path / "raw" / "files" / f"{first_hash}.csv").exists()

        stable_manifest = store.manifest("files")

        def failing_handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == source.url:
                return httpx.Response(200, text=_portal_html("detail-a", "detail-b"))
            if request.url.path.endswith("selectFileDataDownload.do"):
                number = request.url.params["fileDetailSn"]
                return httpx.Response(200, json={
                    "status": True, "atchFileId": "attachment",
                    "fileDetailSn": number,
                    "dataSetFileDetailInfo": {"dataNm": f"sample_2026110{number}.csv"},
                })
            if request.url.path.endswith("check-limit.json"):
                return httpx.Response(200, json={"needCaptcha": False})
            number = request.url.params["fileDetailSn"]
            content = (b"name,city\nchanged,Yongin\n" if number == "1"
                       else b"<!doctype html><html>error</html>")
            return httpx.Response(200, content=content, headers={
                "content-disposition":
                    f'attachment; filename="sample_2026110{number}.csv"'
            })

        with httpx.Client(transport=httpx.MockTransport(failing_handler)) as failing:
            try:
                collect_portal_file(source, store, failing, refresh_existing=True)
            except ValueError as exc:
                assert "HTML" in str(exc)
            else:
                raise AssertionError("second-file failure must fail the whole collection")
        assert store.manifest("files") == stable_manifest


def test_api_stores_response_shape_counts_and_reference_dates(tmp_path):
    source = Source("public_facilities", "api", "https://example.org/api")
    items = [
        {"rdnmadr": "경기도 용인시 수지구", "lnmadr": "",
         "referenceDate": "2026-10-01", "openFcltyNm": "회의실"},
        {"rdnmadr": "", "lnmadr": "경기도 용인시 기흥구",
         "referenceDate": "2026-10-02", "openFcltyNm": "체육관"},
    ]
    payload = {"response": {"header": {"resultCode": "00"},
                            "body": {"items": items, "totalCount": 2}}}

    def handler(request):
        assert request.url.params["serviceKey"] == "secret"
        return httpx.Response(200, json=payload)

    store = Store(tmp_path / "raw", tmp_path / "state")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = collect_api(source, store, client, "secret")
    assert result == {"source": "public_facilities", "found": 2, "saved": 1,
                      "unchanged": 0, "pages": 1, "total_count": 2,
                      "field_count": 4}
    metadata = store.manifest("public_facilities")["items"]["page_1"]
    assert metadata["reference_date"] == "2026-10-02"
    assert metadata["http_status"] == 200
    assert metadata["response"]["record_count"] == 2
    assert metadata["response"]["reference_dates"] == ["2026-10-01", "2026-10-02"]
    assert "secret" not in json.dumps(metadata, ensure_ascii=False)


def test_failed_api_pagination_does_not_commit_first_page(tmp_path):
    source = Source("public_facilities", "api", "https://example.org/api")
    valid = {"rdnmadr": "경기도 용인시", "lnmadr": "",
             "referenceDate": "2026-10-01"}

    def handler(request):
        page = int(request.url.params["pageNo"])
        items = [valid] * 1000 if page == 1 else [{"rdnmadr": "서울특별시"}]
        return httpx.Response(200, json={
            "response": {"header": {"resultCode": "00"},
                         "body": {"items": items, "totalCount": 1001}}
        })

    store = Store(tmp_path / "raw", tmp_path / "state")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            collect_api(source, store, client, "secret")
        except ValueError as exc:
            assert "required facility fields" in str(exc)
        else:
            raise AssertionError("invalid second page must fail the whole collection")
    assert store.manifest("public_facilities")["items"] == {}


def test_n8n_daily_template_is_inactive_key_free_and_kst():
    path = ROOT / "workflows" / "n8n" / "daily-collector.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(workflow)
    assert workflow["active"] is False
    assert workflow["settings"]["timezone"] == "Asia/Seoul"
    schedule = next(node for node in workflow["nodes"]
                    if node["type"] == "n8n-nodes-base.scheduleTrigger")
    interval = schedule["parameters"]["rule"]["interval"][0]
    assert interval["field"] == "days"
    assert interval["triggerAtHour"] == 7
    command = next(node for node in workflow["nodes"]
                   if node["type"] == "n8n-nodes-base.executeCommand")
    assert "python -m yongin_collector daily" in command["parameters"]["command"]
    assert "DATA_GO_KR_SERVICE_KEY" not in serialized


def _vehicle_item(reference_date="2025-12-31"):
    return {
        "시군구": "용인시", "읍면동": "처인구", "용도별 관용": "1",
        "용도별 자가용": "2", "용도별 영업용": "3", "차종별 승용": "4",
        "차종별 승합": "5", "차종별 화물": "6", "차종별 특수": "7",
        "데이터기준일자": reference_date,
    }


def _vehicle_api_source():
    configured = SOURCES["vehicle_registrations_api"]
    return Source(
        configured.source_id, configured.kind, "https://example.org/api",
        required_fields=configured.required_fields,
    )


def test_odcloud_api_uses_header_and_preserves_validated_response(tmp_path):
    source = _vehicle_api_source()
    payload = {"page": 1, "perPage": 1000, "totalCount": 2,
               "currentCount": 2, "matchCount": 2,
               "data": [_vehicle_item(), _vehicle_item("2025-11-30")]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert "serviceKey" not in request.url.params
        assert request.headers["Authorization"] == "Infuser secret-key"
        return httpx.Response(200, json=payload)

    store = Store(tmp_path / "raw", tmp_path / "state")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = collect_odcloud_api(source, store, client, "secret-key")
    assert result == {
        "source": "vehicle_registrations_api", "found": 2, "saved": 1,
        "unchanged": 0, "pages": 1, "total_count": 2, "field_count": 10,
    }
    metadata = store.manifest(source.source_id)["items"]["page_1"]
    assert metadata["reference_date"] == "2025-12-31"
    assert metadata["response"]["total_count"] == 2
    assert "secret-key" not in json.dumps(metadata, ensure_ascii=False)


def test_odcloud_api_rejects_invalid_second_page_without_commit(tmp_path):
    source = _vehicle_api_source()

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        data = [_vehicle_item()] * 1000 if page == 1 else [{"시군구": "용인시"}]
        return httpx.Response(200, json={
            "page": page, "perPage": 1000, "totalCount": 1001,
            "currentCount": len(data), "matchCount": 1001, "data": data,
        })

    store = Store(tmp_path / "raw", tmp_path / "state")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            collect_odcloud_api(source, store, client, "secret-key")
        except ValueError as exc:
            assert "required vehicle fields" in str(exc)
        else:
            raise AssertionError("invalid second page must fail the whole collection")
    assert store.manifest(source.source_id)["items"] == {}


def test_apply_mode_reports_manual_portal_action(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "yongin-collect", "apply", "--source", "vehicle_registrations_api"
    ])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "manual_action_required"
    assert result["requires_login"] is True
    assert result["application_url"].endswith("/data/3035912/fileData.do")


def test_odcloud_url_resolves_current_portal_file_against_oas():
    source = SOURCES["vehicle_registrations_api"]
    detail_id = "uddi:current"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.data.go.kr":
            html = (
                "fileDetailObj.fn_fileDataDown('3035912', "
                f"'{detail_id}', '','1', '1')"
            )
            return httpx.Response(200, text=html)
        assert request.url.host == "infuser.odcloud.kr"
        assert request.url.params["namespace"] == "3035912/v1"
        return httpx.Response(200, json={
            "host": "api.odcloud.kr", "basePath": "/api",
            "schemes": ["https"],
            "paths": {f"/3035912/v1/{detail_id}": {"get": {}}},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resolved = resolve_odcloud_api_url(source, client)
    assert resolved == f"https://api.odcloud.kr/api/3035912/v1/{detail_id}"
