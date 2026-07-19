"""Sequential, resumable experiment runner and result aggregation."""

from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .budget import BudgetGuard, BudgetStop
from .gsm8k import Problem
from .ledger import CallRecord, Ledger
from .providers import LLMProvider, LLMResponse
from .scoring import exact_match, wilson_interval
from .workflow import VariantSpec, build_variant_matrix, run_workflow


@dataclass(frozen=True)
class ExperimentConfig:
    sleep_seconds: float = 4.0
    max_retries: int = 6
    backoff_base_seconds: float = 1.0
    temperature: float = 0.7
    seed: int = 42
    run_id: str = "experiment"
    repeats: int = 1


def select_compute_matched(
    full_mean_cost: float,
    baseline_mean_costs: Mapping[str, float],
) -> str:
    """Select the baseline with the smallest absolute measured cost gap."""

    if not baseline_mean_costs:
        raise ValueError("at least one baseline cost is required")
    return min(
        baseline_mean_costs,
        key=lambda name: (abs(baseline_mean_costs[name] - full_mean_cost), baseline_mean_costs[name], name),
    )


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    response = getattr(exc, "response", None)
    status = status or getattr(response, "status_code", None)
    try:
        if int(status) == 429 or 500 <= int(status) <= 599:
            return True
    except (TypeError, ValueError):
        pass
    message = str(exc).lower()
    return "429" in message or any(str(code) in message for code in range(500, 600))


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


class Experiment:
    def __init__(
        self,
        provider: LLMProvider,
        results_dir: Path,
        config: ExperimentConfig | None = None,
        variants: list[VariantSpec] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        budget_guard: BudgetGuard | None = None,
    ) -> None:
        self.provider = provider
        self.results_dir = results_dir
        self.config = config or ExperimentConfig()
        if self.config.repeats <= 0:
            raise ValueError("repeats must be positive")
        self.variants = variants or build_variant_matrix()
        self.sleep_fn = sleep_fn
        self.budget_guard = budget_guard
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = results_dir / f"checkpoint_{self.config.run_id}.jsonl"
        self.ledger = Ledger(results_dir / f"ledger_{self.config.run_id}.jsonl")
        self._jitter = random.Random(self.config.seed)

    def _provider_call(
        self,
        prompt: str,
        *,
        variant: str,
        component: str,
        problem: Problem,
        sample_index: int,
        repeat: int,
    ) -> tuple[LLMResponse, CallRecord]:
        for attempt in range(self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                if self.budget_guard is not None:
                    self.budget_guard.check_before_call()
                response = self.provider.generate(
                    prompt,
                    variant=variant,
                    component=component,
                    problem_id=problem.problem_id,
                    temperature=self.config.temperature,
                    metadata={
                        "gold_answer": problem.numeric_answer,
                        "sample_index": sample_index,
                        "repeat": repeat,
                    },
                )
                measured_latency_ms = (time.perf_counter() - started) * 1000
                latency_ms = response.simulated_latency_ms or measured_latency_ms
                record = CallRecord.priced(
                    variant=variant,
                    component=component,
                    problem_id=problem.problem_id,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency_ms=latency_ms,
                    model=response.model,
                    repeat=repeat,
                    endpoint_model_version=response.endpoint_model_version,
                    finish_reason=response.finish_reason,
                    blocked=response.blocked,
                )
                self.ledger.append(record)
                if self.config.sleep_seconds > 0:
                    self.sleep_fn(self.config.sleep_seconds)
                return response, record
            except BudgetStop:
                raise
            except Exception as exc:
                if attempt >= self.config.max_retries or not _is_retryable(exc):
                    raise
                delay = self.config.backoff_base_seconds * (2**attempt)
                delay *= 0.75 + self._jitter.random() * 0.5
                self.sleep_fn(delay)
        raise AssertionError("retry loop exhausted unexpectedly")

    def _run_problem(self, spec: VariantSpec, problem: Problem, repeat: int = 0) -> dict[str, Any]:
        records: list[CallRecord] = []

        def call(prompt: str, component: str, sample_index: int) -> LLMResponse:
            response, record = self._provider_call(
                prompt,
                variant=spec.name,
                component=component,
                problem=problem,
                sample_index=sample_index,
                repeat=repeat,
            )
            records.append(record)
            return response

        prediction = run_workflow(spec, problem.question, call)
        component_costs: dict[str, float] = {}
        for record in records:
            component_costs[record.component] = component_costs.get(record.component, 0.0) + record.usd_cost
        return {
            "variant": spec.name,
            "problem_id": problem.problem_id,
            "repeat": repeat,
            "prediction": prediction,
            "reference": problem.numeric_answer,
            "correct": exact_match(prediction, problem.numeric_answer),
            "cost_usd": sum(record.usd_cost for record in records),
            "input_tokens": sum(record.input_tokens for record in records),
            "output_tokens": sum(record.output_tokens for record in records),
            "latency_ms": sum(record.latency_ms for record in records),
            "component_costs": component_costs,
            "problem": problem.question,
        }

    def _append_checkpoint(self, row: Mapping[str, Any]) -> None:
        with self.checkpoint_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")

    def run(self, problems: list[Problem]) -> dict[str, Any]:
        expected_ids = {problem.problem_id for problem in problems}
        expected_variants = {spec.name for spec in self.variants}
        checkpoint_rows = [
            row
            for row in _read_jsonl(self.checkpoint_path)
            if row.get("problem_id") in expected_ids and row.get("variant") in expected_variants
        ]
        completed: dict[tuple[str, str, int], dict[str, Any]] = {
            (row["variant"], row["problem_id"], int(row.get("repeat", 0))): row
            for row in checkpoint_rows
        }

        for repeat in range(self.config.repeats):
            for problem in problems:
                for spec in self.variants:
                    key = (spec.name, problem.problem_id, repeat)
                    if key in completed:
                        continue
                    row = self._run_problem(spec, problem, repeat)
                    self._append_checkpoint(row)
                    completed[key] = row

        ordered_rows = [
            completed[(spec.name, problem.problem_id, repeat)]
            for repeat in range(self.config.repeats)
            for problem in problems
            for spec in self.variants
        ]
        return aggregate_results(ordered_rows, self.variants, self.provider.model, self.config, len(problems))


def aggregate_results(
    rows: list[dict[str, Any]],
    variants: list[VariantSpec],
    model: str,
    config: ExperimentConfig,
    sample_size: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "metadata": {
            "model": model,
            "temperature": config.temperature,
            "sample_size": sample_size,
            "seed": config.seed,
            "repeat_count": config.repeats,
            "ci_method": "Wilson 95% binomial interval",
        },
        "study": {"name": "gsm8k", "systems": [spec.name for spec in variants]},
        "variants": {},
        "missingness": {},
        "scorer_breakdown": {},
    }
    for spec in variants:
        selected = [row for row in rows if row["variant"] == spec.name]
        total = len(selected)
        correct = sum(bool(row["correct"]) for row in selected)
        total_cost = sum(float(row["cost_usd"]) for row in selected)
        component_totals: dict[str, float] = {}
        for row in selected:
            for component, cost in row["component_costs"].items():
                component_totals[component] = component_totals.get(component, 0.0) + float(cost)
        lower, upper = wilson_interval(correct, total)
        mean_cost = total_cost / total if total else 0.0
        output["variants"][spec.name] = {
            "n": total,
            "correct": correct,
            "accuracy": correct / total if total else 0.0,
            "ci": {"lower": lower, "upper": upper, "level": 0.95},
            "mean_cost_usd": mean_cost,
            "cost_per_success_usd": total_cost / correct if correct else None,
            "mean_input_tokens": sum(row["input_tokens"] for row in selected) / total if total else 0.0,
            "mean_output_tokens": sum(row["output_tokens"] for row in selected) / total if total else 0.0,
            "mean_latency_ms": sum(row["latency_ms"] for row in selected) / total if total else 0.0,
            "per_component_cost_share": {
                component: cost / total_cost if total_cost else 0.0
                for component, cost in sorted(component_totals.items())
            },
        }
        output["missingness"][spec.name] = {
            "failed": 0,
            "blocked": 0,
            "truncated": 0,
        }
        output["scorer_breakdown"][spec.name] = {"exact_match": total}

    variants_output = output["variants"]
    if "full" in variants_output:
        full_accuracy = variants_output["full"]["accuracy"]
        for item in variants_output.values():
            item["accuracy_delta_vs_full"] = item["accuracy"] - full_accuracy
    verdict_inputs = {"full", "cot@1", "sc@3", "sc@5"}
    if verdict_inputs.issubset(variants_output):
        rows_by_variant = {
            name: {
                (row["problem_id"], int(row.get("repeat", 0))): row
                for row in rows
                if row["variant"] == name
            }
            for name in verdict_inputs
        }
        shared_problem_ids = sorted(
            set.intersection(*(set(problem_rows) for problem_rows in rows_by_variant.values()))
        )
        verdict_n = len(shared_problem_ids)
        if verdict_n:
            shared_costs = {
                name: sum(float(problem_rows[problem_id]["cost_usd"]) for problem_id in shared_problem_ids)
                / verdict_n
                for name, problem_rows in rows_by_variant.items()
            }
            shared_accuracies = {
                name: sum(bool(problem_rows[problem_id]["correct"]) for problem_id in shared_problem_ids)
                / verdict_n
                for name, problem_rows in rows_by_variant.items()
            }
            matched = select_compute_matched(
                shared_costs["full"],
                {name: shared_costs[name] for name in ("cot@1", "sc@3", "sc@5")},
            )
            gain = shared_accuracies["full"] - shared_accuracies[matched]
            output["verdict"] = {
                "verdict_n": verdict_n,
                "cost_matched_variant": matched,
                "full_mean_cost_usd": shared_costs["full"],
                "baseline_mean_cost_usd": shared_costs[matched],
                "full_accuracy": shared_accuracies["full"],
                "baseline_accuracy": shared_accuracies[matched],
                "gain_over_cost_matched_sc": gain,
                "gain_percentage_points": gain * 100,
            }
        else:
            output["verdict"] = {
                "verdict_n": 0,
                "cost_matched_variant": None,
                "full_mean_cost_usd": None,
                "baseline_mean_cost_usd": None,
                "full_accuracy": None,
                "baseline_accuracy": None,
                "gain_over_cost_matched_sc": None,
                "gain_percentage_points": None,
            }
    return output


def aggregate_checkpoint(
    *,
    results_dir: Path,
    config: ExperimentConfig,
    model: str,
    requested_n: int,
    variants: list[VariantSpec] | None = None,
) -> dict[str, Any]:
    """Aggregate completed checkpoint rows without invoking an LLM provider."""

    if requested_n <= 0:
        raise ValueError("requested_n must be positive")
    variants = variants or build_variant_matrix()
    expected_variants = {spec.name for spec in variants}
    checkpoint_path = results_dir / f"checkpoint_{config.run_id}.jsonl"
    checkpoint_rows = list(_read_jsonl(checkpoint_path))
    valid_rows = [
        row
        for row in checkpoint_rows
        if row.get("variant") in expected_variants and row.get("problem_id") is not None
    ]
    completed_rows = {
        (row["variant"], str(row["problem_id"]), int(row.get("repeat", 0))): row
        for row in valid_rows
    }

    variants_by_problem: dict[tuple[str, int], set[str]] = defaultdict(set)
    for variant, problem_id, repeat in completed_rows:
        variants_by_problem[(problem_id, repeat)].add(variant)
    completed_n = sum(
        completed_variants == expected_variants
        for completed_variants in variants_by_problem.values()
    )

    results = aggregate_results(
        list(completed_rows.values()),
        variants,
        model,
        config,
        sample_size=requested_n,
    )
    results["metadata"].update(
        {
            "requested_sample_size": requested_n,
            "completed_sample_size": completed_n,
            "checkpoint_rows": len(checkpoint_rows),
            "partial_run": completed_n < requested_n,
        }
    )
    return results
