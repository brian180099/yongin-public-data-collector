"""Read-only, bounded public-data queries chosen from a validated chat plan."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row

from .store import ROOT
from .csv_analysis import analyze_csv

EXAMPLES = [
    "숲체험일정은 몇 건이야?",
    "도서관 달력 보여줘",
    "어떤 데이터셋이 있어?",
    "기흥구 2024년 행사 몇 건이야?",
    "기흥구 2024년 월별 행사 수를 보여줘",
    "수지구 자동차 등록 대수가 가장 많은 동은 어디야?",
    "구별 공공시설 수를 비교해줘",
    "기흥구의 테니스장 찾아줘",
]
QUERIES = (
    "event_count", "event_monthly", "event_list", "vehicle_total",
    "vehicle_by_district", "vehicle_top_towns", "vehicle_breakdown",
    "facility_count", "facility_by_district", "facility_search", "unsupported",
)
DISTRICTS = ("처인구", "기흥구", "수지구")
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "query_id": {"type": "string", "enum": list(QUERIES)},
        "district": {"type": ["string", "null"]},
        "year": {"type": ["integer", "null"]},
        "month": {"type": ["integer", "null"]},
        "keyword": {"type": ["string", "null"]},
    },
    "required": ["query_id", "district", "year", "month", "keyword"],
}


def _rules(question, history):
    text = question.strip()
    previous = next((str(m.get("content", "")) for m in reversed(history[-6:])
                     if m.get("role") == "user"), "")
    context = text if re.search(r"자동차|차량|등록 대수|시설|체육관|운동장|테니스|축구|풋살|행사|이벤트", text) else text + " " + previous
    if re.search(r"삭제|수정해|업데이트해|DROP|INSERT|UPDATE|DELETE", text, re.I):
        return {"query_id": "unsupported"}
    district = next((d for d in DISTRICTS if d in text), None)
    if not district and re.search(r"그중|그거|월별로|다시", text):
        district = next((d for d in DISTRICTS if d in previous), None)
    years = re.findall(r"(?<!\d)(20\d{2})년?", text)
    if not years and re.search(r"그중|월별로|다시", text):
        years = re.findall(r"(?<!\d)(20\d{2})년?", previous)
    months = re.findall(r"(?<!\d)(\d{1,2})월(?!별)", text)
    base = {"district": district, "year": int(years[-1]) if years else None,
            "month": int(months[-1]) if months else None, "keyword": None}
    if "자동차" in context or "차량" in context or "등록 대수" in context:
        if re.search(r"용도별|차종별|구성|종류", text):
            query = "vehicle_breakdown"
        elif re.search(r"가장 많은 동|상위.*동|동별|읍면동별", text):
            query = "vehicle_top_towns"
        else:
            query = "vehicle_by_district" if re.search(r"구별|지역별", text) else "vehicle_total"
        return {**base, "query_id": query}
    if re.search(r"시설|체육관|운동장|테니스|축구|풋살", context):
        keyword = next((w for w in ("테니스", "축구", "풋살", "운동장", "체육관") if w in text), None)
        query = "facility_by_district" if re.search(r"구별|지역별", text) else (
            "facility_count" if re.search(r"몇|건수|개수|수는", text) and not keyword else "facility_search")
        return {**base, "keyword": keyword, "query_id": query}
    if "행사" in context or "이벤트" in context:
        if "기흥구" not in context:
            return {"query_id": "unsupported"}
        query = "event_monthly" if re.search(r"월별|달별", text) else (
            "event_count" if re.search(r"몇|건수|개수|총|전체", text) else "event_list")
        return {**base, "district": "기흥구", "query_id": query}
    return {"query_id": "unsupported"}


def _llm(question, history):
    key = os.environ["OPENAI_API_KEY"]
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    messages = [{"role": m["role"], "content": m["content"][:500]}
                for m in history[-6:] if m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str)]
    messages.append({"role": "user", "content": question})
    instructions = (
        "Interpret Korean questions about loaded Yongin data. Choose one query_id only: "
        "event_count/monthly/list for Giheung events (start dates 2017-2024); "
        "vehicle_total/by_district/top_towns/breakdown for vehicle registrations; "
        "facility_count/by_district/search for Yongin public facilities. "
        "Resolve follow-up references from conversation. district: 처인구, 기흥구, 수지구 or null. "
        "year/month only for events; keyword is short facility search text. "
        "Use unsupported for out-of-scope, ambiguous or mutation requests. Never write SQL."
    )
    with httpx.Client(timeout=20) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "instructions": instructions, "input": messages,
                  "store": False, "max_output_tokens": 250,
                  "text": {"format": {"type": "json_schema", "name": "yongin_query_plan",
                                      "strict": True, "schema": SCHEMA}}})
        response.raise_for_status()
        body = response.json()
    if body.get("status") != "completed":
        raise ValueError("incomplete response")
    parts = [part.get("text", "") for item in body.get("output", [])
             for part in item.get("content", []) if part.get("type") == "output_text"]
    return json.loads("".join(parts))


def plan_question(question, history=None):
    history = history or []
    if (not isinstance(question, str) or not question.strip() or len(question) > 500
            or re.search(r"수원시|성남시|서울시|화성시|안양시", question)):
        raw, interpreter = {"query_id": "unsupported"}, "validation"
    elif os.getenv("OPENAI_API_KEY", "").strip():
        preliminary = _rules(question, history)
        if preliminary.get("query_id") == "unsupported":
            raw, interpreter = preliminary, "rules"
        else:
            try:
                raw, interpreter = _llm(question, history), "llm"
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raw, interpreter = preliminary, "rules"
    else:
        raw, interpreter = _rules(question, history), "rules"
    query = raw.get("query_id")
    district, year, month, keyword = (raw.get(k) for k in ("district", "year", "month", "keyword"))
    if query not in QUERIES or district not in (*DISTRICTS, None):
        return {"query_id": "unsupported", "district": None, "year": None,
                "month": None, "keyword": None}, interpreter
    if year is not None and (type(year) is not int or not 2010 <= year <= 2100):
        query = "unsupported"
    if month is not None and (type(month) is not int or not 1 <= month <= 12):
        query = "unsupported"
    if keyword is not None and (not isinstance(keyword, str) or len(keyword) > 40):
        query = "unsupported"
    if keyword and not re.fullmatch(r"[가-힣A-Za-z0-9 ]+", keyword):
        query = "unsupported"
    return {"query_id": query, "district": district, "year": year,
            "month": month, "keyword": keyword.strip() if keyword else None}, interpreter


def _dataset(query):
    if query.startswith("event_"):
        return "giheung_events"
    if query.startswith("vehicle_"):
        return "vehicle_registrations"
    if query.startswith("facility_"):
        return "public_facilities"
    return None


def _source(cursor, dataset):
    cursor.execute("""select display_name, provider, portal_url, reference_date,
                    collected_at, last_success_at from analytics.dataset_sources
                    where dataset_id=%s""", (dataset,))
    row = cursor.fetchone()
    if row is None:
        return None
    return {"dataset_id": dataset, "dataset_name": row["display_name"],
            "provider": row["provider"], "url": row["portal_url"],
            "reference_date": str(row["reference_date"]) if row["reference_date"] else None,
            "collected_at": row["collected_at"].isoformat() if row["collected_at"] else None,
            "last_success_at": row["last_success_at"].isoformat() if row["last_success_at"] else None}


def _query(cursor, plan):
    query = plan["query_id"]
    district, year, month, keyword = (plan[k] for k in ("district", "year", "month", "keyword"))
    chart = None
    if query.startswith("event_"):
        if month and not year or query == "event_monthly" and not year:
            raise ValueError("행사 월별 조회에는 연도를 지정해 주세요.")
        if district and district != "기흥구":
            raise ValueError("행사 CSV는 기흥구만 포함합니다.")
        limits = ["원본 행사 행 수이며 실제 개최·취소 상태는 확인할 수 없습니다.",
                  "행사 시작일은 2017~2024년입니다."]
        if query == "event_monthly":
            cursor.execute("""with grouped as (select extract(month from start_date)::int as month,
                count(*)::int as count from analytics.giheung_events
                where start_date >= make_date(%s,1,1) and start_date < make_date(%s,1,1)
                group by 1) select m.month, coalesce(g.count,0)::int as count
                from generate_series(1,12) m(month) left join grouped g using (month)
                order by m.month limit 12""", (year, year + 1))
            chart = {"type": "bar", "x": "month", "y": "count"}
        elif query == "event_count":
            cursor.execute("""select count(*)::int count from analytics.giheung_events
                where (%s::int is null or extract(year from start_date)::int=%s)
                  and (%s::int is null or extract(month from start_date)::int=%s)""",
                           (year, year, month, month))
        else:
            cursor.execute("""select title, start_date, end_date from analytics.giheung_events
                where (%s::int is null or extract(year from start_date)::int=%s)
                  and (%s::int is null or extract(month from start_date)::int=%s)
                order by start_date desc nulls last, title limit 12""", (year, year, month, month))
    elif query.startswith("vehicle_"):
        if year or month:
            raise ValueError("자동차 CSV는 한 기준일의 현황입니다. 연도·월별 추이를 제공하지 않습니다.")
        limits = ["등록 현황이며 신규 등록 건수나 시계열 변화가 아닙니다."]
        total = "(government_count+private_count+commercial_count)"
        if query == "vehicle_by_district":
            cursor.execute(f"""select district, sum({total})::bigint count
                from analytics.vehicle_registrations group by district order by count desc limit 12""")
            chart = {"type": "bar", "x": "district", "y": "count"}
        elif query == "vehicle_top_towns":
            cursor.execute(f"""select district,town,sum({total})::bigint count
                from analytics.vehicle_registrations where (%s::text is null or district=%s)
                group by district,town order by count desc,district,town limit 12""", (district, district))
            chart = {"type": "bar", "x": "town", "y": "count"}
        elif query == "vehicle_breakdown":
            cursor.execute("""select sum(government_count)::bigint government_count,
                sum(private_count)::bigint private_count, sum(commercial_count)::bigint commercial_count,
                sum(passenger_count)::bigint passenger_count, sum(van_count)::bigint van_count,
                sum(truck_count)::bigint truck_count, sum(special_count)::bigint special_count
                from analytics.vehicle_registrations where (%s::text is null or district=%s)""", (district, district))
        else:
            cursor.execute(f"""select sum({total})::bigint count from analytics.vehicle_registrations
                where (%s::text is null or district=%s)""", (district, district))
    else:
        if year or month:
            raise ValueError("공공시설 API는 한 기준일의 현황입니다. 기간별 추이를 제공하지 않습니다.")
        limits = ["주소가 용인시인 원본 행입니다. 현재 운영 여부는 별도 확인이 필요합니다."]
        if query == "facility_by_district":
            cursor.execute("""select district,count(*)::int count from analytics.public_facilities
                group by district order by count desc limit 12""")
            chart = {"type": "bar", "x": "district", "y": "count"}
        elif query == "facility_count":
            cursor.execute("""select count(*)::int count from analytics.public_facilities
                where (%s::text is null or district=%s)
                  and (%s::text is null or facility_name ilike '%%'||%s||'%%'
                       or facility_type ilike '%%'||%s||'%%')""",
                           (district, district, keyword, keyword, keyword))
        else:
            cursor.execute("""select facility_name,place_name,facility_type,district,
                       address,homepage_url from analytics.public_facilities
                where (%s::text is null or district=%s)
                  and (%s::text is null or facility_name ilike '%%'||%s||'%%'
                       or facility_type ilike '%%'||%s||'%%'
                       or place_name ilike '%%'||%s||'%%')
                order by facility_name,place_name limit 12""",
                           (district, district, keyword, keyword, keyword, keyword))
    return [dict(row) for row in cursor.fetchall()], chart, limits


def analyze(question, history=None, conversation_id=None):
    request_id = str(uuid.uuid4())
    plan, interpreter = plan_question(question, history)
    query = plan["query_id"]
    dataset = _dataset(query)
    result = {"request_id": request_id, "conversation_id": conversation_id,
              "status": "ok", "intent": query, "interpreter": interpreter,
              "answer": "", "filters": {k: v for k, v in plan.items() if k != "query_id"},
              "result": [], "visualization": None, "sources": [],
              "calculation": None, "limitations": []}
    try:
        if not dataset:
            csv_result = analyze_csv(question, request_id, conversation_id, history or [])
            result.update(csv_result)
            if result["status"] == "unsupported":
                result["answer"] = "적재된 용인시 생활여가·문화·체육 CSV 자료명이나 주제를 구체적으로 질문해 주세요."
            return result
        dsn = os.getenv("SUPABASE_ANALYSIS_DB_URL") or os.getenv("SUPABASE_DB_URL")
        if not dsn:
            raise RuntimeError("database is not configured")
        with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute("set transaction read only")
                    cursor.execute("set local statement_timeout = '5000ms'")
                    cursor.execute("set local role yongin_analysis_reader")
                    source = _source(cursor, dataset)
                    rows, chart, limits = _query(cursor, plan)
        result.update(result=rows, visualization=chart, limitations=limits,
                      sources=[source] if source else [],
                      calculation={"query_id": query, "dataset_id": dataset,
                                   "measure": "등록 자동차 대수" if query.startswith("vehicle_") else "원본 행 수"})
        if query in ("event_count", "vehicle_total", "facility_count"):
            count = rows[0].get("count") or 0
            result["answer"] = f"{plan['district'] or '용인시'} 기준 결과는 {count:,}{'대' if query == 'vehicle_total' else '건'}입니다."
            if count == 0:
                result["status"] = "empty"
        elif query == "event_monthly":
            result["answer"] = f"기흥구 {plan['year']}년 시작 행사 {sum(r['count'] for r in rows):,}건을 월별로 표시했습니다."
        elif not rows:
            result.update(status="empty", answer="해당 조건에 맞는 데이터가 없습니다.")
        elif query == "vehicle_top_towns":
            top = rows[0]
            result["answer"] = (f"{plan['district'] or '용인시'}에서 등록 자동차가 가장 많은 읍면동은 "
                                f"{top['district']} {top['town']}이며 {top['count']:,}대입니다. "
                                "상위 읍면동 순위를 표시했습니다.")
        elif query == "vehicle_by_district":
            result["answer"] = f"구별 자동차 등록 대수를 비교했습니다. 가장 많은 곳은 {rows[0]['district']} {rows[0]['count']:,}대입니다."
        elif query == "facility_by_district":
            result["answer"] = f"구별 공공시설 수를 비교했습니다. 가장 많은 곳은 {rows[0]['district']} {rows[0]['count']:,}건입니다."
        elif query == "facility_search":
            result["answer"] = f"조건에 맞는 공공시설 {len(rows)}건을 표시했습니다. 최대 12건까지 보여줍니다."
        elif query == "event_list":
            result["answer"] = f"조건에 맞는 행사 중 {len(rows)}건을 표시했습니다. 최대 12건까지 보여줍니다."
        elif query == "vehicle_breakdown":
            result["answer"] = "자동차 등록 대수를 용도별·차종별로 나눠 표시했습니다. 두 분류는 같은 차량의 서로 다른 구분입니다."
        else:
            result["answer"] = "분석 결과를 표시했습니다."
        return result
    except ValueError as exc:
        result.update(status="clarification", answer=str(exc))
        return result
    except Exception:
        result.update(status="error", answer="데이터 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.", result=[])
        return result
    finally:
        path = Path(os.getenv("YONGIN_DATA_DIR", str(ROOT / "data"))) / "state" / "analysis_queries.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                                     "request_id": request_id, "conversation_id": conversation_id,
                                     "query_id": result["intent"],
                                     "interpreter": result["interpreter"],
                                     "filters": result["filters"], "status": result["status"],
                                     "result_count": len(result["result"])}, ensure_ascii=False) + "\n")
