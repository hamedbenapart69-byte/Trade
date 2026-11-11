#!/usr/bin/env python3
"""Detective policy guard: secret-like files, sensitive direct pushes, branch drift."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath

SENSITIVE_WORKFLOW = re.compile(
    r"^\.github/workflows/.*(telegram|cloudflare|signal_bot|signal-bot).*\.ya?ml$",
    re.IGNORECASE,
)
SECRET_NAME = re.compile(
    r"(^|/)\.env(?:\..*)?$|\.env$|\.pem$|(^|/)secrets\.[^/]+$",
    re.IGNORECASE,
)
PRIVATE_KEY = re.compile(
    r"-{5}BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-{5}|"
    r"-{5}BEGIN PGP PRIVATE KEY BLOCK-{5}",
    re.IGNORECASE,
)


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def changed_paths(base: str, head: str, event: str) -> list[str]:
    if not base or set(base) == {"0"}:
        return run_git("diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines()
    if event == "pull_request":
        return run_git("diff", "--name-only", f"{base}...{head}").splitlines()
    return run_git("diff", "--name-only", base, head).splitlines()


def is_secret_path(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    if name == ".env.example":
        return False
    return bool(SECRET_NAME.search(name) or SECRET_NAME.search(path))


def classify_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    secret_paths = [p for p in paths if is_secret_path(p)]
    sensitive_workflows = [p for p in paths if SENSITIVE_WORKFLOW.search(p)]
    return secret_paths, sensitive_workflows


def scan_diff_for_private_keys(base: str, head: str, event: str) -> bool:
    if not base or set(base) == {"0"}:
        diff = run_git("show", "--format=", "--no-ext-diff", head)
    else:
        separator = "..." if event == "pull_request" else ""
        revision = f"{base}{separator}{head}" if separator else base
        args = ["diff", "--no-ext-diff", "--unified=0"]
        if separator:
            args.append(revision)
        else:
            args.extend([base, head])
        diff = run_git(*args)
    return bool(PRIVATE_KEY.search(diff))


def branch_drift() -> tuple[int, int] | None:
    try:
        run_git("fetch", "--no-tags", "origin", "main", "stage1b-lrt15m")
        run_git("merge-base", "origin/main", "origin/stage1b-lrt15m")
        counts = run_git(
            "rev-list", "--left-right", "--count",
            "origin/main...origin/stage1b-lrt15m",
        )
        left, right = counts.split()
        return int(left), int(right)
    except (subprocess.CalledProcessError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", required=True)
    args = parser.parse_args()

    paths = changed_paths(args.base, args.head, args.event)
    secret_paths, sensitive_workflows = classify_paths(paths)
    private_key_found = scan_diff_for_private_keys(args.base, args.head, args.event)

    if secret_paths:
        print("::error::Secret-like file paths detected (names only): " + ", ".join(secret_paths))
    if private_key_found:
        print("::error::Private-key material detected in changed diff; content suppressed.")
    if secret_paths or private_key_found:
        print("POLICY_GUARD=FAIL")
        return 1

    if args.event == "push" and sensitive_workflows:
        print("::warning::Sensitive Telegram/Cloudflare workflow changed by direct push to main: "
              + ", ".join(sensitive_workflows))
    elif sensitive_workflows:
        print("POLICY_GUARD_SENSITIVE_WORKFLOW_CHANGE=" + ",".join(sensitive_workflows))

    drift = branch_drift()
    if drift is None:
        print("::warning::Could not compare main and stage1b-lrt15m; branch compatibility is UNKNOWN.")
    else:
        main_only, stage_only = drift
        if main_only or stage_only:
            print(
                "::warning::Branch drift detected: "
                f"main_only={main_only}, stage1b_only={stage_only}. Review before promotion."
            )
        else:
            print("BRANCH_COMPATIBILITY=IN_SYNC")

    print(f"POLICY_GUARD=PASS changed_paths={len(paths)} event={args.event}")
    print("CONTROL_TYPE=DETECTIVE_ONLY_NOT_BRANCH_PROTECTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
