"""Synthetic portal detail examples; no live credentials or portal HTML."""

import json

import pytest
from dotenv import dotenv_values

from yongin_collector.portal_application import (
    parse_approved_application, save_approved_application,
)


PORTAL_URL = "https://www.data.go.kr/iim/api/applicationDetail.do"
TEXT = (
    "[개발계정] 공공시설개방정보 기본 정보 처리상태 승인 "
    "서비스 정보 End Point https://api.data.go.kr/openapi/facilities "
    "일반 인증키 syntheticGeneralKey0123456789"
)


def test_approved_allowlisted_detail_is_saved_without_secret_in_status(tmp_path):
    application = parse_approved_application("public_facilities", TEXT, PORTAL_URL)
    status = save_approved_application(
        application, tmp_path, "https://api.data.go.kr/openapi/facilities"
    )
    assert dotenv_values(tmp_path / "collector.env")["DATA_GO_KR_SERVICE_KEY"] == (
        "syntheticGeneralKey0123456789"
    )
    assert status["status"] == "approved_key_saved_call_unverified"
    assert status["endpoint_matches_collector"] is True
    assert "syntheticGeneralKey" not in json.dumps(status)
    assert "syntheticGeneralKey" not in (tmp_path / "portal_application_status.json").read_text()


@pytest.mark.parametrize("source,text,url", [
    ("public_facilities", TEXT.replace("공공시설개방정보", "관내 기업 현황"), PORTAL_URL),
    ("public_facilities", TEXT.replace("처리상태 승인", "처리상태 신청"), PORTAL_URL),
    ("public_facilities", TEXT.replace("일반 인증키", "인증키 없음"), PORTAL_URL),
    ("public_facilities", TEXT, "https://example.com/detail"),
    ("public_facilities", TEXT.replace("https://api.data.go.kr/openapi/facilities",
                                     "https://api.data.go.kr/openapi/facilities?key=leak"),
     PORTAL_URL),
    ("vehicle_registrations_api", TEXT, PORTAL_URL),
])
def test_rejects_wrong_or_incomplete_application(source, text, url):
    with pytest.raises(ValueError):
        parse_approved_application(source, text, url)
