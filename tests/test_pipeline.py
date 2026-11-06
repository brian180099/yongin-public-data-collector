import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yongin_collector.api import app
from yongin_collector.pipeline import (
    QualityError, compare_snapshot, prepare_csv_snapshot, validate_deletion_rate,
    validate_vehicle_snapshot, prepare_facility_snapshot,
)
from yongin_collector.store import Store


HEADERS = "관리번호,제목,시작일,종료일,데이터기준일자\n"


def snapshot(*rows: str):
    return prepare_csv_snapshot(
        (HEADERS + "\n".join(rows) + "\n").encode("utf-8"),
        unique_key_columns=["관리번호"],
        required_columns=["관리번호", "제목", "시작일", "종료일", "데이터기준일자"],
        reference_date_column="데이터기준일자",
    )


def previous_from(current):
    return {
        key: {"payload": value, "payload_hash": current.hashes[key], "active": True}
        for key, value in current.records.items()
    }


def test_row_order_does_not_create_modifications():
    first = snapshot(
        "A,행사 A,2026-01-01,2026-01-02,2026-01-01",
        "B,행사 B,2026-02-01,2026-02-02,2026-01-01",
    )
    reordered = snapshot(
        "B,행사 B,2026-02-01,2026-02-02,2026-01-01",
        "A,행사 A,2026-01-01,2026-01-02,2026-01-01",
    )
    changes = compare_snapshot(reordered, previous_from(first), full_snapshot=True)
    assert changes["modified"] == []
    assert changes["added"] == []
    assert changes["deleted_candidate"] == []
    assert changes["unchanged"] == ["A", "B"]


def test_add_modify_and_delete_candidate_are_separate():
    first = snapshot(
        "A,행사 A,2026-01-01,2026-01-02,2026-01-01",
        "B,행사 B,2026-02-01,2026-02-02,2026-01-01",
    )
    changed = snapshot(
        "A,행사 A 수정,2026-01-01,2026-01-02,2026-01-01",
        "C,행사 C,2026-03-01,2026-03-02,2026-01-01",
    )
    changes = compare_snapshot(changed, previous_from(first), full_snapshot=True)
    assert changes == {
        "added": ["C"], "modified": ["A"], "unchanged": [],
        "deleted_candidate": ["B"],
    }


def test_incremental_response_never_marks_deletions():
    first = snapshot(
        "A,행사 A,2026-01-01,2026-01-02,2026-01-01",
        "B,행사 B,2026-02-01,2026-02-02,2026-01-01",
    )
    partial = snapshot("A,행사 A,2026-01-01,2026-01-02,2026-01-01")
    changes = compare_snapshot(partial, previous_from(first), full_snapshot=False)
    assert changes["deleted_candidate"] == []


def test_duplicate_or_missing_keys_block_snapshot():
    with pytest.raises(QualityError, match="duplicate"):
        snapshot(
            "A,행사 A,2026-01-01,2026-01-02,2026-01-01",
            "A,행사 A2,2026-01-03,2026-01-04,2026-01-01",
        )
    with pytest.raises(QualityError, match="required values"):
        snapshot(",행사,2026-01-01,2026-01-02,2026-01-01")


def test_abnormal_mass_deletion_is_blocked():
    with pytest.raises(QualityError, match="mass deletion"):
        validate_deletion_rate(20, 7)
    validate_deletion_rate(20, 5)


def test_payload_hash_is_stable_for_unicode_json():
    prepared = snapshot("A,문화 행사,2026-01-01,2026-01-02,2026-01-01")
    assert len(prepared.hashes["A"]) == 64
    assert json.dumps(prepared.records["A"], ensure_ascii=False)


def test_vehicle_counts_must_be_numeric_and_consistent():
    headers = (
        "시군구,읍면동,용도별 관용,용도별 자가용,용도별 영업용,"
        "차종별 승용,차종별 승합,차종별 화물,차종별 특수,데이터기준일자\n"
    )

    def prepare(counts: str):
        return prepare_csv_snapshot(
            (headers + f"수지구,죽전동,{counts},2026-04-02\n").encode(),
            unique_key_columns=["시군구", "읍면동"],
            required_columns=headers.strip().split(","),
            reference_date_column="데이터기준일자",
        )

    good = validate_vehicle_snapshot(prepare("1,7,2,6,2,2,0"))
    assert good.reference_date.isoformat() == "2026-04-02"
    assert good.quality["vehicle_count_validation"] == "passed"
    with pytest.raises(QualityError, match="nonnegative integer"):
        validate_vehicle_snapshot(prepare("1,seven,2,6,2,2,0"))
    with pytest.raises(QualityError, match="totals disagree"):
        validate_vehicle_snapshot(prepare("1,7,2,7,2,2,0"))


def test_facility_snapshot_checks_all_pages_and_yongin_keys(tmp_path):
    store = Store(tmp_path / "raw", tmp_path / "state")

    def artifact(page_no, items):
        return {
            "item_id": f"page_{page_no}", "extension": "json",
            "content": json.dumps({
                "header": {"resultCode": "00"},
                "body": {"items": {"item": items}, "totalCount": 3},
            }, ensure_ascii=False).encode(),
            "source_url": "https://api.data.go.kr/openapi/example",
        }

    first = {"insttCode": "1", "openFcltyNm": "체육관", "openLcNm": "강당",
             "rdnmadr": "경기도 용인시 수지구", "lnmadr": "",
             "referenceDate": "2026-09-30"}
    second = {**first, "openLcNm": "회의실", "rdnmadr": "",
              "lnmadr": "경기도 용인시 기흥구"}
    other = {**first, "insttCode": "2", "rdnmadr": "서울특별시 중구"}
    store.save_many("public_facilities", [artifact(1, [first, other]),
                                          artifact(2, [second])])
    result = {"pages": 2, "source_total_count": 3, "found": 2}
    snapshot, artifacts = prepare_facility_snapshot(store, result)
    assert len(snapshot.records) == 2
    assert len(artifacts) == 2
    assert snapshot.reference_date.isoformat() == "2026-09-30"
    assert snapshot.quality["source_record_count"] == 3

    with pytest.raises(QualityError, match="count mismatch"):
        prepare_facility_snapshot(store, {**result, "found": 3})
    store.save_many("public_facilities", [artifact(2, [first])])
    with pytest.raises(QualityError, match="duplicate facility record key"):
        prepare_facility_snapshot(store, result)


def test_collector_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "service": "yongin-public-data-collector"
    }


def test_weekly_n8n_workflow_has_connected_operational_nodes():
    root = Path(__file__).resolve().parents[1]
    workflow = json.loads(
        (root / "workflows" / "n8n" / "yongin-weekly-collector.json")
        .read_text(encoding="utf-8")
    )
    names = {node["name"] for node in workflow["nodes"]}
    assert workflow["name"] == "YONGIN_01_공공데이터_수집갱신"
    assert workflow["active"] is True
    assert workflow["settings"]["timezone"] == "Asia/Seoul"
    assert len(workflow["nodes"]) == 16
    assert {
        "수동 실행", "매주 월요일 오전 9시", "데이터셋별 반복",
        "Python 수집·비교·반영 실행", "실패 여부 확인",
        "변경 없음 여부 확인", "전체 결과 취합",
    }.issubset(names)
    schedule = next(node for node in workflow["nodes"]
                    if node["name"] == "매주 월요일 오전 9시")
    interval = schedule["parameters"]["rule"]["interval"][0]
    assert interval == {
        "field": "weeks", "weeksInterval": 1, "triggerAtDay": [1],
        "triggerAtHour": 9, "triggerAtMinute": 0,
    }
    connected = set(workflow["connections"])
    assert names - {"전체 결과 취합"} <= connected
    serialized = json.dumps(workflow)
    assert "SUPABASE" not in serialized
    assert "DATA_GO_KR_SERVICE_KEY" not in serialized
