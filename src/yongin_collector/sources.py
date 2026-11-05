"""Explicit MVP allowlist; the 351-result search page is discovery only."""

from dataclasses import dataclass

from .csv_allowlist import CSV_ALLOWLIST, ZIP_CSV_CONTRACTS


SEARCH_URL = (
    "https://www.data.go.kr/tcs/dss/selectDataSetList.do?"
    "keyword=%EC%9A%A9%EC%9D%B8%EC%8B%9C&conditionType=search&org=&orgFilter=&orgFullName="
)


@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str
    url: str
    portal_id: str | None = None
    max_files: int = 20
    application_url: str | None = None
    required_fields: tuple[str, ...] = ()
    zip_marker: str | None = None
    allow_large_zip: bool = False


SOURCES = {
    "suji_programs": Source(
        "suji_programs", "page", "https://www.sujigu.go.kr/lmth/04life0703.asp"
    ),
    "library_new_books": Source(
        "library_new_books", "portal_file",
        "https://www.data.go.kr/data/3038399/fileData.do", "3038399"
    ),
    "giheung_events": Source(
        "giheung_events", "portal_file",
        "https://www.data.go.kr/data/15136583/fileData.do", "15136583"
    ),
    "public_facilities": Source(
        "public_facilities", "api",
        "https://api.data.go.kr/openapi/tn_pubr_public_pblfclt_opn_info_api",
        "15013117",
        application_url="https://www.data.go.kr/data/15013117/standard.do",
    ),
    "vehicle_registrations": Source(
        "vehicle_registrations", "portal_file",
        "https://www.data.go.kr/data/3035912/fileData.do", "3035912"
    ),
    "vehicle_registrations_api": Source(
        "vehicle_registrations_api", "odcloud_api",
        "https://api.odcloud.kr/api/3035912/v1/"
        "uddi:2310ae65-f196-4e39-8235-906b9bb69cb7",
        "3035912",
        application_url="https://www.data.go.kr/data/3035912/fileData.do",
        required_fields=(
            "시군구", "읍면동", "용도별 관용", "용도별 자가용", "용도별 영업용",
            "차종별 승용", "차종별 승합", "차종별 화물", "차종별 특수",
            "데이터기준일자",
        ),
    ),
}

# Add only individually reviewed portal IDs. They are not automatic DB targets
# until a downloaded CSV passes schema/key review and is registered there.
SOURCES.update({
    f"portal_csv_{portal_id}": Source(
        f"portal_csv_{portal_id}", "portal_file",
        f"https://www.data.go.kr/data/{portal_id}/fileData.do", portal_id,
    )
    for portal_id in CSV_ALLOWLIST
})

SOURCES.update({
    f"portal_zip_{member_id}": Source(
        f"portal_zip_{member_id}", "portal_zip_member",
        f"https://www.data.go.kr/data/{portal_id}/fileData.do", portal_id,
        zip_marker=marker,
    )
    for member_id, (portal_id, marker, _, _) in ZIP_CSV_CONTRACTS.items()
})

DEFAULT_SOURCE_IDS = (
    "giheung_events", "library_new_books", "public_facilities",
    "vehicle_registrations", "vehicle_registrations_api",
)
