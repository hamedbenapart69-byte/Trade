"""Persistent open-signal state store (JSON, atomic replace)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"signal_state_unreadable:{self.path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("open_signals"), dict):
            raise ValueError("signal_state_schema_invalid")
        data.setdefault("schema_version", 1)
        data.setdefault("closed_signals", {})
        return data

    def upsert(self, signal: dict[str, Any]) -> dict[str, Any]:
        signal_id = str(signal.get("signal_id", "")).strip()
        if not signal_id:
            raise ValueError("signal_id_required")
        previous = self.state["open_signals"].get(signal_id, {})
        record = {**previous, **signal,
                  "tracker_status": "OPEN",
                  "first_seen_utc": previous.get("first_seen_utc", _now()),
                  "last_seen_utc": _now(),
                  "updates": int(previous.get("updates", 0)) + 1}
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
