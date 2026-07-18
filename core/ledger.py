"""Per-call accounting and append-only JSON-lines persistence."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


# USD per one million tokens at public list price.
PRICES: dict[str, dict[str, float]] = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "mock-gsm8k": {"input": 0.10, "output": 0.40},
    "mock-math500": {"input": 0.10, "output": 0.40},
}


def compute_usd_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts cannot be negative")
    try:
        price = PRICES[model]
    except KeyError as exc:
        raise KeyError(f"No list price configured for model {model!r}") from exc
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


@dataclass(frozen=True)
class CallRecord:
    variant: str
    component: str
    problem_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str
    usd_cost: float
    repeat: int = 0
    endpoint_model_version: str | None = None
    timestamp: str = ""
    finish_reason: str | None = None
    blocked: bool = False

    @classmethod
    def priced(
        cls,
        *,
        variant: str,
        component: str,
        problem_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        model: str,
        repeat: int = 0,
        endpoint_model_version: str | None = None,
        timestamp: str | None = None,
        finish_reason: str | None = None,
        blocked: bool = False,
    ) -> "CallRecord":
        return cls(
            variant=variant,
            component=component,
            problem_id=problem_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            model=model,
            usd_cost=compute_usd_cost(model, input_tokens, output_tokens),
            repeat=repeat,
            endpoint_model_version=endpoint_model_version or model,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            finish_reason=finish_reason,
            blocked=blocked,
        )


class Ledger:
    """In-memory records mirrored to disk as soon as each call completes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.records: list[CallRecord] = []
        self._lock = threading.RLock()
        if path and path.exists():
            self.records = list(self._read(path))

    @staticmethod
    def _read(path: Path) -> Iterable[CallRecord]:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield CallRecord(**json.loads(line))

    def append(self, record: CallRecord) -> None:
        with self._lock:
            self.records.append(record)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")

    def for_problem(self, variant: str, problem_id: str) -> list[CallRecord]:
        with self._lock:
            return [r for r in self.records if r.variant == variant and r.problem_id == problem_id]

    def total_usd(self) -> float:
        with self._lock:
            return sum(record.usd_cost for record in self.records)
