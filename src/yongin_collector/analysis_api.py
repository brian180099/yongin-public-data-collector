"""Public-facing analysis app; the collection process never serves queries."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .analysis import EXAMPLES, analyze
from .store import ROOT


load_dotenv(ROOT / ".env")
app = FastAPI(title="Yongin public-data analysis", version="1.0.0")


class QuestionRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "yongin-public-data-analysis"}


@app.get("/")
def question_page() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/v1/analysis/examples")
def analysis_examples() -> dict:
    return {"questions": EXAMPLES, "dataset_id": "giheung_events"}


@app.post("/v1/analyze")
def analyze_question(request: QuestionRequest) -> dict:
    return analyze(request.question)


@app.post("/ask")
def ask_via_n8n(request: QuestionRequest) -> dict:
    endpoint = os.getenv("YONGIN_ANALYSIS_WEBHOOK_URL") or (
        "http://n8n:5678/webhook/yongin-analysis-v1"
    )
    try:
        with httpx.Client(timeout=25) as client:
            response = client.post(endpoint, json=request.model_dump())
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "request_id" not in payload:
                raise ValueError("unexpected workflow response")
            return payload
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="분석 워크플로에 연결할 수 없습니다. 활성 상태를 확인해 주세요.",
        ) from exc
