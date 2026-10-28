"""HTTP API for the approval-gated execution ledger and durable outbox."""
from __future__ import annotations
import hmac, os, re, uuid
from datetime import datetime, timezone, timedelta
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

class OutboxFinish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_token: str = Field(min_length=20, max_length=100)
    succeeded: bool
    result: dict[str, Any] = Field(default_factory=dict)

class OutboxReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(retry|fail)$")
    actor: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=5, max_length=1000)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    if request.url.path == "/health": return
    expected = os.getenv("CONTROL_API_TOKEN", "")
    if len(expected) < 24: raise HTTPException(status_code=503, detail="operational_api_not_configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid_or_missing_api_key")

app = FastAPI(title="AI Orchestration Control Plane", version="0.3.0", dependencies=[Depends(require_api_key)])

@app.on_event("startup")
def startup() -> None: store.init_db()

@app.get("/health")
def health() -> dict[str,str]: return {"status":"ok","service":"control-plane","version":app.version}

@app.post("/runs",status_code=201)
def create_run(body:RunCreate,idempotency_key:str|None=Header(default=None,alias="Idempotency-Key"))->dict[str,Any]:
    if not idempotency_key or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}",idempotency_key):
        raise HTTPException(status_code=400,detail="valid_idempotency_key_required")
    try:
        return store.insert_run(run_id=str(uuid.uuid4()),idempotency_key=idempotency_key,workflow=body.workflow,payload=body.input,created_at=now_iso())
    except ValueError as exc:
        if str(exc)=="idempotency_key_conflict": raise HTTPException(status_code=409,detail="idempotency_key_reused_with_different_request") from exc
        raise

@app.get("/runs")
def list_runs(limit:int=50,offset:int=0,status:str|None=None)->dict[str,Any]:
    if limit<1 or limit>100 or offset<0: raise HTTPException(status_code=400,detail="invalid_pagination")
    allowed={"pending_approval","approved","rejected","cancelled"}
    if status is not None and status not in allowed: raise HTTPException(status_code=400,detail="invalid_status_filter")
    return store.get_runs(limit=limit,offset=offset,status=status)

@app.get("/runs/{run_id}/events")
def list_run_events(run_id:str)->dict[str,Any]:
    events=store.get_run_events(run_id)
    if events is None: raise HTTPException(status_code=404,detail="run_not_found")
    return {"items":events}

@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id:str,body:Decision)->dict[str,Any]: return _decide(run_id,"cancelled",body)

@app.post("/runs/{run_id}/queue",status_code=202)
def queue_approved_run(run_id:str)->dict[str,Any]:
    try: result=store.enqueue_approved_run(run_id,created_at=now_iso())
    except ValueError as exc:
        if str(exc)=="run_not_approved": raise HTTPException(status_code=409,detail="run_must_be_approved_before_queueing") from exc
        raise
    if result is None: raise HTTPException(status_code=404,detail="run_not_found")
    return result

@app.post("/internal/outbox/lease")
def lease_outbox(lease_seconds:int=60)->dict[str,Any]:
    if lease_seconds<10 or lease_seconds>300: raise HTTPException(status_code=400,detail="lease_seconds_must_be_between_10_and_300")
    now=datetime.now(timezone.utc)
    item=store.lease_next_outbox(now=now.isoformat(timespec="seconds"),lease_until=(now+timedelta(seconds=lease_seconds)).isoformat(timespec="seconds"))
    return {"item":item}

@app.post("/internal/outbox/{item_id}/finish")
def finish_outbox(item_id:str,body:OutboxFinish)->dict[str,Any]:
    try: result=store.finish_outbox(item_id,lease_token=body.lease_token,succeeded=body.succeeded,finished_at=now_iso(),result=body.result)
    except ValueError as exc:
        if str(exc)=="stale_or_invalid_lease": raise HTTPException(status_code=409,detail="stale_or_invalid_lease") from exc
        raise
    if result is None: raise HTTPException(status_code=404,detail="outbox_item_not_found")
    return result

@app.post("/internal/outbox/{item_id}/reconcile")
def reconcile_outbox(item_id:str,body:OutboxReconcile)->dict[str,Any]:
    try:
        result=store.reconcile_outbox(item_id,action=body.action,actor=body.actor,note=body.note,at=now_iso())
    except ValueError as exc:
        if str(exc)=="outbox_not_unknown": raise HTTPException(status_code=409,detail="outbox_item_not_unknown") from exc
        if str(exc)=="invalid_reconciliation_action": raise HTTPException(status_code=400,detail="invalid_reconciliation_action") from exc
        raise
    if result is None: raise HTTPException(status_code=404,detail="outbox_item_not_found")
    return result

@app.get("/runs/{run_id}")
def get_run(run_id:str)->dict[str,Any]:
    result=store.get_run(run_id)
    if result is None: raise HTTPException(status_code=404,detail="run_not_found")
    return result

@app.post("/runs/{run_id}/approve")
def approve_run(run_id:str,body:Decision)->dict[str,Any]: return _decide(run_id,"approved",body)

@app.post("/runs/{run_id}/reject")
def reject_run(run_id:str,body:Decision)->dict[str,Any]: return _decide(run_id,"rejected",body)

def _decide(run_id:str,decision:str,body:Decision)->dict[str,Any]:
    try: result=store.decide_run(run_id,decision=decision,decided_by=body.decided_by,note=body.note,decided_at=now_iso())
    except ValueError as exc:
        if str(exc)=="run_already_decided": raise HTTPException(status_code=409,detail="run_already_decided") from exc
        raise
    if result is None: raise HTTPException(status_code=404,detail="run_not_found")
    return result
