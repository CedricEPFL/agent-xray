import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.ledger import CallRecord, Ledger, PRICES, compute_usd_cost


def test_cost_arithmetic_at_list_prices():
    expected = (2_000 * PRICES["gemini-2.5-flash-lite"]["input"] + 500 * PRICES["gemini-2.5-flash-lite"]["output"]) / 1_000_000
    assert compute_usd_cost("gemini-2.5-flash-lite", 2_000, 500) == pytest.approx(expected)


def test_current_gemini_model_price_is_configured():
    assert PRICES["gemini-3.1-flash-lite"] == {"input": 0.25, "output": 1.50}
    expected = (2_000 * 0.25 + 500 * 1.50) / 1_000_000
    assert compute_usd_cost("gemini-3.1-flash-lite", 2_000, 500) == pytest.approx(expected)


def test_ledger_jsonl_round_trip():
    path = Path(__file__).with_name("_ledger_test.jsonl")
    path.unlink(missing_ok=True)
    record = CallRecord.priced(
        variant="full",
        component="generate",
        problem_id="7",
        input_tokens=100,
        output_tokens=25,
        latency_ms=12.5,
        model="mock-gsm8k",
    )
    try:
        Ledger(path).append(record)
        assert len(path.read_text(encoding="utf-8").splitlines()) == 1
        assert json.loads(path.read_text(encoding="utf-8"))["usd_cost"] == pytest.approx(record.usd_cost)
        assert Ledger(path).records == [record]
    finally:
        path.unlink(missing_ok=True)


def test_ledger_append_is_thread_safe_and_records_ops_fields():
    path = Path(__file__).with_name("_ledger_thread_test.jsonl")
    path.unlink(missing_ok=True)
    ledger = Ledger(path)

    def append(index):
        ledger.append(
            CallRecord.priced(
                variant="sc@3",
                component="generate",
                problem_id=str(index),
                repeat=2,
                input_tokens=10,
                output_tokens=5,
                latency_ms=1.0,
                model="mock-math500",
                endpoint_model_version="mock-math500-seeded-v2",
                finish_reason="STOP",
                blocked=False,
            )
        )

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(append, range(40)))
        loaded = Ledger(path).records
        assert len(loaded) == 40
        assert len(path.read_text(encoding="utf-8").splitlines()) == 40
        assert all(record.timestamp and record.endpoint_model_version for record in loaded)
        assert all(record.repeat == 2 and record.finish_reason == "STOP" for record in loaded)
    finally:
        path.unlink(missing_ok=True)
