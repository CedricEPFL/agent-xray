"""Cross-run live-spend guardrails."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class BudgetStop(RuntimeError):
    exit_code = 3


class AbsoluteBudgetExceeded(AssertionError):
    pass


@dataclass(frozen=True)
class BudgetLimits:
    warn_usd: float = 60.0
    stop_usd: float = 80.0
    absolute_usd: float = 100.0

    @classmethod
    def from_env(cls) -> "BudgetLimits":
        limits = cls(
            warn_usd=float(os.getenv("AGENT_XRAY_BUDGET_WARN", "60")),
            stop_usd=float(os.getenv("AGENT_XRAY_BUDGET_STOP", "80")),
            absolute_usd=float(os.getenv("AGENT_XRAY_BUDGET_ABSOLUTE", "100")),
        )
        if not 0 <= limits.warn_usd < limits.stop_usd < limits.absolute_usd:
            raise ValueError("Budget limits must satisfy 0 <= warn < stop < absolute")
        return limits


def live_ledger_total(results_dir: Path) -> float:
    total = 0.0
    for path in results_dir.glob("ledger_live*.jsonl"):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    total += float(json.loads(line).get("usd_cost", 0.0))
    return total


class BudgetGuard:
    def __init__(
        self,
        results_dir: Path,
        limits: BudgetLimits | None = None,
        total_fn: Callable[[], float] | None = None,
    ) -> None:
        self.results_dir = results_dir
        self.limits = limits or BudgetLimits.from_env()
        self._total_fn = total_fn or (lambda: live_ledger_total(results_dir))
        self._lock = threading.Lock()
        self._warned = False

    def check_before_call(self) -> float:
        with self._lock:
            total = self._total_fn()
            if total >= self.limits.absolute_usd:
                raise AbsoluteBudgetExceeded(
                    f"ABSOLUTE_BUDGET_ASSERT: ${total:.2f} >= ${self.limits.absolute_usd:.2f}"
                )
            if total >= self.limits.stop_usd:
                raise BudgetStop(
                    f"BUDGET_STOP: cumulative live ledger cost ${total:.2f} reached "
                    f"${self.limits.stop_usd:.2f}"
                )
            if total >= self.limits.warn_usd and not self._warned:
                logging.warning(
                    "BUDGET_WARNING: cumulative live ledger cost $%.2f reached $%.2f",
                    total,
                    self.limits.warn_usd,
                )
                self._warned = True
            return total
