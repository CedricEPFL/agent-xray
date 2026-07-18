import json
from pathlib import Path

from core.experiment import Experiment, ExperimentConfig, aggregate_results, select_compute_matched
from core.gsm8k import Problem
from core.providers import MockProvider
from core.run import run_aggregate_only
from core.workflow import build_variant_matrix, variant_by_name


class CountingMockProvider(MockProvider):
    def __init__(self):
        super().__init__(seed=42)
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return super().generate(*args, **kwargs)


class RecordingMockProvider(MockProvider):
    def __init__(self):
        super().__init__(seed=42)
        self.sequence = []

    def generate(self, *args, **kwargs):
        self.sequence.append((kwargs["problem_id"], kwargs["variant"]))
        return super().generate(*args, **kwargs)


def test_compute_matching_selects_closest_measured_cost():
    costs = {"cot@1": 0.1, "sc@3": 0.31, "sc@5": 0.52}
    assert select_compute_matched(0.36, costs) == "sc@3"
    assert select_compute_matched(0.50, costs) == "sc@5"


def test_experiment_runs_all_variants_problem_major():
    problems = [
        Problem("a", "What is 2 + 2?", "2+2=4. #### 4", "4"),
        Problem("b", "What is 3 + 3?", "3+3=6. #### 6", "6"),
    ]
    config = ExperimentConfig(sleep_seconds=0, run_id="_order_test")
    results_dir = Path(__file__).parent
    artifacts = [
        results_dir / "checkpoint__order_test.jsonl",
        results_dir / "ledger__order_test.jsonl",
    ]
    for path in artifacts:
        path.unlink(missing_ok=True)
    try:
        provider = RecordingMockProvider()
        Experiment(provider, results_dir, config).run(problems)
        transitions = []
        for call in provider.sequence:
            if not transitions or transitions[-1] != call:
                transitions.append(call)
        names = [spec.name for spec in build_variant_matrix()]
        assert transitions == [(problem.problem_id, name) for problem in problems for name in names]
    finally:
        for path in artifacts:
            path.unlink(missing_ok=True)


def _result_row(variant, problem_id, *, correct, cost):
    return {
        "variant": variant,
        "problem_id": problem_id,
        "correct": correct,
        "cost_usd": cost,
        "input_tokens": 10,
        "output_tokens": 5,
        "latency_ms": 1.0,
        "component_costs": {"generate": cost},
    }


def test_verdict_uses_only_problem_intersection_when_n_is_unequal():
    rows = [
        _result_row("full", "a", correct=True, cost=1.0),
        _result_row("full", "b", correct=False, cost=100.0),
        _result_row("cot@1", "a", correct=False, cost=0.9),
        _result_row("cot@1", "b", correct=True, cost=20.0),
        _result_row("sc@3", "a", correct=True, cost=1.2),
        _result_row("sc@5", "a", correct=False, cost=2.0),
        _result_row("sc@5", "c", correct=True, cost=2.0),
    ]
    result = aggregate_results(
        rows,
        build_variant_matrix(),
        "mock-gsm8k",
        ExperimentConfig(sleep_seconds=0),
        sample_size=3,
    )
    verdict = result["verdict"]
    assert verdict["verdict_n"] == 1
    assert verdict["cost_matched_variant"] == "cot@1"
    assert verdict["full_mean_cost_usd"] == 1.0
    assert verdict["full_accuracy"] == 1.0
    assert verdict["baseline_accuracy"] == 0.0
    assert verdict["gain_over_cost_matched_sc"] == 1.0


def test_checkpoint_resume_skips_completed_problem():
    first = Problem("a", "What is 2 + 2?", "2+2=4. #### 4", "4")
    second = Problem("b", "What is 3 + 3?", "3+3=6. #### 6", "6")
    config = ExperimentConfig(sleep_seconds=0, run_id="_resume_test")
    variant = [variant_by_name("cot@1")]
    results_dir = Path(__file__).parent
    artifacts = [
        results_dir / "checkpoint__resume_test.jsonl",
        results_dir / "ledger__resume_test.jsonl",
    ]
    for path in artifacts:
        path.unlink(missing_ok=True)
    try:
        initial_provider = CountingMockProvider()
        Experiment(initial_provider, results_dir, config, variants=variant).run([first])
        assert initial_provider.calls == 1

        resumed_provider = CountingMockProvider()
        result = Experiment(resumed_provider, results_dir, config, variants=variant).run([first, second])
        assert resumed_provider.calls == 1
        assert result["variants"]["cot@1"]["n"] == 2
    finally:
        for path in artifacts:
            path.unlink(missing_ok=True)


def test_gsm_checkpoint_key_includes_repeat():
    problem = Problem("repeat-a", "What is 4 + 4?", "4+4=8. #### 8", "8")
    config = ExperimentConfig(sleep_seconds=0, run_id="_repeat_test", repeats=2)
    variant = [variant_by_name("cot@1")]
    results_dir = Path(__file__).parent
    artifacts = [
        results_dir / "checkpoint__repeat_test.jsonl",
        results_dir / "ledger__repeat_test.jsonl",
    ]
    for path in artifacts:
        path.unlink(missing_ok=True)
    try:
        provider = CountingMockProvider()
        result = Experiment(provider, results_dir, config, variants=variant).run([problem])
        rows = [json.loads(line) for line in artifacts[0].read_text(encoding="utf-8").splitlines()]
        assert provider.calls == 2
        assert {row["repeat"] for row in rows} == {0, 1}
        assert result["variants"]["cot@1"]["n"] == 2
        assert result["metadata"]["repeat_count"] == 2
    finally:
        for path in artifacts:
            path.unlink(missing_ok=True)


def test_aggregate_only_reports_partial_checkpoint_without_provider(monkeypatch):
    results_dir = Path(__file__).parent
    checkpoint_path = results_dir / "checkpoint_live_n5_seed42.jsonl"
    results_path = results_dir / "results.json"
    report_path = results_dir / "REPORT.md"
    artifacts = [checkpoint_path, results_path, report_path]
    for path in artifacts:
        path.unlink(missing_ok=True)

    variants = build_variant_matrix()
    rows = []
    for problem_id in ("complete-1", "complete-2", "complete-3"):
        rows.extend(
            _result_row(spec.name, problem_id, correct=True, cost=index + 1.0)
            for index, spec in enumerate(variants)
        )
    rows.extend(
        [
            _result_row("full", "partial-1", correct=False, cost=1.0),
            _result_row("-critique", "partial-1", correct=True, cost=2.0),
            _result_row("-vote", "partial-2", correct=True, cost=4.0),
            _result_row("cot@1", "partial-2", correct=True, cost=5.0),
        ]
    )
    checkpoint_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    def provider_must_not_initialize(*args, **kwargs):
        raise AssertionError("aggregate-only instantiated GeminiProvider")

    monkeypatch.setattr("core.run.GeminiProvider.__init__", provider_must_not_initialize)
    try:
        results, written_json, written_report = run_aggregate_only(
            results_dir=results_dir,
            is_mock=False,
            n=5,
            seed=42,
        )
        assert written_json == results_path
        assert written_report == report_path
        assert results["metadata"]["completed_sample_size"] == 3
        assert results["metadata"]["checkpoint_rows"] == 25
        assert results["variants"]["full"]["n"] == 4
        assert results["variants"]["-critique"]["n"] == 4
        assert results["variants"]["-revise"]["n"] == 3
        assert results["variants"]["-vote"]["n"] == 4
        assert results["variants"]["cot@1"]["n"] == 4
        assert results["variants"]["sc@3"]["n"] == 3
        assert results["variants"]["sc@5"]["n"] == 3
        assert results["verdict"]["verdict_n"] == 3
        report = report_path.read_text(encoding="utf-8")
        assert "Sample: n=3/5 problems (PARTIAL RUN — free-tier quota interrupted)" in report
        assert "Checkpoint rows: 25" in report
    finally:
        for path in artifacts:
            path.unlink(missing_ok=True)
