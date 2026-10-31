# MiniMax task SDD-SHIP-2026

Fix `app/shipping.py` so orders totaling exactly CNY 100 receive free
standard shipping. Keep below-threshold price, express surcharge, bad-input
errors, and Decimal output unchanged.

Necessary sources:
- Active specification `specs/shipping.md`, SPEC-SHIP-001 through 005.
- Code `app/shipping.py`, `shipping_quote`.
- Target tests `tests/test_target.py`.
- Regression tests `tests/test_regression.py`.
- PowerContext durable task-state evidence after module/Server restart.

Before the patch: target tests fail due to wrong boundary fee, regressions pass.
After real MiniMax-produced patch: both test groups pass, unchanged.
Also re-import a modified spec into seekdb and show new text from the next DB query.
