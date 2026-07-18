import logging
import json
from pathlib import Path

import pytest

from core.budget import BudgetGuard, BudgetLimits, BudgetStop, live_ledger_total


def test_budget_guard_warns_stops_and_asserts(caplog):
    spend = {"value": 60.0}
    guard = BudgetGuard(
        Path(__file__).parent,
        limits=BudgetLimits(warn_usd=60, stop_usd=80, absolute_usd=100),
        total_fn=lambda: spend["value"],
    )
    with caplog.at_level(logging.WARNING):
        assert guard.check_before_call() == 60.0
        assert "BUDGET_WARNING" in caplog.text
    spend["value"] = 80.0
    with pytest.raises(BudgetStop, match="BUDGET_STOP"):
        guard.check_before_call()
    spend["value"] = 100.0
    with pytest.raises(AssertionError, match="ABSOLUTE_BUDGET_ASSERT"):
        guard.check_before_call()


def test_budget_total_sums_all_live_ledger_files():
    results_dir = Path(__file__).parent
    paths = [
        results_dir / "ledger_live_budget_a.jsonl",
        results_dir / "ledger_live_budget_b.jsonl",
    ]
    try:
        paths[0].write_text(json.dumps({"usd_cost": 1.25}) + "\n", encoding="utf-8")
        paths[1].write_text(
            json.dumps({"usd_cost": 2.5}) + "\n" + json.dumps({"usd_cost": 0.25}) + "\n",
            encoding="utf-8",
        )
        assert live_ledger_total(results_dir) == pytest.approx(4.0)
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
