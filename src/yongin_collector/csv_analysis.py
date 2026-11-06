"""Bounded, read-only question handling for reviewed CSV snapshots."""

import json
import os
import re

import httpx

from .analysis_db import analysis_pool


STOPWORDS = ("경기도", "용인시", "용인", "홈페이지", "정보", "관련", "데이터", "알려줘",
             "보여줘", "찾아줘", "조회", "분석", "현황", "전체", "몇", "건", "개", "있어")
TOPICS = {
    "숲체험일정": "portal_zip_forest_schedule",
    "숲체험교육": "portal_zip_forest_classes",
    "도서관달력": "portal_zip_library_calendar",
    "견학달력": "portal_zip_library_tours",
    "연간행사": "portal_zip_library_annual_events",
    "마라톤코스": "portal_zip_reading_marathon_courses",
    "마라톤": "portal_zip_reading_marathon",
    "교육기관": "portal_zip_lifelong_institutions",
}


def _compact(value: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", value).lower()


def _catalog(cursor):
    cursor.execute("""select dataset_id, display_name, provider, portal_url,
                           reference_date, collected_at, last_success_at
                    from analytics.dataset_sources
                    where dataset_id like 'portal_csv_%' or dataset_id like 'portal_zip_%'
                    order by dataset_id""")
    return [dict(row) for row in cursor.fetchall()]


def _choose(question: str, catalog: list[dict]):
    compact = _compact(question)
    by_id = {row["dataset_id"]: row for row in catalog}
    for phrase, dataset_id in TOPICS.items():
        if phrase in compact and dataset_id in by_id:
            return by_id[dataset_id], []
    scores = []
    for row in catalog:
        title = row["display_name"].split(" / ")[-1]
        title = title.split("_")[-1]
        words = [w for w in re.findall(r"[가-힣A-Za-z0-9]+", title)
                 if len(w) >= 2 and w not in STOPWORDS]
        score = sum(len(w) for w in words if _compact(w) in compact)
        if score:
            scores.append((score, row))
    scores.sort(key=lambda pair: (-pair[0], pair[1]["dataset_id"]))
    if not scores:
        return None, []
    top = scores[0][0]
    tied = [row for score, row in scores if score == top]
    if len(tied) > 1:
        return None, tied[:5]
    return scores[0][1], []


def _llm_csv(question: str, history: list[dict], catalog: list[dict]) -> dict:
    """Let the model choose a reviewed dataset and bounded operation, never SQL."""
    dataset_ids = [row["dataset_id"] for row in catalog]
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "dataset_id": {"type": "string", "enum": dataset_ids + ["unsupported"]},
            "operation": {"type": "string", "enum": ["count", "records", "catalog", "unsupported"]},
            "needs_filter": {"type": "boolean"},
            "keyword": {"type": ["string", "null"]},
        },
        "required": ["dataset_id", "operation", "needs_filter", "keyword"],
    }
    dataset_lines = "\n".join(f"{row['dataset_id']}: {row['display_name']}"
                              for row in catalog)
    instructions = (
        "Interpret the Korean question using only the reviewed Yongin CSV datasets below. "
        "Choose catalog for a general list, count for the entire current snapshot, "
        "records for up to ten example rows, or unsupported if no dataset fits. "
        "Set needs_filter=true if the question requests a date, district, comparison, "
        "ranking, calculation, or a condition beyond a simple keyword search. "
        "A short keyword may filter record values; otherwise set keyword=null. "
        "Never write SQL or invent a dataset. Use conversation context for follow-ups.\n"
        + dataset_lines
    )
    messages = [{"role": item["role"], "content": item["content"][:500]}
                for item in history[-6:] if item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)]
    messages.append({"role": "user", "content": question})
    with httpx.Client(timeout=20) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                  "instructions": instructions, "input": messages,
                  "store": False, "max_output_tokens": 250,
                  "text": {"format": {"type": "json_schema", "name": "yongin_csv_plan",
                                      "strict": True, "schema": schema}}},
        )
        response.raise_for_status()
        body = response.json()
    if body.get("status") != "completed":
        raise ValueError("incomplete model response")
    parts = [part.get("text", "") for item in body.get("output", [])
             for part in item.get("content", []) if part.get("type") == "output_text"]
    return json.loads("".join(parts))


def analyze_csv(question: str, request_id: str, conversation_id: str | None,
                history: list[dict] | None = None):
    """Return a catalog, exact snapshot count or up to ten raw records."""
    dsn = os.getenv("SUPABASE_ANALYSIS_DB_URL") or os.getenv("SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError("database is not configured")
    result = {"request_id": request_id, "conversation_id": conversation_id,
              "status": "unsupported", "intent": "csv_catalog", "interpreter": "rules",
              "answer": "", "filters": {}, "result": [], "visualization": None,
              "sources": [], "calculation": None, "limitations": []}
    if re.search(r"수원시|성남시|서울시|화성시|안양시|삭제|수정|업데이트|DROP|INSERT|UPDATE|DELETE",
                 question, re.I):
        return result
    with analysis_pool(dsn).connection() as conn:
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute("set transaction read only")
                cursor.execute("set local statement_timeout = '5000ms'")
                cursor.execute("set local role yongin_analysis_reader")
                catalog = _catalog(cursor)
                model_plan = None
                if os.getenv("OPENAI_API_KEY", "").strip():
                    try:
                        model_plan = _llm_csv(question, history or [], catalog)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        pass
                catalog_requested = bool(re.search(r"어떤|목록|종류|데이터셋", question)
                                         and not re.search(r"숲|도서|체육|행사|교육|관광|공원|시설", question))
                if model_plan and model_plan.get("operation") == "catalog":
                    catalog_requested = True
                if catalog_requested:
                    result["status"] = "ok"
                    result["interpreter"] = "llm" if model_plan else "rules"
                    result["answer"] = f"검증해 적재한 용인 생활여가·문화·체육 CSV 데이터셋은 {len(catalog)}종입니다. 앞의 10종을 보여드립니다. 주제를 더 구체적으로 물어보세요."
                    result["result"] = [{"dataset_id": row["dataset_id"],
                                         "dataset_name": row["display_name"]}
                                        for row in catalog[:10]]
                    return result
                selected, tied = _choose(question, catalog)
                if model_plan and model_plan.get("dataset_id") in {
                        row["dataset_id"] for row in catalog}:
                    selected = next(row for row in catalog
                                    if row["dataset_id"] == model_plan["dataset_id"])
                    tied = []
                    result["interpreter"] = "llm"
                if tied:
                    result["status"] = "clarification"
                    result["answer"] = "어느 자료를 뜻하는지 선택해 주세요: " + ", ".join(
                        row["display_name"] for row in tied)
                    return result
                if not selected:
                    return result
                dataset_id = selected["dataset_id"]
                keyword = model_plan.get("keyword") if model_plan else None
                if keyword is not None and (not isinstance(keyword, str)
                                            or len(keyword) > 40
                                            or not re.fullmatch(r"[가-힣A-Za-z0-9 ]+", keyword)):
                    keyword = None
                if not keyword:
                    explicit = re.search(r"(?:검색어|키워드)\s*[:：]?\s*['\"]([^'\"]{1,40})['\"]", question)
                    keyword = explicit.group(1) if explicit else None
                if ((model_plan and model_plan.get("needs_filter") is True) or
                        re.search(r"(?<!\d)20\d{2}(?!\d)|\d{1,2}월|처인구|기흥구|수지구|"
                                  r"월별|연도별|구별|비교|평균|추세|가장|순위|합계|"
                                  r"오늘|내일|이번|지난|다음|이달|올해|최근|부터|까지", question)):
                    result["status"] = "clarification"
                    result["answer"] = ("이 자료는 현재 전체 적재 건수와 원본 행 조회를 지원합니다. "
                                        "기간·지역 필터나 비교 계산은 컬럼별 분석 계약을 검증한 뒤 제공하겠습니다.")
                    return result
                wants_count = bool(re.search(r"몇|건수|개수|총|전체", question))
                if model_plan and model_plan.get("operation") in {"count", "records"}:
                    wants_count = model_plan["operation"] == "count"
                result["intent"] = "csv_count" if wants_count else "csv_records"
                result["filters"] = {"dataset_id": dataset_id, "keyword": keyword}
                source = {"dataset_id": dataset_id,
                          "dataset_name": selected["display_name"],
                          "provider": selected["provider"],
                          "url": selected["portal_url"],
                          "reference_date": str(selected["reference_date"]) if selected["reference_date"] else None,
                          "collected_at": selected["collected_at"].isoformat() if selected["collected_at"] else None,
                          "last_success_at": selected["last_success_at"].isoformat() if selected["last_success_at"] else None}
                result["sources"] = [source]
                result["limitations"] = ["원본 CSV의 현재 적재 행 기준입니다. 실제 운영 상태나 현재 예약 가능 여부와 다를 수 있습니다."]
                if keyword:
                    result["limitations"].append("검색어는 원본 행의 텍스트 값에 포함되는지 확인합니다.")
                pattern = "%" + (keyword or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                if result["intent"] == "csv_count":
                    cursor.execute("""select count(*)::int as count
                                    from analytics.current_dataset_records
                                    where dataset_id=%s and (%s::text is null or
                                    exists (select 1 from jsonb_each_text(payload) v
                                            where v.value ilike %s escape '\\'))""",
                                   (dataset_id, keyword, pattern))
                    count = cursor.fetchone()["count"]
                    result["result"] = [{"count": count}]
                    result["answer"] = f"{selected['display_name']}의 {'검색 결과' if keyword else '적재 행'}는 {count:,}건입니다."
                    result["calculation"] = {"query_id": "csv_count", "dataset_id": dataset_id,
                                             "measure": "현재 적재 행 수"}
                else:
                    cursor.execute("""select payload from analytics.current_dataset_records
                                    where dataset_id=%s and (%s::text is null or
                                    exists (select 1 from jsonb_each_text(payload) v
                                            where v.value ilike %s escape '\\'))
                                    order by record_key limit 10""",
                                   (dataset_id, keyword, pattern))
                    result["result"] = [dict(row["payload"]) for row in cursor.fetchall()]
                    result["answer"] = f"{selected['display_name']} {'검색 결과' if keyword else '원본 행'}를 최대 10건 보여드립니다."
                    result["calculation"] = {"query_id": "csv_records", "dataset_id": dataset_id,
                                             "measure": "원본 행 조회"}
                result["status"] = "ok" if result["result"] else "empty"
    return result
