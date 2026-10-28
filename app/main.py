"""HTTP API for the initial, approval-gated execution ledger."""
from __future__ import annotations
import hmac, os, re, uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app import store

class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: str = Field(min_length=3, max_length=120, pattern=r"^[a-zA-Z0-9_.:-]+$")
    input: dict[str, Any] = Field(default_factory=dict)

class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decided_by: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    if request.url.path == "/health": return
    expected = os.getenv("CONTROL_API_TOKEN", "")
    if len(expected) < 24: raise HTTPException(status_code=503, detail="operational_api_not_configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid_or_missing_api_key")

app = FastAPI(title="AI Orchestration Control Plane", version="0.1.0", dependencies=[Depends(require_api_key)])

@app.on_event("startup")
def startup() -> None: store.init_db()

@app.get("/health")
def health() -> dict[str, str]:
    return {"status":"ok","service":"control-plane","version":app.version}

@app.post("/runs", status_code=201)
def create_run(body: RunCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
    if not idempotency_key or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", idempotency_key):
        raise HTTPException(status_code=400, detail="valid_idempotency_key_required")
    try:
        return store.insert_run(run_id=str(uuid.uuid4()), idempotency_key=idempotency_key,
                                workflow=body.workflow, payload=body.input, created_at=now_iso())
    except ValueError as exc:
        if str(exc) == "idempotency_key_conflict":
            raise HTTPException(status_code=409, detail="idempotency_key_reused_with_different_request") from exc
        raise

@app.get("/runs")
def list_runs(limit: int = 50, offset: int = 0, status: str | None = None) -> dict[str, Any]:
    if limit < 1 or limit > 100 or offset < 0: raise HTTPException(status_code=400, detail="invalid_pagination")
    allowed = {"pending_approval","approved","rejected","cancelled"}
    if status is not None and status not in allowed: raise HTTPException(status_code=400, detail="invalid_status_filter")
    return store.get_runs(limit=limit, offset=offset, status=status)

@app.get("/runs/{run_id}/events")
def list_run_events(run_id: str) -> dict[str, Any]:
    events = store.get_run_events(run_id)
    if events is None: raise HTTPException(status_code=404, detail="run_not_found")
    return {"items":events}

@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, body: Decision) -> dict[str, Any]:
    return _decide(run_id, "cancelled", body)

@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    result = store.get_run(run_id)
    if result is None: raise HTTPException(status_code=404, detail="run_not_found")
    return result

@app.post("/runs/{run_id}/approve")
def approve_run(run_id: str, body: Decision) -> dict[str, Any]: return _decide(run_id, "approved", body)

@app.post("/runs/{run_id}/reject")
def reject_run(run_id: str, body: Decision) -> dict[str, Any]: return _decide(run_id, "rejected", body)

def _decide(run_id: str, decision: str, body: Decision) -> dict[str, Any]:
    try:
        result = store.decide_run(run_id, decision=decision, decided_by=body.decided_by, note=body.note, decided_at=now_iso())
    except ValueError as exc:
        if str(exc) == "run_already_decided": raise HTTPException(status_code=409, detail="run_already_decided") from exc
        raise
    if result is None: raise HTTPException(status_code=404, detail="run_not_found")
    return result
