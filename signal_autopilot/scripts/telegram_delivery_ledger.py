"""مدیریت دفتر پایدار تحویل اعلان تلگرام با سیاست at-most-once."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_LEDGER_BYTES = 2_000_000
VALID_STATUSES = {"CLAIMED", "SENT", "DELIVERY_UNCONFIRMED"}


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("ledger_clock_must_be_timezone_aware")
    return current.astimezone(timezone.utc)


def _load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("delivery_ledger_not_regular_file")
    if path.stat().st_size > MAX_LEDGER_BYTES:
        raise ValueError("delivery_ledger_too_large")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("delivery_ledger_unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("delivery_ledger_schema_invalid")
    deliveries = payload.get("deliveries")
    if not isinstance(deliveries, dict):
        raise ValueError("delivery_ledger_entries_invalid")
    for run_id, record in deliveries.items():
        if not isinstance(run_id, str) or not isinstance(record, dict):
            raise ValueError("delivery_ledger_entry_invalid")
        if record.get("status") not in VALID_STATUSES:
            raise ValueError("delivery_ledger_status_invalid")
    return payload


def _save(path: Path, payload: dict[str, Any]) -> None:
    temporary_name: str | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=".telegram-delivery-", suffix=".tmp", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def claim_delivery(
    state_path: str | Path,
    run_id: str,
    now: datetime | None = None,
) -> bool:
    """رزرو پایدار شناسهٔ اجرا؛ اجرای تکراری مجاز به ارسال دوباره نیست."""
    key = str(run_id).strip()
    if not key:
        raise ValueError("workflow_run_id_required")
    path = Path(state_path)
    payload = _load(path)
    deliveries = payload["deliveries"]
    if key in deliveries:
        return False
    deliveries[key] = {
        "status": "CLAIMED",
        "claimed_at_utc": _now(now).isoformat(),
    }
    _save(path, payload)
    return True


def finalize_delivery(
    state_path: str | Path,
    run_id: str,
    outcome: str,
    now: datetime | None = None,
) -> str:
    """ثبت نتیجه؛ شکست مبهم شبکه به‌عنوان ارسال تأییدنشده نگه داشته می‌شود."""
    key = str(run_id).strip()
    if not key:
        raise ValueError("workflow_run_id_required")
    path = Path(state_path)
    payload = _load(path)
    record = payload["deliveries"].get(key)
    if not isinstance(record, dict) or record.get("status") != "CLAIMED":
        raise ValueError("delivery_claim_not_found_or_already_finalized")
    status = "SENT" if outcome == "success" else "DELIVERY_UNCONFIRMED"
    record["status"] = status
    record["finalized_at_utc"] = _now(now).isoformat()
    record["workflow_step_outcome"] = str(outcome)
    _save(path, payload)
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("claim", "finalize"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--state", type=Path, required=True)
        sub.add_argument("--run-id", required=True)
        if command == "finalize":
            sub.add_argument("--outcome", required=True)
    args = parser.parse_args()
    if args.command == "claim":
        claimed = claim_delivery(args.state, args.run_id)
        print(f"DELIVERY_CLAIMED={'true' if claimed else 'false'}")
        return 0
    status = finalize_delivery(args.state, args.run_id, args.outcome)
    print(f"DELIVERY_STATUS={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
