"""Bounded, predefined read queries for the currently loaded Yongin data."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .store import ROOT


EXAMPLES = [
    "기흥구 행사 전체 몇 건이야?",
    "기흥구 2024년 행사 몇 건이야?",
    "기흥구 2024년 월별 행사 수를 보여줘",
]
SOURCE_ID = "giheung_events"
LIMITATIONS = [
    "기흥구 이벤트 CSV에 등록된 행의 수이며 실제 개최·취소 여부는 확인할 수 없습니다.",
    "원본의 행사 시작일은 2017~2024년입니다. 기준일이 최근이라고 현재 진행 중인 행사는 아닙니다.",
    "시설·수지구·처인구 자료는 현재 운영 DB에 적재되지 않았습니다.",
]


def classify(question: str) -> tuple[str, dict, str | None]:
    text = question.strip()
    if not text or len(text) > 300:
        return "clarification", {}, "질문을 1~300자로 입력해 주세요."
    if re.search(r"삭제|수정|업데이트|DROP|INSERT|UPDATE|DELETE", text, re.I):
        return "unsupported", {}, "데이터 변경 요청은 지원하지 않습니다."
    if re.search(r"시설|체육관|운동장|도서|프로그램|공원", text):
        return "facility_search", {}, "해당 시설·프로그램 데이터는 아직 적재되지 않았습니다."
    if re.search(r"구별|지역별|수지구|처인구|용인시 전체|수원시|성남시|서울시", text):
        return "regional_comparison", {}, "현재는 기흥구 행사 자료만 있어 지역 비교가 불가능합니다."
    if "기흥구" not in text:
        return "clarification", {}, "현재 조회 가능한 지역은 기흥구입니다. 기흥구를 지정해 주세요."
    if not re.search(r"행사|이벤트", text):
        return "unsupported", {}, "현재 지원하는 질문은 기흥구 행사 건수입니다."
    if re.search(r"올해|이번 달|현재|진행 중|예정", text):
        return "clarification", {}, "원본은 2024년 시작 행사까지 포함합니다. 과거 연도를 지정해 주세요."
    years = re.findall(r"(?<!\d)(20\d{2})년?", text)
    if len(set(years)) > 1:
        return "clarification", {}, "한 번에 한 연도를 지정해 주세요."
    year = int(years[0]) if years else None
    months = re.findall(r"(?<!\d)(\d{1,2})월", text)
    if any(not 1 <= int(value) <= 12 for value in months):
        return "clarification", {}, "월은 1~12 사이로 지정해 주세요."
    if len(set(months)) > 1:
        return "clarification", {}, "한 번에 한 월을 지정해 주세요."
    month = int(months[0]) if months else None
    monthly = bool(re.search(r"월별|달별", text))
    if month and not year:
        return "clarification", {}, "월별 건수에는 연도를 함께 지정해 주세요."
    if monthly and not year:
        return "clarification", {}, "월별 비교할 연도를 지정해 주세요."
    if not re.search(r"몇|건수|수|집계|월별|달별", text):
        return "clarification", {}, "행사 건수를 묻는지와 연도 조건을 알려 주세요."
    return "count_summary", {"year": year, "month": month, "monthly": monthly}, None


def _source(cursor) -> dict | None:
    cursor.execute(
        """select display_name, provider, portal_url,
                  reference_date, collected_at, last_success_at
           from analytics.dataset_sources where dataset_id=%s""",
        (SOURCE_ID,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "dataset_id": SOURCE_ID,
        "dataset_name": row["display_name"],
        "provider": row["provider"],
        "reference_date": str(row["reference_date"]) if row["reference_date"] else None,
        "collected_at": row["collected_at"].isoformat() if row["collected_at"] else None,
        "last_success_at": row["last_success_at"].isoformat() if row["last_success_at"] else None,
        "url": row["portal_url"],
    }


def _log(entry: dict) -> None:
    path = Path(os.getenv("YONGIN_DATA_DIR", str(ROOT / "data"))) / "state" / "analysis_queries.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def analyze(question: str) -> dict:
    request_id = str(uuid.uuid4())
    intent, filters, reason = classify(question)
    response = {
        "request_id": request_id, "status": "ok", "intent": intent,
        "answer": "", "filters": filters, "result": [], "visualization": None,
        "sources": [], "calculation": None, "limitations": [],
    }
    query_id = None
    try:
        if reason:
            response["status"] = "clarification" if intent == "clarification" else "unsupported"
            response["answer"] = reason
            response["limitations"] = LIMITATIONS
            return response

        year, month, monthly = filters["year"], filters["month"], filters["monthly"]
        query_id = "event_monthly" if monthly else "event_count"
        dsn = os.getenv("SUPABASE_ANALYSIS_DB_URL") or os.getenv("SUPABASE_DB_URL")
        if not dsn:
            raise RuntimeError("analysis database connection is not configured")
        with psycopg.connect(dsn, connect_timeout=15, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute("set transaction read only")
                    cursor.execute("set local statement_timeout = '5000ms'")
                    cursor.execute("set local role yongin_analysis_reader")
                    source = _source(cursor)
                    if monthly:
                        cursor.execute(
                            """with grouped as (
                                 select extract(month from start_date)::int as month,
                                        count(*)::int as count
                                 from analytics.giheung_events
                                 where start_date >= make_date(%s,1,1)
                                   and start_date < make_date(%s,1,1)
                                 group by 1
                               )
                               select m.month, coalesce(g.count,0)::int as count
                               from generate_series(1,12) as m(month)
                               left join grouped g using (month)
                               order by m.month limit 12""",
                            (year, year + 1),
                        )
                        rows = cursor.fetchall()
                    else:
                        cursor.execute(
                            """select count(*)::int as count
                               from analytics.giheung_events
                               where (%s::int is null or
                                 (start_date >= make_date(%s,1,1) and
                                  start_date < make_date(%s,1,1)))
                                 and (%s::int is null or extract(month from start_date)::int=%s)
                               limit 1""",
                            (year, year, year + 1 if year else None, month, month),
                        )
                        rows = cursor.fetchall()
        response["sources"] = [source] if source else []
        response["calculation"] = {
            "query_id": query_id, "measure": "고유 관리번호 행 수",
            "date_field": "시작일", "region": "용인시 기흥구",
            "null_handling": "시작일 결측 행은 연도·월 필터에서 제외",
        }
        response["limitations"] = LIMITATIONS
        response["result"] = [dict(row) for row in rows]
        count = sum(row["count"] for row in rows)
        if count == 0:
            response["status"] = "empty"
            response["answer"] = "해당 조건에 맞는 기흥구 행사 행이 없습니다."
        elif monthly:
            response["answer"] = f"기흥구 {year}년 시작 행사 {count}건을 월별로 집계했습니다."
            response["visualization"] = {"type": "bar", "x": "month", "y": "count"}
        else:
            period = f"{year}년 " if year else "전체 "
            if month:
                period = f"{year}년 {month}월 "
            response["answer"] = f"기흥구 {period}시작 행사 행은 {count}건입니다."
        return response
    except Exception:
        response["status"] = "error"
        response["answer"] = "데이터베이스 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."
        response["result"] = []
        return response
    finally:
        _log({
            "at": datetime.now(timezone.utc).isoformat(), "request_id": request_id,
            "intent": intent, "query_id": query_id, "filters": filters,
            "status": response["status"], "result_count": len(response["result"]),
        })
