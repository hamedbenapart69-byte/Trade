"""Persistent open-signal state store (JSON, atomic replace)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_STATE_BYTES = 10_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignalTracker:
    def __init__(self, state_path: str | Path):
        self.path = Path(state_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "updated_at_utc": _now(), "open_signals": {}, "closed_signals": {}}
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("signal_state_not_regular_file")
        if self.path.stat().st_size > MAX_STATE_BYTES:
            raise ValueError("signal_state_too_large")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"signal_state_unreadable:{self.path}") from exc
        if (
            not isinstance(data, dict)
            or isinstance(data.get("schema_version"), bool)
            or data.get("schema_version", 1) != 1
            or not isinstance(data.get("open_signals"), dict)
        ):
            raise ValueError("signal_state_schema_invalid")
        data.setdefault("closed_signals", {})
        if not isinstance(data["closed_signals"], dict):
            raise ValueError("signal_state_closed_schema_invalid")
        open_rows, closed_rows = data["open_signals"], data["closed_signals"]
        if set(open_rows) & set(closed_rows):
            raise ValueError("signal_state_open_closed_id_overlap")
        for collection in (open_rows, closed_rows):
            for signal_id, record in collection.items():
                if (
                    not isinstance(signal_id, str) or not signal_id.strip()
                    or not isinstance(record, dict)
                    or record.get("signal_id") != signal_id
                ):
                    raise ValueError("signal_state_record_invalid")
        return data

    def upsert(self, signal: dict[str, Any]) -> dict[str, Any]:
        signal_id = str(signal.get("signal_id", "")).strip()
        if not signal_id:
            raise ValueError("signal_id_required")
        if signal_id in self.state.get("closed_signals", {}):
            raise ValueError("signal_id_already_closed")
        previous = self.state["open_signals"].get(signal_id, {})
        observed_at = _now()
        first_seen = (
            previous.get("first_seen_utc")
            or previous.get("created_at_utc")
            or signal.get("created_at_utc")
            or observed_at
        )
        # یک شناسهٔ سیگنال نمایندهٔ یک setup مشخص است؛ تکرار اسکن نباید
        # زمان ایجاد یا سطوح مرجع آن را جابه‌جا کند و نتیجهٔ Shadow را بازنویسی کند.
        # مقادیر موجود در snapshot اولیه تغییرناپذیرند؛ فقط فیلدهای غایبِ
        # رکوردهای قدیمی می‌توانند تکمیل شوند و هیچ مقدار قبلی بازنویسی نمی‌شود.
        # اگر snapshot زمان ایجاد دارد، کامل و immutable است؛ حتی فیلدهای
        # سیاستیِ تازه نباید بعداً به آن الصاق شوند. فقط رکوردهای قدیمیِ
        # بدون created_at_utc اجازهٔ تکمیل یک‌بارهٔ فیلدهای مفقود را دارند.
        record = (
            dict(previous)
            if previous.get("created_at_utc")
            else {**signal, **previous}
        )
        record.update({
            "tracker_status": "OPEN",
            "created_at_utc": previous.get("created_at_utc") or first_seen,
            "first_seen_utc": first_seen,
            "last_seen_utc": observed_at,
            "updates": int(previous.get("updates", 0)) + 1,
        })
        self.state["open_signals"][signal_id] = record
        self.save()
        return record

    def close(self, signal_id: str, reason: str = "CLOSED") -> bool:
        record = self.state["open_signals"].pop(signal_id, None)
        if not record:
            return False
        record["tracker_status"] = "CLOSED"
        record["closed_at_utc"] = _now()
        record["close_reason"] = reason
        self.state.setdefault("closed_signals", {})[signal_id] = record
        self.save()
        return True

    def save(self) -> None:
        self.state["updated_at_utc"] = _now()
        fd, tmp_name = tempfile.mkstemp(prefix=".open_signals.", suffix=".tmp",
                                        dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.state, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def snapshot(self) -> dict[str, Any]:
        return self.state

# Delivery contract marker: open signal state is persisted as an atomic JSON snapshot for the signal-state branch.
