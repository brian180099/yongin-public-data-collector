"""Public-facing analysis app; the collection process never serves queries."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .chat_analysis import EXAMPLES, analyze
from .store import ROOT


load_dotenv(ROOT / ".env")
app = FastAPI(title="Yongin public-data analysis", version="1.0.0")


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = Field(default=None, max_length=80)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "yongin-public-data-analysis"}


@app.get("/")
def question_page() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/v1/analysis/examples")
def analysis_examples() -> dict:
    return {"questions": EXAMPLES, "llm_enabled": bool(os.getenv("OPENAI_API_KEY", "").strip())}


@app.post("/v1/analyze")
def analyze_question(request: QuestionRequest) -> dict:
    history = [m for m in request.history if m.get("role") in ("user", "assistant")
               and isinstance(m.get("content"), str) and len(m["content"]) <= 500]
    return analyze(request.question, history, request.conversation_id)


@app.post("/ask")
def ask_via_n8n(request: QuestionRequest) -> dict:
    endpoint = os.getenv("YONGIN_ANALYSIS_WEBHOOK_URL") or (
        "http://n8n:5678/webhook/yongin-analysis-v1"
    )
    try:
        with httpx.Client(timeout=35) as client:
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
