# Archived legacy strategy code

This directory quarantines the retired VTM, Apex Synergy, and Python LRT-15m
strategy implementations (including the quarantined V5 live scan), their strategy-specific workflows, and their tests.
Files are preserved for traceability and are not active production entry points. Compatibility symlinks under signal_autopilot/modules and scripts/ resolve to archived legacy modules so existing imports do not break during transition; remove those links when all legacy consumers are retired.

## Preserved in the active tree

- scripts/build_pit_universe.py: strategy-agnostic PIT universe builder.
- Legacy LRT-1D research sweep and workflow are preserved under archive/.
- signal_autopilot/scripts/binance_vision_1d.py
- signal_autopilot/scripts/binance_vision_derivatives_1d.py
- signal_autopilot/scripts/binance_vision_15m.py
- signal_autopilot/tests/test_binance_vision_15m.py
- signal_autopilot/tests/test_binance_vision_1d.py
- signal_autopilot/tests/test_binance_vision_derivatives_1d.py
- config/universe.json and generic universe validation assets.

## PIT limitation

Candidate symbols are discovered from currently discoverable Binance Vision
archive folders. This does not prove complete historical delisted-symbol
coverage or reconstruct a full historical exchangeInfo status series.
