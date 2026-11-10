# M0 Diagnostics — pytest import-path repair

## Scope
- Repository: hamedbenapart69-byte/Trade
- Base commit: 10ba55136ef3a88b9b3638634b19190fbee5cf2f
- Fix commit: e85276e43a0ff0d3c84d9823b768863956241494
- Workflow run: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42780913567
- Job ID: 129710463710

## Root-cause evidence
The repository contains two separate Python package roots:
- Root application package: `app/` (including app/store.py, app/main.py, app/integrations/)
- Signal pipeline package root: `signal_autopilot/` (including signal_autopilot/modules/ and signal_autopilot/app/)

The first attempted pytest configuration prepended `signal_autopilot` to sys.path. This resolved `from modules...` in signal_autopilot tests, but caused root tests importing `app` to resolve the wrong package: `signal_autopilot/app/__init__.py`. The resulting CI log included:
- `ImportError: cannot import name 'store' from 'app' (/home/runner/work/Trade/Trade/signal_autopilot/app/__init__.py)`
- `ModuleNotFoundError: No module named 'app.integrations'`
- `ModuleNotFoundError: No module named 'app.main'`
The failed run was https://github.com/hamedbenapart69-byte/Trade/actions/runs/42779134772.

## Root fix
- Removed `signal_autopilot` from pytest's globally prepended pythonpath.
- Added root `conftest.py` that appends `signal_autopilot/` to sys.path.
- This preserves repository-root precedence for `app`, while making `modules` importable for signal_autopilot tests.
- No test files were modified.

## Failure prediction and blast radius
Blast radius: test collection and import resolution for both root application tests and signal_autopilot tests. Runtime trading logic and deployed pipeline files were not changed.

Predicted failure modes:
1. Root `app` shadowed by `signal_autopilot/app`: early warning is imports resolving to the wrong `__file__`; observed on the first attempt.
2. `modules` unavailable to signal_autopilot tests: early warning is ModuleNotFoundError during collection; not observed after the fix.
3. Dependency/Python-version incompatibility: early warning is installation failure or import/runtime errors before test execution; dependency installation succeeded under Python 3.12.16.

Pre-flight: inspect both package roots and confirm path ordering before invoking the complete repository test suite.

Rollback: revert fix commit `e85276e43a0ff0d3c84d9823b768863956241494`; previous commit remains `10ba55136ef3a88b9b3638634b19190fbee5cf2f`.

## Verification
Command executed by GitHub Actions:
```bash
python -m pytest -v --tb=short
```
Environment: Python 3.12.16, pytest 9.2.0.
Collection: 159 items.
Result: 159 passed, 3 warnings in 6.14s.
Warnings:
- Starlette TestClient/httpx deprecation.
- FastAPI `@app.on_event` deprecation at app/main.py:81 (reported twice).
No test file changes were made.

## Post-change self-check
1. Regression: all 159 repository tests passed, including both package roots.
2. Root cause: fixed import-path precedence rather than suppressing import exceptions.
3. Long-term risk: future package layout changes may reintroduce top-level `app` name collisions.
4. Fragile assumption: pytest loads root conftest before test module imports; confirmed by successful collection and execution.
5. Independent break attempt: remove conftest path append; signal_autopilot tests would again fail to import `modules`. Rename package roots would be a broader architectural cleanup, not needed for this minimal fix.
6. Rollback is a single revert commit.

## Remaining watch items
- Deprecation warnings in app/main.py and Starlette/httpx integration.
- This test run validates test suite behavior, not production signal quality, live exchange access, Telegram delivery, or OOS trading performance.
