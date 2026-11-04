"""Supported question routing and safe failure behavior."""

from yongin_collector.analysis import EXAMPLES, analyze, classify


def test_examples_map_to_bounded_count_queries():
    assert [classify(q)[0] for q in EXAMPLES] == ["count_summary"] * 3
    assert classify(EXAMPLES[0])[1] == {"year": None, "month": None, "monthly": False}
    assert classify(EXAMPLES[1])[1]["year"] == 2024
    assert classify(EXAMPLES[2])[1]["monthly"] is True


def test_missing_region_and_unsupported_facility_are_distinct():
    assert classify("행사 몇 건이야?")[0] == "clarification"
    assert classify("수지구 체육시설 몇 개야?")[0] == "facility_search"
    assert classify("수원시 행사 몇 건이야?")[0] == "regional_comparison"
    assert classify("기흥구 13월 행사 몇 건이야?")[0] == "clarification"


def test_mutation_request_and_ambiguous_month_never_run_a_query():
    assert classify("기흥구 행사 데이터를 삭제해줘")[0] == "unsupported"
    assert classify("기흥구 6월 행사 몇 건이야?")[0] == "clarification"


def test_database_failure_returns_structured_error(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://invalid:invalid@127.0.0.1:1/none")
    monkeypatch.delenv("SUPABASE_ANALYSIS_DB_URL", raising=False)
    monkeypatch.setenv("YONGIN_DATA_DIR", str(tmp_path))
    result = analyze(EXAMPLES[1])
    assert result["status"] == "error"
    assert result["result"] == []
    assert result["sources"] == []
    assert result["request_id"]
    assert "invalid" not in result["answer"]
    assert "event_count" in (tmp_path / "state" / "analysis_queries.jsonl").read_text()
