"""Atomic JSON/CSV output for the dashboard and pipeline history."""
import csv, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path

FIELDS=["generated_at_utc","symbol","status","side","tier","provider","engine","reason","confidence","ev_net","idempotency_key"]


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def build_health(payload):
    """ساخت وضعیت سلامت مستقل و قابل ممیزی برای داشبورد."""
    quality = payload.get("quality") or {}
    input_hash = payload.get("input_hash")
    hash_valid = (
        isinstance(input_hash, str)
        and len(input_hash) == 64
        and all(char in "0123456789abcdef" for char in input_hash.lower())
    )
    return {
        "schema_version": "1.0",
        "generated_at_utc": payload.get("generated_at_utc"),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_status": payload.get("pipeline_status", "DEGRADED"),
        "provider": payload.get("provider", "unknown"),
        "engine": payload.get("engine", "unknown"),
        "input_hash": input_hash if hash_valid else None,
        "input_hash_algorithm": "sha256" if hash_valid else None,
        "input_hash_status": "OK" if hash_valid else "UNAVAILABLE",
        "symbols_requested": quality.get("symbols_requested", 0),
        "symbols_processed": quality.get("symbols_processed", 0),
        "symbols_unscanned": quality.get("symbols_unscanned", 0),
        "coverage_pct": quality.get("coverage_pct", 0.0),
        "coverage_status": quality.get("coverage_status", "UNAVAILABLE"),
        "data_errors": payload.get("data_errors") or {},
        "manual_trade_only": True,
    }


def publish(payload):
    repo_root=Path(__file__).resolve().parents[2]
    data_root=repo_root/"signal_autopilot"/"data"
    web_data=repo_root/"web"/"futures"/"data"
    text=json.dumps(payload,ensure_ascii=False,indent=2)+"\n"
    health=build_health(payload)
    health_text=json.dumps(health,ensure_ascii=False,indent=2)+"\n"
    history=data_root/"history.csv"
    history.parent.mkdir(parents=True,exist_ok=True)
    old=history.read_text(encoding="utf-8") if history.exists() else ""
    seen=set()
    if old:
        import io
        seen={r.get("idempotency_key") for r in csv.DictReader(io.StringIO(old))}
    import io
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS)
    if not old:
        writer.writeheader()
    added=0
    for s in payload.get("signals",[]):
        key=f'{payload.get("generated_at_utc")}|{s.get("symbol")}|{payload.get("engine")}'
        if key in seen:
            continue
        writer.writerow({
            "generated_at_utc":payload.get("generated_at_utc"),"symbol":s.get("symbol"),
            "status":s.get("status"),"side":s.get("side"),"tier":s.get("tier"),
            "provider":payload.get("provider"),"engine":payload.get("engine"),
            "reason":s.get("reason"),"confidence":s.get("confidence"),
            "ev_net":s.get("ev_net"),"idempotency_key":key
        })
        added+=1
    if added:
        atomic_text(history,old+buf.getvalue())
    atomic_text(data_root/"signals.json",text)
    atomic_text(data_root/"health.json",health_text)
    atomic_text(web_data/"signals.json",text)
    atomic_text(web_data/"health.json",health_text)
    atomic_text(web_data/"history.csv",history.read_text(encoding="utf-8") if history.exists() else ",".join(FIELDS)+"\n")
    return {"signals_added_to_history":added,"signals_total":len(payload.get("signals",[])),
            "health_status":health["input_hash_status"]}
