"""Synthetic portal detail examples; no live credentials or portal HTML."""

import json
from unittest.mock import MagicMock

import httpx
import pytest
from dotenv import dotenv_values

from scripts.sync_portal_application import (
    APPLICATION_LIST_URL, open_approved_detail, wait_for_login,
)
from yongin_collector.portal_application import (
    APPLICATION_TITLES, parse_approved_application, save_approved_application,
    verify_approved_application,
)


PORTAL_URL = "https://www.data.go.kr/iim/api/selectAPIAcountView.do"
ENDPOINT = "https://api.data.go.kr/openapi/facilities"
TEXT = (
    "[개발계정] 전국공공시설개방정보표준데이터 기본 정보 처리상태 승인 "
    "서비스 정보 End Point " + ENDPOINT + " "
    "일반 인증키 syntheticGeneralKey0123456789"
)


def test_approved_allowlisted_detail_is_saved_without_secret_in_status(tmp_path):
    application = parse_approved_application("public_facilities", TEXT, PORTAL_URL)
    status = save_approved_application(
        application, tmp_path, ENDPOINT, api_verified=True
    )
    assert dotenv_values(tmp_path / "collector.env")["DATA_GO_KR_SERVICE_KEY"] == (
        "syntheticGeneralKey0123456789"
    )
    assert status["status"] == "approved_key_verified_saved"
    assert status["endpoint_matches_collector"] is True
    assert "syntheticGeneralKey" not in json.dumps(status)
    assert "syntheticGeneralKey" not in (tmp_path / "portal_application_status.json").read_text()


@pytest.mark.parametrize("source,text,url", [
    ("public_facilities", TEXT.replace(APPLICATION_TITLES["public_facilities"],
                                       "관내 기업 현황"), PORTAL_URL),
    ("public_facilities", TEXT.replace("처리상태 승인", "처리상태 신청"), PORTAL_URL),
    ("public_facilities", TEXT.replace("일반 인증키", "인증키 없음"), PORTAL_URL),
    ("public_facilities", TEXT, "https://example.com/detail"),
    ("public_facilities", TEXT, "https://www.data.go.kr/iim/api/selectAcounList.do"),
    ("public_facilities", TEXT.replace("https://api.data.go.kr/openapi/facilities",
                                     "https://api.data.go.kr/openapi/facilities?key=leak"),
     PORTAL_URL),
    ("vehicle_registrations_api", TEXT, PORTAL_URL),
])
def test_rejects_wrong_or_incomplete_application(source, text, url):
    with pytest.raises(ValueError):
        parse_approved_application(source, text, url)


def test_endpoint_mismatch_keeps_existing_key(tmp_path):
    env_path = tmp_path / "collector.env"
    env_path.write_text("DATA_GO_KR_SERVICE_KEY=existingWorkingKey0123456789\n")
    application = parse_approved_application("public_facilities", TEXT, PORTAL_URL)
    with pytest.raises(ValueError, match="endpoint"):
        save_approved_application(application, tmp_path, ENDPOINT + "/different")
    assert dotenv_values(env_path)["DATA_GO_KR_SERVICE_KEY"] == (
        "existingWorkingKey0123456789"
    )


def test_decoding_key_characters_are_read_without_clipboard():
    candidate = "abcDEF0123456789+/abcDEF0123456789="
    application = parse_approved_application(
        "public_facilities", TEXT.replace("syntheticGeneralKey0123456789", candidate),
        PORTAL_URL,
    )
    assert application.key == candidate


def test_candidate_key_is_verified_before_saving():
    application = parse_approved_application("public_facilities", TEXT, PORTAL_URL)

    def handler(request):
        assert request.url.params["serviceKey"] == application.key
        return httpx.Response(200, json={
            "header": {"resultCode": "00"},
            "body": {"items": {"item": [{"rdnmadr": "경기도 용인시"}]},
                     "totalCount": 1},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        verify_approved_application(application, ENDPOINT, client)

    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(403, json={"error": "denied"}))) as client:
        with pytest.raises(ValueError) as error:
            verify_approved_application(application, ENDPOINT, client)
    assert application.key not in str(error.value)


def test_login_and_approved_detail_navigation_are_automatic():
    page = MagicMock()
    page.is_closed.return_value = False
    page.get_by_text.return_value.count.return_value = 1
    page.get_by_text.return_value.first.is_visible.return_value = True
    context = MagicMock(pages=[page])
    assert wait_for_login(context, timeout_seconds=1) is page

    page.url = APPLICATION_LIST_URL
    page.get_by_text.return_value.first.click.side_effect = (
        lambda: setattr(page, "url", PORTAL_URL)
    )
    assert open_approved_detail(
        context, page, APPLICATION_TITLES["public_facilities"]
    ) is page
    page.goto.assert_called_once_with(APPLICATION_LIST_URL,
                                      wait_until="domcontentloaded")
