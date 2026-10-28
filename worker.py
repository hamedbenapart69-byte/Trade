"""Opt-in one-shot worker for the durable outbox.

No loop and no external delivery unless explicitly enabled. An uncertain delivery is
left leased so expiry moves it to 'unknown'; it is never blindly retried.
"""
from __future__ import annotations
import os
import sys
from urllib.parse import urlparse
import httpx
from app.integrations.n8n import deliver_approved_payload, IntegrationDisabled, IntegrationConfigurationError, IntegrationDeliveryError

class WorkerConfigurationError(RuntimeError): pass

def run_once(*,client:httpx.Client|None=None,deliverer=deliver_approved_payload)->str:
    if os.getenv("ENABLE_WORKER_EXECUTION","false").strip().lower()!="true":
        raise WorkerConfigurationError("worker execution is disabled; set ENABLE_WORKER_EXECUTION=true explicitly")
    base=os.getenv("CONTROL_API_URL","http://127.0.0.1:8000").rstrip("/")
    parsed=urlparse(base)
    if parsed.scheme not in {"https","http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise WorkerConfigurationError("CONTROL_API_URL must be an absolute HTTP(S) base URL without embedded credentials/query/fragment")
    if parsed.scheme=="http" and parsed.hostname not in {"127.0.0.1","localhost","::1"}:
        raise WorkerConfigurationError("CONTROL_API_URL must use HTTPS outside loopback")
    token=os.getenv("WORKER_API_TOKEN","")
    if len(token)<24: raise WorkerConfigurationError("WORKER_API_TOKEN must be at least 24 characters")
    allowed={x.strip() for x in os.getenv("WORKER_ALLOWED_WORKFLOWS","").split(",") if x.strip()}
    if not allowed: raise WorkerConfigurationError("WORKER_ALLOWED_WORKFLOWS must explicitly list permitted workflows")
    own=client is None
    http=client or httpx.Client(timeout=10,follow_redirects=False)
    headers={"X-API-Key":token}
    try:
        response=http.post(f"{base}/internal/outbox/lease",headers=headers,params={"lease_seconds":60})
        response.raise_for_status()
        item=response.json().get("item")
        if not item: return "idle"
        item_id=item["id"]
        if item.get("workflow") not in allowed:
            finish=http.post(f"{base}/internal/outbox/{item_id}/finish",headers=headers,json={
                "lease_token":item["lease_token"],"succeeded":False,
                "result":{"error":"workflow_not_allowlisted"}})
            finish.raise_for_status()
            return "rejected_workflow"
        # Any uncertain delivery exception deliberately leaves the lease unfinished.
        # Once expired, the control plane marks it unknown for operator reconciliation.
        result=deliverer(run_id=item["run_id"],workflow=item["workflow"],payload=item.get("input",{}),idempotency_key=item["run_id"])
        finish=http.post(f"{base}/internal/outbox/{item_id}/finish",headers=headers,json={
            "lease_token":item["lease_token"],"succeeded":True,
            "result":{"provider":"n8n","http_status":result.status_code,"response":result.response_text[:1000]}})
        finish.raise_for_status()
        return "completed"
    finally:
        if own: http.close()

if __name__=="__main__":
    try:
        print(run_once())
    except (WorkerConfigurationError,IntegrationDisabled,IntegrationConfigurationError,IntegrationDeliveryError,httpx.HTTPError) as exc:
        print(f"worker stopped safely: {exc}",file=sys.stderr)
        raise SystemExit(2)
