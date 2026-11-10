"""Atomic JSON/CSV output for the dashboard and pipeline history."""
import csv, json, os, tempfile
from pathlib import Path

FIELDS=["generated_at_utc","symbol","status","side","tier","provider","engine","reason","confidence","ev_net","ev_status","idempotency_key"]

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

def migrate_history_csv(old: str) -> str:
    """مهاجرت امن CSV قدیمی به ستون‌های جاری بدون حذف سوابق یا کلیدهای تکرارزدایی."""
    if not old:
        return ""
    import io
    reader = csv.DictReader(io.StringIO(old))
    if reader.fieldnames == FIELDS:
        return old
    rows = list(reader)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in FIELDS})
    return output.getvalue()


def publish(payload):
    repo_root=Path(__file__).resolve().parents[2]
    data_root=repo_root/"signal_autopilot"/"data"
    web_data=repo_root/"web"/"futures"/"data"
    text=json.dumps(payload,ensure_ascii=False,indent=2)+"\n"
    history=data_root/"history.csv"
    history.parent.mkdir(parents=True,exist_ok=True)
    old_raw=history.read_text(encoding="utf-8") if history.exists() else ""
    old=migrate_history_csv(old_raw)
    history_migrated = old != old_raw
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
            "ev_net":s.get("ev_net"),"ev_status":s.get("ev_status"),"idempotency_key":key
        })
        added+=1
    if added or history_migrated:
        atomic_text(history,old+buf.getvalue())
    atomic_text(data_root/"signals.json",text)
    atomic_text(web_data/"signals.json",text)
    atomic_text(web_data/"history.csv",history.read_text(encoding="utf-8") if history.exists() else ",".join(FIELDS)+"\n")
    return {"signals_added_to_history":added,"signals_total":len(payload.get("signals",[]))}
