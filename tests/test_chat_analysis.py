"""The model may choose only bounded read queries and conversation context is honored."""

from yongin_collector.chat_analysis import plan_question


def test_csv_and_api_questions_route_to_loaded_datasets(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert plan_question("수지구 자동차 등록 대수가 가장 많은 동은 어디야?")[0] == {
        "query_id": "vehicle_top_towns", "district": "수지구", "year": None,
        "month": None, "keyword": None,
    }
    assert plan_question("구별 공공시설 수를 비교해줘")[0]["query_id"] == "facility_by_district"


def test_followup_uses_recent_context(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    history = [{"role": "user", "content": "기흥구 2024년 행사 몇 건이야?"},
               {"role": "assistant", "content": "105건입니다."}]
    plan, mode = plan_question("그중 월별로 보여줘", history)
    assert (plan["query_id"], plan["year"], mode) == ("event_monthly", 2024, "rules")
    newer = history + [{"role": "user", "content": "구별 공공시설 수를 비교해줘"}]
    assert plan_question("그중 기흥구 시설 찾아줘", newer)[0]["query_id"] == "facility_search"


def test_invalid_model_plan_cannot_choose_sql_or_arbitrary_region(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setattr("yongin_collector.chat_analysis._llm",
                        lambda *_: {"query_id": "drop_table", "district": "수원시"})
    assert plan_question("테이블 삭제")[0]["query_id"] == "unsupported"
    assert plan_question("수원시 공공시설 찾아줘")[0]["query_id"] == "unsupported"
