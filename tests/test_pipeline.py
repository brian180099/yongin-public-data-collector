import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yongin_collector.api import app
from yongin_collector.pipeline import (
    QualityError, compare_snapshot, prepare_csv_snapshot, validate_deletion_rate,
)


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
    assert workflow["active"] is False
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
