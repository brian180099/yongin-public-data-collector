"""HTTP boundary used by n8n; collection logic remains in Python."""

from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .pipeline import list_due_datasets, run_collection
from .store import ROOT


load_dotenv(ROOT / ".env")
app = FastAPI(title="Yongin public-data collector", version="1.0.0")


class CollectionRequest(BaseModel):
    trigger_type: Literal["manual", "schedule", "retry"] = "manual"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "yongin-public-data-collector"}


@app.get("/v1/datasets/due")
def due_datasets(force: bool = Query(False),
                 trigger_type: Literal["manual", "schedule", "retry"] = "schedule") -> dict:
    datasets = list_due_datasets(force=force)
    return {"count": len(datasets), "trigger_type": trigger_type,
            "datasets": datasets}


@app.post("/v1/collect/{dataset_id}")
def collect_dataset(dataset_id: str, request: CollectionRequest) -> dict:
    try:
        return run_collection(dataset_id, request.trigger_type)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown dataset") from exc
