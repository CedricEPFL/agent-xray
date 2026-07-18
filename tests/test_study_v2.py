import asyncio
import json
import threading
import time
from pathlib import Path

from core.experiment import ExperimentConfig
from core.math500 import load_math500
from core.providers import MockProvider
from core.study_v2 import MATH_SYSTEMS, MathStudyExperiment, aggregate_math_results


class SlowConcurrencyMock(MockProvider):
    def __init__(self):
        super().__init__(seed=42, model="mock-math500")
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def generate(self, *args, **kwargs):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.005)
            return super().generate(*args, **kwargs)
        finally:
            with self._lock:
                self.active -= 1


def test_async_provider_calls_respect_concurrency_bound():
    provider = SlowConcurrencyMock()
    problem = load_math500(n=1, seed=42, offline_mock=True)[0]
    results_dir = Path(__file__).parent
    ledger_path = results_dir / "ledger__concurrency_test.jsonl"
    ledger_path.unlink(missing_ok=True)
    experiment = MathStudyExperiment(
        provider,
        results_dir,
        ExperimentConfig(sleep_seconds=0, run_id="_concurrency_test"),
        concurrency=3,
    )
    records = []
    try:
        asyncio.run(experiment._samples(problem, "sc@9", 0, 9, records))
        assert 1 < provider.max_active <= 3
    finally:
        ledger_path.unlink(missing_ok=True)


def test_math_study_calibrates_repeats_and_reports_ops_blocks():
    results_dir = Path(__file__).parent
    checkpoint = results_dir / "checkpoint__mathstudy_test.jsonl"
    ledger = results_dir / "ledger__mathstudy_test.jsonl"
    checkpoint.unlink(missing_ok=True)
    ledger.unlink(missing_ok=True)
    problems = load_math500(n=3, seed=7, offline_mock=True)
    experiment = MathStudyExperiment(
        MockProvider(seed=7, model="mock-math500"),
        results_dir,
        ExperimentConfig(sleep_seconds=0, run_id="_mathstudy_test"),
        concurrency=4,
        repeats=2,
    )
    try:
        results = asyncio.run(experiment.run(problems))
        assert set(results["variants"]) == set(MATH_SYSTEMS)
        assert all(item["n"] == 6 for item in results["variants"].values())
        assert results["verdict"]["verdict_n"] == 6
        assert results["study"]["calibration"]["n"] == 3
        assert results["study"]["calibration"]["sc_budget_n"] >= 1
        assert results["study"]["calibration"]["escalate_sc_extra_samples"] >= 1
        assert all(sum(block.values()) == 0 for block in results["missingness"].values())
        assert all(sum(block.values()) == 6 for block in results["scorer_breakdown"].values())
        rows = checkpoint.read_text(encoding="utf-8").splitlines()
        assert len(rows) == 3 * 2 * len(MATH_SYSTEMS)
        checkpoint_rows = [json.loads(row) for row in rows]
        assert all(isinstance(row["level"], int) for row in checkpoint_rows)
        assert all(
            row["scoring_method"] in {"sympy_equiv", "string_match", "failed"}
            for row in checkpoint_rows
        )
        ledger_records = experiment.ledger.records
        assert ledger_records
        assert all(record.timestamp and record.endpoint_model_version for record in ledger_records)
    finally:
        checkpoint.unlink(missing_ok=True)
        ledger.unlink(missing_ok=True)


def test_math_aggregation_reports_missingness_by_system():
    rows = []
    for system in MATH_SYSTEMS:
        rows.append(
            {
                "variant": system,
                "problem_id": "x",
                "repeat": 0,
                "correct": False,
                "scoring_method": "failed",
                "status": "blocked" if system == "full" else "truncated" if system == "sc@9" else "failed",
                "cost_usd": 0.1,
                "input_tokens": 1,
                "output_tokens": 1,
                "latency_ms": 1.0,
                "component_costs": {"generate": 0.1},
            }
        )
    results = aggregate_math_results(
        rows,
        model="mock-math500",
        config=ExperimentConfig(sleep_seconds=0),
        problem_count=1,
        repeats=1,
        calibration={},
    )
    assert results["missingness"]["full"] == {"failed": 0, "blocked": 1, "truncated": 0}
    assert results["missingness"]["sc@9"] == {"failed": 0, "blocked": 0, "truncated": 1}
    assert results["missingness"]["cot@1"]["failed"] == 1
    assert results["scorer_breakdown"]["full"]["failed"] == 1
