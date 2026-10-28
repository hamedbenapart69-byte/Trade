"""Fail-closed n8n webhook adapter; not wired to approval endpoints."""
from __future__ import annotations
import os
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx

class IntegrationDisabled(RuntimeError): pass
class IntegrationConfigurationError(RuntimeError): pass
class IntegrationDeliveryError(RuntimeError): pass

@dataclass(frozen=True)
class N8nResult:
    status_code:int
    response_text:str

def _validated_webhook_url(raw_url:str)->str:
    parsed=urlparse(raw_url)
    if parsed.scheme not in {"https","http"} or not parsed.hostname:
        raise IntegrationConfigurationError("N8N_WEBHOOK_URL must be an absolute HTTP(S) URL")
    if parsed.scheme=="http" and parsed.hostname not in {"127.0.0.1","localhost","::1"}:
        raise IntegrationConfigurationError("n8n webhook must use HTTPS outside loopback development")
    if parsed.username or parsed.password: raise IntegrationConfigurationError("credentials must not be embedded in webhook URL")
    return raw_url

def deliver_approved_payload(*,run_id:str,workflow:str,payload:dict,idempotency_key:str,client:httpx.Client|None=None)->N8nResult:
    if os.getenv("ENABLE_N8N_EXECUTION","false").strip().lower()!="true":
        raise IntegrationDisabled("n8n execution is disabled; set ENABLE_N8N_EXECUTION=true explicitly")
    raw_url=os.getenv("N8N_WEBHOOK_URL","").strip()
    if not raw_url: raise IntegrationConfigurationError("N8N_WEBHOOK_URL is required when n8n execution is enabled")
    url=_validated_webhook_url(raw_url)
    timeout_seconds=float(os.getenv("N8N_TIMEOUT_SECONDS","8"))
    if not 1<=timeout_seconds<=30: raise IntegrationConfigurationError("N8N_TIMEOUT_SECONDS must be between 1 and 30")
    secret=os.getenv("N8N_WEBHOOK_TOKEN","").strip()
    headers={"Content-Type":"application/json","Idempotency-Key":idempotency_key}
    if secret: headers["X-Webhook-Token"]=secret
    body={"run_id":run_id,"workflow":workflow,"input":payload}
    own_client=client is None
    http=client or httpx.Client(timeout=timeout_seconds,follow_redirects=False)
    try:
        response=http.post(url,json=body,headers=headers,timeout=timeout_seconds)
        if not 200<=response.status_code<300: raise IntegrationDeliveryError(f"n8n webhook returned HTTP {response.status_code}")
        return N8nResult(response.status_code,response.text[:2000])
    except httpx.HTTPError as exc:
        raise IntegrationDeliveryError(f"n8n webhook transport failed: {type(exc).__name__}") from exc
    finally:
        if own_client: http.close()
