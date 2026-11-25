#!/usr/bin/env python3
"""Fail CI if any repository workflow capable of executing rejected V21 engines is enabled."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REJECTED_WORKFLOWS = (
    ".github/workflows/alpha-discovery.yml",
    ".github/workflows/cpp-stage5-dual-engines-v1.yml",
    ".github/workflows/cpp-stage6-meta-cognition-v1.yml",
    ".github/workflows/cpp-stage6-pr-live-validation.yml",
    ".github/workflows/extract-vtm-result.yml",
    ".github/workflows/stage1b-lrt15m.yml",
)


def job_level_conditions(source: str) -> dict[str, str | None]:
    """Return jobs.<id> conditions; step-level conditions do not count."""
    lines = source.splitlines()
    in_jobs = False
    current: str | None = None
    result: dict[str, str | None] = {}
    for line in lines:
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line and not line.startswith(" "):
            break
        job = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if job:
            current = job.group(1)
            result[current] = None
            continue
        if current is not None:
            cond = re.match(r"^    if:\s*(.*?)\s*(?:#.*)?$", line)
            if cond:
                result[current] = cond.group(1).strip()
    return result


def check() -> list[str]:
    failures: list[str] = []
    for relative in REJECTED_WORKFLOWS:
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"MISSING rejected workflow: {relative}")
            continue
        jobs = job_level_conditions(path.read_text(encoding="utf-8"))
        if not jobs:
            failures.append(f"NO JOBS found in rejected workflow: {relative}")
            continue
        enabled = [name for name, condition in jobs.items() if condition != "false"]
        if enabled:
            failures.append(
                f"REJECTED WORKFLOW NOT HARD-QUARANTINED: {relative}; "
                f"jobs without literal job-level 'if: false': {', '.join(enabled)}"
            )
    return failures


if __name__ == "__main__":
    errors = check()
    if errors:
        for error in errors:
            print(f"::error::{error}")
        print("REJECTED_WORKFLOW_GUARD=FAIL")
        raise SystemExit(1)
    print(f"REJECTED_WORKFLOW_GUARD=PASS workflows={len(REJECTED_WORKFLOWS)}")
