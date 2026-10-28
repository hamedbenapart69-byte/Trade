"""HTTP API for the approval-gated execution ledger and durable outbox."""
from __future__ import annotations
import hmac, json, os, re, uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
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

@app.on_event("startup")
def startup() -> None: store.init_db()

@app.get("/",response_class=HTMLResponse,include_in_schema=False)
def console() -> str:
    return "<!doctype html>\n<html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"color-scheme\" content=\"dark light\"><title>مرکز کنترل اتوماسیون</title>\n<style>\n:root{font-family:Tahoma,Arial,sans-serif;color-scheme:dark;background:#10141d;color:#edf2fa}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top right,#1b2b40,#10141d 55%);min-height:100vh}main{max-width:1100px;margin:auto;padding:22px 16px 48px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}.brand{font-size:1.25rem;font-weight:800}.sub{color:#aab8ca;font-size:.88rem;margin-top:7px}.panel{background:#171e2a;border:1px solid #2b3748;border-radius:16px;padding:16px;margin-top:16px;box-shadow:0 12px 32px #0002}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.row>*{flex:1;min-width:150px}input,textarea,select,button{font:inherit;border-radius:10px;border:1px solid #39485d;padding:11px;background:#101722;color:#f5f7fb;width:100%}textarea{min-height:80px;direction:ltr;text-align:left}button{cursor:pointer;background:#d8e7ff;color:#142033;border:0;font-weight:700}button.secondary{background:#29374b;color:#edf2fa}button.danger{background:#4b2630;color:#ffdbe0}.actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.actions button{width:auto;font-size:.84rem;padding:8px 10px}.muted{color:#aab8ca;font-size:.85rem}.status{display:inline-block;border:1px solid #39485d;padding:4px 8px;border-radius:99px;font-size:.78rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px;margin-top:12px}.item{border:1px solid #2b3748;border-radius:12px;padding:13px;background:#111823;min-width:0}.item h3{margin:0 0 9px;font-size:1rem;overflow-wrap:anywhere}.item pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:130px;overflow:auto;color:#c5d2e4;font-size:.78rem;direction:ltr;text-align:left}.section-title{font-weight:800;font-size:1.05rem}.msg{padding:10px;border-radius:10px;background:#253448;color:#dceaff;margin-top:10px;display:none}.warn{color:#ffdba6}.hidden{display:none}@media(min-width:700px){main{padding-top:32px}.panel{padding:20px}}\n</style></head><body><main>\n<header class=\"top\"><div><div class=\"brand\">مرکز کنترل هوشمند</div><div class=\"sub\">مدیریت اجراها، تأیید انسانی و صف عملیات</div></div><span class=\"status\">اجرای بیرونی: فقط با فعال‌سازی صریح</span></header>\n<section class=\"panel\"><div class=\"section-title\">اتصال امن</div><p class=\"muted\">کلید کنترل فقط در حافظه همین صفحه استفاده می‌شود و در مرورگر ذخیره نمی‌شود. برای استفاده محلی، سرویس را روی 127.0.0.1 نگه دارید.</p><div class=\"row\"><input id=\"token\" type=\"password\" autocomplete=\"off\" placeholder=\"CONTROL_API_TOKEN\"><button id=\"connect\">اتصال و بارگذاری</button></div><div id=\"msg\" class=\"msg\"></div></section>\n<section class=\"panel\"><div class=\"section-title\">ثبت اجرای جدید</div><div class=\"row\" style=\"margin-top:12px\"><input id=\"workflow\" placeholder=\"نام ورک‌فلو، مثال: research.scan\"><input id=\"idem\" placeholder=\"کلید یکتای درخواست\"></div><textarea id=\"payload\" placeholder='{\"symbol\":\"BTCUSDT\",\"timeframe\":\"4h\"}' style=\"margin-top:10px\"></textarea><button id=\"create\" style=\"margin-top:10px\">ثبت برای بررسی انسانی</button></section>\n<section class=\"panel\"><div class=\"top\"><div class=\"section-title\">اجراها</div><button class=\"secondary\" id=\"refresh\" style=\"max-width:150px\">به‌روزرسانی</button></div><div id=\"runs\" class=\"grid\"></div></section>\n<section class=\"panel\"><div class=\"top\"><div class=\"section-title\">صف اجرای عملیات</div><button class=\"secondary\" id=\"refreshOutbox\" style=\"max-width:150px\">به‌روزرسانی صف</button></div><p class=\"muted\">وضعیت unknown یعنی نتیجه مقصد باید دستی بررسی شود؛ قبل از بررسی، retry نکنید.</p><div id=\"outbox\" class=\"grid\"></div></section>\n<script>\nlet apiToken=\"\";\nconst $=id=>document.getElementById(id);\nfunction message(s){$(\"msg\").textContent=s;$(\"msg\").style.display=\"block\"}\nasync function api(path,opts={}){const res=await fetch(path,{...opts,headers:{\"Content-Type\":\"application/json\",\"X-API-Key\":apiToken,...(opts.headers||{})}});const body=await res.json().catch(()=>({detail:res.statusText}));if(!res.ok)throw new Error(body.detail||(\"HTTP \"+res.status));return body}\nfunction esc(s){return String(s??\"\").replace(/[&<>\"']/g,c=>({\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#39;\"}[c]))}\nasync function loadRuns(){const data=await api(\"/runs?limit=50\");$(\"runs\").innerHTML=data.items.map(r=>'<article class=\"item\"><h3>'+esc(r.workflow)+'</h3><div class=\"muted\">شناسه: '+esc(r.id)+'</div><p><span class=\"status\">'+esc(r.status)+'</span></p><p class="muted">'+(r.outbox_status?'وضعیت صف: '+esc(r.outbox_status):'هنوز وارد صف نشده')+'</p><pre>'+esc(JSON.stringify(r.input,null,2))+'</pre><div class=\"actions\">'+(r.status===\"pending_approval\"?'<button data-act=\"approve\" data-id=\"'+esc(r.id)+'\">تأیید</button><button class=\"danger\" data-act=\"reject\" data-id=\"'+esc(r.id)+'\">رد</button>':'')+(r.status===\"approved\"?'<button data-act=\"queue\" data-id=\"'+esc(r.id)+'\">افزودن به صف</button>':'')+'<button class=\"secondary\" data-act=\"events\" data-id=\"'+esc(r.id)+'\">رویدادها</button></div></article>').join(\"\")||'<p class=\"muted\">اجرایی ثبت نشده است.</p>'}\nasync function loadOutbox(){const data=await api(\"/outbox?limit=50\");$(\"outbox\").innerHTML=data.items.map(i=>'<article class=\"item\"><h3>آیتم صف</h3><div class=\"muted\">شناسه: '+esc(i.id)+'</div><p><span class=\"status\">'+esc(i.status)+'</span> <span class=\"muted\">تلاش: '+esc(i.attempts)+'</span></p><div class=\"muted\">Run: '+esc(i.run_id)+'</div><pre>'+esc(JSON.stringify(i.result,null,2))+'</pre>'+(i.status===\"unknown\"?'<div class=\"warn\">نتیجه اجرا نامشخص است؛ ابتدا مقصد را بررسی کنید.</div><div class=\"actions\"><button data-act=\"reconcile-retry\" data-id=\"'+esc(i.id)+'\">تأیید بررسی و تلاش مجدد</button><button class=\"danger\" data-act=\"reconcile-fail\" data-id=\"'+esc(i.id)+'\">علامت‌گذاری ناموفق</button></div>':'')+'</article>').join(\"\")||'<p class=\"muted\">صف خالی است.</p>'}\n$(\"connect\").onclick=async()=>{apiToken=$(\"token\").value.trim();try{await loadRuns();await loadOutbox();message(\"اتصال برقرار شد.\");}catch(e){message(\"خطا: \"+e.message)}};\n$(\"refresh\").onclick=async()=>{try{await loadRuns();message(\"اجراها به‌روز شدند.\")}catch(e){message(e.message)}};\n$(\"refreshOutbox\").onclick=async()=>{try{await loadOutbox();message(\"صف به‌روز شد.\")}catch(e){message(e.message)}};\n$(\"create\").onclick=async()=>{try{const workflow=$(\"workflow\").value.trim(),key=$(\"idem\").value.trim(),payload=JSON.parse($(\"payload\").value||\"{}\");if(!workflow||key.length<8)throw new Error(\"نام ورک‌فلو و کلید یکتای حداقل ۸ نویسه لازم است.\");await api(\"/runs\",{method:\"POST\",headers:{\"Idempotency-Key\":key},body:JSON.stringify({workflow,input:payload})});message(\"ثبت شد؛ تا تأیید انسانی اجرا نمی‌شود.\");await loadRuns()}catch(e){message(\"خطا: \"+e.message)}};\ndocument.addEventListener(\"click\",async e=>{const b=e.target.closest(\"button[data-act]\");if(!b)return;const id=b.dataset.id,act=b.dataset.act;try{if(act===\"approve\"||act===\"reject\"){await api(\"/runs/\"+id+\"/\"+act,{method:\"POST\",body:JSON.stringify({decided_by:\"operator-console\"})})}else if(act===\"queue\"){await api(\"/runs/\"+id+\"/queue\",{method:\"POST\"})}else if(act===\"events\"){const d=await api(\"/runs/\"+id+\"/events\");alert(JSON.stringify(d.items,null,2));return}else if(act.startsWith(\"reconcile-\")){const action=act.endsWith(\"retry\")?\"retry\":\"fail\";const note=prompt(\"نتیجه بررسی مقصد را توضیح بده؛ retry فقط پس از بررسی واقعی:\");if(!note||note.trim().length<5)return;await api(\"/internal/outbox/\"+id+\"/reconcile\",{method:\"POST\",body:JSON.stringify({action,actor:\"operator-console\",note:note.trim()})});await loadOutbox()}await loadRuns();message(\"عملیات ثبت شد.\")}catch(err){message(\"خطا: \"+err.message)}});\n</script></main></body></html>"

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
