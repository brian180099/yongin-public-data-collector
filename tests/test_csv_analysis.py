import httpx
import json

from yongin_collector.csv_analysis import _choose, _llm_csv


def test_reviewed_zip_topic_selects_exact_dataset():
    catalog = [
        {"dataset_id": "portal_zip_forest_classes", "display_name": "용인시 숲체험교육 정보"},
        {"dataset_id": "portal_zip_forest_schedule", "display_name": "용인시 숲체험일정 정보"},
    ]
    selected, tied = _choose("숲체험일정 몇 건이야?", catalog)
    assert selected["dataset_id"] == "portal_zip_forest_schedule"
    assert tied == []


def test_ambiguous_topic_requests_clarification():
    catalog = [
        {"dataset_id": "portal_csv_1", "display_name": "용인시_도서관 A 정보"},
        {"dataset_id": "portal_csv_2", "display_name": "용인시_도서관 B 정보"},
    ]
    selected, tied = _choose("도서관 알려줘", catalog)
    assert selected is None
    assert len(tied) == 2


def test_csv_llm_plan_is_limited_to_reviewed_ids(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "completed", "output": [{
            "content": [{"type": "output_text", "text": (
                '{"dataset_id":"portal_zip_forest_schedule",'
                '"operation":"count","needs_filter":false,"keyword":null}')}] }]})

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    real_client = httpx.Client
    monkeypatch.setattr("yongin_collector.csv_analysis.httpx.Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler),
                                                     **kwargs))
    catalog = [{"dataset_id": "portal_zip_forest_schedule",
                "display_name": "용인시 숲체험일정 정보"}]
    plan = _llm_csv("숲체험 일정 몇 건?", [], catalog)
    assert plan == {"dataset_id": "portal_zip_forest_schedule",
                    "operation": "count", "needs_filter": False, "keyword": None}
    body = json.loads(requests[0].content)
    assert body["store"] is False
    assert body["text"]["format"]["schema"]["properties"]["dataset_id"]["enum"] == [
        "portal_zip_forest_schedule", "unsupported"]
