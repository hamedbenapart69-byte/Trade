"""Atomic JSON/CSV output for the dashboard and pipeline history."""
import csv, json, os, tempfile
from pathlib import Path

FIELDS = [
    "generated_at_utc", "symbol", "status", "side", "tier", "provider", "engine",
    "reason", "confidence", "ev_net", "entry", "stop_loss", "take_profit_json",
    "ema20", "ema50", "atr14", "timeframe", "analysis_type",
    "ticker_timestamp_utc", "ticker_timestamp_source", "entry_price_quality",
    "quality_gates_json", "quality_metrics_json", "input_hash", "signal_id",
    "hypothesis", "falsification", "idempotency_key",
]


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


def _json_cell(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def publish(payload):
    repo_root = Path(__file__).resolve().parents[2]
    data_root = repo_root / "signal_autopilot" / "data"
    web_data = repo_root / "web" / "futures" / "data"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    history = data_root / "history.csv"
    history.parent.mkdir(parents=True, exist_ok=True)
    old = history.read_text(encoding="utf-8") if history.exists() else ""
    import io

    # مهاجرت افزایشی CSV قدیمی؛ ستون‌های قبلی حفظ می‌شوند و ستون‌های جدید خالی می‌مانند.
    if old:
        old_reader = csv.DictReader(io.StringIO(old))
        old_fields = old_reader.fieldnames or []
        old_rows = list(old_reader)
        if old_fields != FIELDS:
            migrated = io.StringIO(newline="")
            migration_writer = csv.DictWriter(migrated, fieldnames=FIELDS)
            migration_writer.writeheader()
            for old_row in old_rows:
                migration_writer.writerow({field: old_row.get(field, "") for field in FIELDS})
            old = migrated.getvalue()

    seen = set()
    if old:
        seen = {r.get("idempotency_key") for r in csv.DictReader(io.StringIO(old))}

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    if not old:
        writer.writeheader()
    added = 0
    for signal in payload.get("signals", []):
        key = f'{payload.get("generated_at_utc")}|{signal.get("symbol")}|{payload.get("engine")}'
        if key in seen:
            continue
        writer.writerow({
            "generated_at_utc": payload.get("generated_at_utc"),
            "symbol": signal.get("symbol"), "status": signal.get("status"),
            "side": signal.get("side"), "tier": signal.get("tier"),
            "provider": signal.get("provider") or payload.get("provider"),
            "engine": payload.get("engine"), "reason": signal.get("reason"),
            "confidence": signal.get("confidence"), "ev_net": signal.get("ev_net"),
            "entry": signal.get("entry"), "stop_loss": signal.get("stop_loss"),
            "take_profit_json": _json_cell(signal.get("take_profit") or []),
            "ema20": signal.get("ema20"), "ema50": signal.get("ema50"),
            "atr14": signal.get("atr14"), "timeframe": signal.get("timeframe"),
            "analysis_type": signal.get("analysis_type"),
            "ticker_timestamp_utc": signal.get("ticker_timestamp_utc"),
            "ticker_timestamp_source": signal.get("ticker_timestamp_source"),
            "entry_price_quality": signal.get("entry_price_quality"),
            "quality_gates_json": _json_cell(signal.get("quality_gates") or {}),
            "quality_metrics_json": _json_cell(signal.get("quality_metrics") or {}),
            "input_hash": signal.get("input_hash"), "signal_id": signal.get("signal_id"),
            "hypothesis": signal.get("hypothesis"), "falsification": signal.get("falsification"),
            "idempotency_key": key,
        })
        added += 1
    if added:
        atomic_text(history, old + buf.getvalue())
    elif old and history.read_text(encoding="utf-8") != old:
        atomic_text(history, old)

    atomic_text(data_root / "signals.json", text)
    atomic_text(web_data / "signals.json", text)
    atomic_text(web_data / "history.csv", history.read_text(encoding="utf-8") if history.exists() else ",".join(FIELDS) + "\n")
    return {"signals_added_to_history": added, "signals_total": len(payload.get("signals", []))}
