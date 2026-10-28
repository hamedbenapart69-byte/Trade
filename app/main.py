"""HTTP API for the approval-gated execution ledger and durable outbox."""
from __future__ import annotations
import hmac, json, logging, os, re, time, uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from app import store
from app.workflow_schemas import validate_workflow_input

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
    path=request.url.path
    if path in {"/health","/"}: return
    # Worker routes use a separate credential. Reconciliation remains owner/operator-only.
    is_worker_route = path == "/internal/outbox/lease" or (path.startswith("/internal/outbox/") and path.endswith("/finish"))
    env_name = "WORKER_API_TOKEN" if is_worker_route else "CONTROL_API_TOKEN"
    expected = os.getenv(env_name, "")
    if len(expected) < 24: raise HTTPException(status_code=503, detail=f"{env_name.lower()}_not_configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid_or_missing_api_key")

app = FastAPI(title="AI Orchestration Control Plane", version="0.3.0", dependencies=[Depends(require_api_key)])
access_log = logging.getLogger("control.access")

@app.middleware("http")
async def request_observability(request: Request, call_next):
    # Never log query strings, headers, bodies, credentials, or downstream response content.
    supplied=request.headers.get("X-Request-ID","")
    request_id=supplied if re.fullmatch(r"[A-Za-z0-9._:-]{8,80}",supplied) else str(uuid.uuid4())
    started=time.perf_counter()
    try:
        response=await call_next(request)
        response.headers["X-Request-ID"]=request_id
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"]="no-store"
        access_log.info("http_request",extra={"request_id":request_id,"method":request.method,
            "path":request.url.path,"status_code":response.status_code,
            "duration_ms":round((time.perf_counter()-started)*1000,2)})
        return response
    except Exception as exc:
        access_log.error("http_request_failed",extra={"request_id":request_id,"method":request.method,
            "path":request.url.path,"error_type":type(exc).__name__,
            "duration_ms":round((time.perf_counter()-started)*1000,2)})
        raise

@app.on_event("startup")
def startup() -> None: store.init_db()

@app.get("/",response_class=HTMLResponse,include_in_schema=False)
def console() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")

@app.get("/health")
def health() -> dict[str,str]: return {"status":"ok","service":"control-plane","version":app.version}

@app.post("/runs",status_code=201)
def create_run(body:RunCreate,idempotency_key:str|None=Header(default=None,alias="Idempotency-Key"))->dict[str,Any]:
    if not idempotency_key or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}",idempotency_key):
        raise HTTPException(status_code=400,detail="valid_idempotency_key_required")
    if len(json.dumps(body.input,ensure_ascii=False,separators=(",",":")).encode("utf-8")) > 32768:
        raise HTTPException(status_code=413,detail="run_input_too_large_max_32768_bytes")
    try:
        return store.insert_run(run_id=str(uuid.uuid4()),idempotency_key=idempotency_key,workflow=body.workflow,payload=body.input,created_at=now_iso())
    except ValueError as exc:
        if str(exc)=="idempotency_key_conflict": raise HTTPException(status_code=409,detail="idempotency_key_reused_with_different_request") from exc
        raise

@app.get("/summary")
def operational_summary()->dict[str,Any]:
    return store.get_operational_summary()

@app.get("/outbox")
def list_outbox(limit:int=50,offset:int=0,status:str|None=None)->dict[str,Any]:
    if limit<1 or limit>100 or offset<0: raise HTTPException(status_code=400,detail="invalid_pagination")
    allowed={"queued","leased","unknown","completed","failed"}
    if status is not None and status not in allowed: raise HTTPException(status_code=400,detail="invalid_status_filter")
    return store.get_outbox(limit=limit,offset=offset,status=status)

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
    run=store.get_run(run_id)
    if run is None: raise HTTPException(status_code=404,detail="run_not_found")
    if run["status"]!="approved": raise HTTPException(status_code=409,detail="run_must_be_approved_before_queueing")
    schema_error=validate_workflow_input(run["workflow"],run["input"])
    if schema_error: raise HTTPException(status_code=422,detail=schema_error)
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
