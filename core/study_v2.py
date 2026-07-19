"""Async MATH-500 confirmatory-study harness."""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from .budget import AbsoluteBudgetExceeded, BudgetGuard, BudgetStop
from .experiment import ExperimentConfig, _is_retryable
from .ledger import CallRecord, Ledger
from .math500 import MathProblem
from .math_scoring import extract_math_answer, normalize_math_string, score_math_answer
from .providers import LLMProvider, LLMResponse
from .scoring import wilson_interval


MATH_SYSTEMS = (
    "cot@1",
    "sc@3",
    "sc@9",
    "sc@budget",
    "full",
    "escalate_structure",
    "escalate_sc",
)
CALIBRATION_FILENAME = "calibration_math500.json"


def _read_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _majority(candidates: Sequence[str]) -> str:
    extracted = [extract_math_answer(candidate) for candidate in candidates]
    normalized = [normalize_math_string(answer) for answer in extracted]
    usable = [(raw, norm) for raw, norm in zip(extracted, normalized) if raw and norm]
    if not usable:
        return candidates[0] if candidates else ""
    counts = Counter(norm for _, norm in usable)
    winner = max(counts, key=counts.get)
    raw = next(raw for raw, norm in usable if norm == winner)
    return rf"Final answer: \boxed{{{raw}}}"


def _unanimous(candidates: Sequence[str]) -> bool:
    answers = [normalize_math_string(extract_math_answer(candidate)) for candidate in candidates]
    return bool(answers) and all(answers) and len(set(answers)) == 1


def _nearest_sample_count(target_cost: float, sample_cost: float) -> int:
    if target_cost <= 0 or sample_cost <= 0:
        return 1
    raw = target_cost / sample_cost
    choices = {max(1, int(raw)), max(1, int(raw) + 1)}
    return min(choices, key=lambda count: (abs(count * sample_cost - target_cost), count))


class MathStudyExperiment:
    def __init__(
        self,
        provider: LLMProvider,
        results_dir: Path,
        config: ExperimentConfig,
        *,
        concurrency: int = 8,
        repeats: int = 1,
        budget_guard: BudgetGuard | None = None,
        systems: Sequence[str] | None = None,
    ) -> None:
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if repeats <= 0:
            raise ValueError("repeats must be positive")
        self.provider = provider
        self.results_dir = results_dir
        self.config = config
        self.repeats = repeats
        requested_systems = tuple(systems) if systems is not None else MATH_SYSTEMS
        if not requested_systems:
            raise ValueError("at least one MATH system is required")
        invalid_systems = set(requested_systems) - set(MATH_SYSTEMS)
        if invalid_systems:
            raise ValueError(f"unknown MATH systems: {', '.join(sorted(invalid_systems))}")
        self.systems = tuple(name for name in MATH_SYSTEMS if name in requested_systems)
        self.filtered_systems = systems is not None
        self.semaphore = asyncio.Semaphore(concurrency)
        self.budget_guard = budget_guard
        self.checkpoint_path = results_dir / f"checkpoint_{config.run_id}.jsonl"
        self.calibration_path = results_dir / CALIBRATION_FILENAME
        self.ledger = Ledger(results_dir / f"ledger_{config.run_id}.jsonl")
        self._checkpoint_lock = asyncio.Lock()
        self._completed: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.sc_budget_n = 1
        self.escalate_sc_extra_samples = 1
        self.calibration: dict[str, Any] = {}
        results_dir.mkdir(parents=True, exist_ok=True)
        for row in _read_checkpoint(self.checkpoint_path):
            if row.get("variant") in self.systems and row.get("problem_id") is not None:
                key = (row["variant"], str(row["problem_id"]), int(row.get("repeat", 0)))
                self._completed[key] = row

    async def _call(
        self,
        prompt: str,
        *,
        variant: str,
        component: str,
        problem: MathProblem,
        repeat: int,
        sample_index: int,
    ) -> tuple[LLMResponse, CallRecord]:
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self.semaphore:
                    if self.budget_guard is not None:
                        await asyncio.to_thread(self.budget_guard.check_before_call)
                    started = time.perf_counter()
                    response = await asyncio.to_thread(
                        self.provider.generate,
                        prompt,
                        variant=variant,
                        component=component,
                        problem_id=problem.problem_id,
                        temperature=self.config.temperature,
                        metadata={
                            "gold_answer": problem.answer,
                            "sample_index": sample_index,
                            "repeat": repeat,
                            "study": "math500",
                        },
                    )
                    measured_latency_ms = (time.perf_counter() - started) * 1000
                record = CallRecord.priced(
                    variant=variant,
                    component=component,
                    problem_id=problem.problem_id,
                    repeat=repeat,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency_ms=response.simulated_latency_ms or measured_latency_ms,
                    model=response.model,
                    endpoint_model_version=response.endpoint_model_version,
                    finish_reason=response.finish_reason,
                    blocked=response.blocked,
                )
                self.ledger.append(record)
                if self.config.sleep_seconds > 0:
                    await asyncio.sleep(self.config.sleep_seconds)
                return response, record
            except BudgetStop:
                raise
            except AbsoluteBudgetExceeded:
                raise
            except Exception as exc:
                if attempt >= self.config.max_retries or not _is_retryable(exc):
                    raise
                delay = self.config.backoff_base_seconds * (2**attempt)
                await asyncio.sleep(delay * (0.75 + ((attempt * 37 + repeat * 11) % 50) / 100))
        raise AssertionError("retry loop exhausted unexpectedly")

    async def _generate(
        self,
        problem: MathProblem,
        variant: str,
        repeat: int,
        sample_index: int,
        records: list[CallRecord],
    ) -> str:
        prompt = (
            "Solve the competition mathematics problem carefully. Show concise reasoning and end with "
            "exactly one final expression in \\boxed{...}. Preserve exact fractions and radicals.\n\n"
            f"Problem: {problem.problem}"
        )
        response, record = await self._call(
            prompt,
            variant=variant,
            component="generate",
            problem=problem,
            repeat=repeat,
            sample_index=sample_index,
        )
        records.append(record)
        return response.text

    async def _samples(
        self,
        problem: MathProblem,
        variant: str,
        repeat: int,
        count: int,
        records: list[CallRecord],
        start_index: int = 0,
    ) -> list[str]:
        return list(
            await asyncio.gather(
                *(
                    self._generate(problem, variant, repeat, start_index + index, records)
                    for index in range(count)
                )
            )
        )

    async def _full(
        self,
        problem: MathProblem,
        variant: str,
        repeat: int,
        records: list[CallRecord],
    ) -> str:
        drafts = await self._samples(problem, variant, repeat, 3, records)

        async def critique(index: int, draft: str) -> str:
            prompt = (
                "Audit this proposed MATH solution for algebraic, logical, and domain errors. "
                f"Problem: {problem.problem}\n\nSolution: {draft}"
            )
            response, record = await self._call(
                prompt,
                variant=variant,
                component="critique",
                problem=problem,
                repeat=repeat,
                sample_index=index,
            )
            records.append(record)
            return response.text

        critiques = list(await asyncio.gather(*(critique(index, draft) for index, draft in enumerate(drafts))))

        async def revise(index: int, draft: str, feedback: str) -> str:
            prompt = (
                "Revise the solution using the audit. End with exactly one final expression in \\boxed{...}.\n\n"
                f"Problem: {problem.problem}\n\nDraft: {draft}\n\nAudit: {feedback}"
            )
            response, record = await self._call(
                prompt,
                variant=variant,
                component="revise",
                problem=problem,
                repeat=repeat,
                sample_index=index,
            )
            records.append(record)
            return response.text

        revised = list(
            await asyncio.gather(
                *(revise(index, draft, critiques[index]) for index, draft in enumerate(drafts))
            )
        )
        rendered = "\n\n".join(f"Candidate {index + 1}: {candidate}" for index, candidate in enumerate(revised))
        prompt = (
            "Choose the answer best supported by these independent audited candidates. Recheck ties and "
            "end with exactly one final expression in \\boxed{...}.\n\n"
            f"Problem: {problem.problem}\n\n{rendered}"
        )
        response, record = await self._call(
            prompt,
            variant=variant,
            component="vote",
            problem=problem,
            repeat=repeat,
            sample_index=0,
        )
        records.append(record)
        return response.text

    async def _run_system(
        self,
        name: str,
        problem: MathProblem,
        repeat: int,
        records: list[CallRecord],
    ) -> tuple[str, bool, float]:
        if name == "cot@1":
            samples = await self._samples(problem, name, repeat, 1, records)
            return samples[0], False, 0.0
        if name in {"sc@3", "sc@9", "sc@budget"}:
            count = {"sc@3": 3, "sc@9": 9, "sc@budget": self.sc_budget_n}[name]
            samples = await self._samples(problem, name, repeat, count, records)
            return _majority(samples), False, 0.0
        if name == "full":
            return await self._full(problem, name, repeat, records), False, 0.0
        if name in {"escalate_structure", "escalate_sc"}:
            initial = await self._samples(problem, name, repeat, 3, records)
            if _unanimous(initial):
                return _majority(initial), False, 0.0
            before = sum(record.usd_cost for record in records)
            if name == "escalate_structure":
                prediction = await self._full(problem, name, repeat, records)
            else:
                additional = await self._samples(
                    problem,
                    name,
                    repeat,
                    self.escalate_sc_extra_samples,
                    records,
                    start_index=3,
                )
                prediction = _majority([*initial, *additional])
            return prediction, True, sum(record.usd_cost for record in records) - before
        raise KeyError(name)

    async def _execute(self, name: str, problem: MathProblem, repeat: int) -> dict[str, Any]:
        key = (name, problem.problem_id, repeat)
        if key in self._completed:
            return self._completed[key]
        records: list[CallRecord] = []
        error: str | None = None
        escalated = False
        incremental_cost = 0.0
        try:
            prediction, escalated, incremental_cost = await self._run_system(
                name, problem, repeat, records
            )
        except BudgetStop:
            raise
        except AbsoluteBudgetExceeded:
            raise
        except Exception as exc:
            prediction = ""
            error = f"{type(exc).__name__}: {exc}"

        finish_reasons = {(record.finish_reason or "").upper() for record in records}
        if error:
            status = "failed"
        elif any(record.blocked for record in records):
            status = "blocked"
        elif "MAX_TOKENS" in finish_reasons:
            status = "truncated"
        else:
            status = "ok"
        score = score_math_answer(prediction, problem.answer) if status == "ok" else score_math_answer("", problem.answer)
        component_costs: dict[str, float] = {}
        for record in records:
            component_costs[record.component] = component_costs.get(record.component, 0.0) + record.usd_cost
        row = {
            "variant": name,
            "problem_id": problem.problem_id,
            "repeat": repeat,
            "prediction": prediction,
            "reference": problem.answer,
            "correct": score.correct,
            "scoring_method": score.method,
            "status": status,
            "error": error,
            "cost_usd": sum(record.usd_cost for record in records),
            "input_tokens": sum(record.input_tokens for record in records),
            "output_tokens": sum(record.output_tokens for record in records),
            "latency_ms": sum(record.latency_ms for record in records),
            "component_costs": component_costs,
            "problem": problem.problem,
            "level": problem.level,
            "subject": problem.subject,
            "escalated": escalated,
            "incremental_cost_usd": incremental_cost,
        }
        async with self._checkpoint_lock:
            with self.checkpoint_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            self._completed[key] = row
        return row

    async def _calibrate(self, problems: list[MathProblem]) -> None:
        calibration_problems = problems[: min(20, len(problems))]
        for problem in calibration_problems:
            for name in ("cot@1", "full", "escalate_structure"):
                await self._execute(name, problem, 0)
        rows = [
            self._completed[(name, problem.problem_id, 0)]
            for problem in calibration_problems
            for name in ("cot@1", "full", "escalate_structure")
        ]
        cot_costs = [row["cost_usd"] for row in rows if row["variant"] == "cot@1" and row["cost_usd"] > 0]
        full_costs = [row["cost_usd"] for row in rows if row["variant"] == "full" and row["cost_usd"] > 0]
        escalation_costs = [
            row["incremental_cost_usd"]
            for row in rows
            if row["variant"] == "escalate_structure" and row["escalated"] and row["incremental_cost_usd"] > 0
        ]
        cot_mean = sum(cot_costs) / len(cot_costs) if cot_costs else 0.0
        full_mean = sum(full_costs) / len(full_costs) if full_costs else 0.0
        escalation_mean = (
            sum(escalation_costs) / len(escalation_costs) if escalation_costs else full_mean
        )
        self.sc_budget_n = _nearest_sample_count(full_mean, cot_mean)
        self.escalate_sc_extra_samples = _nearest_sample_count(escalation_mean, cot_mean)
        self.calibration = {
            "n": len(calibration_problems),
            "cot_sample_mean_cost_usd": cot_mean,
            "full_mean_cost_usd": full_mean,
            "escalate_structure_mean_incremental_cost_usd": escalation_mean,
            "sc_budget_n": self.sc_budget_n,
            "escalate_sc_extra_samples": self.escalate_sc_extra_samples,
        }
        self._persist_calibration(self.calibration, source_run_id=self.config.run_id)

    def _persist_calibration(
        self,
        calibration: dict[str, Any],
        *,
        source_run_id: str,
        source_results_file: str | None = None,
    ) -> None:
        calibration_model = calibration.get("model")
        if calibration_model and calibration_model != self.provider.model:
            raise ValueError(
                f"Calibration model {calibration_model!r} does not match provider {self.provider.model!r}"
            )
        payload = {
            **calibration,
            "model": self.provider.model,
            "source_run_id": source_run_id,
        }
        if source_results_file:
            payload["source_results_file"] = source_results_file
        if self.calibration_path.exists():
            existing = json.loads(self.calibration_path.read_text(encoding="utf-8"))
            existing_model = existing.get("model")
            if not existing_model or existing_model == self.provider.model:
                return
            if self.provider.model.startswith("mock"):
                return
            if not str(existing_model).startswith("mock"):
                raise ValueError(
                    f"Refusing to replace calibration for {existing_model!r} with {self.provider.model!r}"
                )
        self.calibration_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_calibration(self) -> None:
        if self.calibration_path.exists():
            payload = json.loads(self.calibration_path.read_text(encoding="utf-8"))
        else:
            final_results_path = self.results_dir / "results_math500_final.json"
            if not final_results_path.exists():
                raise FileNotFoundError(
                    "Filtered MATH systems require results/calibration_math500.json; "
                    "run the complete MATH system matrix first"
                )
            final_results = json.loads(final_results_path.read_text(encoding="utf-8"))
            payload = dict(final_results.get("study", {}).get("calibration", {}))
            final_model = final_results.get("metadata", {}).get("model")
            if final_model:
                payload["model"] = final_model
            if final_model and final_model != self.provider.model:
                raise ValueError(
                    f"Final-results model {final_model!r} does not match provider {self.provider.model!r}"
                )
            self._persist_calibration(
                payload,
                source_run_id="recovered-math500-final",
                source_results_file=final_results_path.name,
            )
        saved_model = payload.get("model")
        if saved_model and saved_model != self.provider.model:
            raise ValueError(
                f"Saved calibration model {saved_model!r} does not match provider {self.provider.model!r}"
            )
        if "calibration" in payload:
            payload = dict(payload["calibration"])
        required = set()
        if "sc@budget" in self.systems:
            required.add("sc_budget_n")
        if "escalate_sc" in self.systems:
            required.add("escalate_sc_extra_samples")
        missing = required - set(payload)
        if missing:
            raise ValueError(f"Saved MATH calibration is missing: {', '.join(sorted(missing))}")
        if "sc_budget_n" in payload:
            self.sc_budget_n = int(payload["sc_budget_n"])
        if "escalate_sc_extra_samples" in payload:
            self.escalate_sc_extra_samples = int(payload["escalate_sc_extra_samples"])
        self.calibration = {
            key: value
            for key, value in payload.items()
            if key not in {"model", "source_run_id", "source_results_file"}
        }
        self.calibration["reused"] = True

    async def run(self, problems: list[MathProblem]) -> dict[str, Any]:
        if self.filtered_systems:
            if {"sc@budget", "escalate_sc"} & set(self.systems):
                self._load_calibration()
        else:
            await self._calibrate(problems)
        for repeat in range(self.repeats):
            for problem in problems:
                for name in self.systems:
                    await self._execute(name, problem, repeat)
        rows = [
            self._completed[(name, problem.problem_id, repeat)]
            for repeat in range(self.repeats)
            for problem in problems
            for name in self.systems
        ]
        return aggregate_math_results(
            rows,
            model=self.provider.model,
            config=self.config,
            problem_count=len(problems),
            repeats=self.repeats,
            calibration=self.calibration,
            systems=self.systems,
        )


def aggregate_math_results(
    rows: list[dict[str, Any]],
    *,
    model: str,
    config: ExperimentConfig,
    problem_count: int,
    repeats: int,
    calibration: dict[str, Any],
    systems: Sequence[str] = MATH_SYSTEMS,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "metadata": {
            "model": model,
            "temperature": config.temperature,
            "sample_size": problem_count,
            "seed": config.seed,
            "repeat_count": repeats,
            "ci_method": "Wilson 95% binomial interval",
        },
        "study": {
            "name": "math500",
            "systems": list(systems),
            "calibration": calibration,
        },
        "variants": {},
        "missingness": {},
        "scorer_breakdown": {},
    }
    for name in systems:
        selected = [row for row in rows if row["variant"] == name]
        total = len(selected)
        correct = sum(bool(row["correct"]) for row in selected)
        total_cost = sum(float(row["cost_usd"]) for row in selected)
        lower, upper = wilson_interval(correct, total)
        components: dict[str, float] = {}
        for row in selected:
            for component, cost in row.get("component_costs", {}).items():
                components[component] = components.get(component, 0.0) + float(cost)
        missing = {
            status: sum(row.get("status") == status for row in selected)
            for status in ("failed", "blocked", "truncated")
        }
        methods = {
            method: sum(row.get("scoring_method") == method for row in selected)
            for method in ("sympy_equiv", "string_match", "failed")
        }
        output["missingness"][name] = missing
        output["scorer_breakdown"][name] = methods
        output["variants"][name] = {
            "n": total,
            "correct": correct,
            "accuracy": correct / total if total else 0.0,
            "ci": {"lower": lower, "upper": upper, "level": 0.95},
            "mean_cost_usd": total_cost / total if total else 0.0,
            "cost_per_success_usd": total_cost / correct if correct else None,
            "mean_input_tokens": sum(row.get("input_tokens", 0) for row in selected) / total if total else 0.0,
            "mean_output_tokens": sum(row.get("output_tokens", 0) for row in selected) / total if total else 0.0,
            "mean_latency_ms": sum(row.get("latency_ms", 0.0) for row in selected) / total if total else 0.0,
            "per_component_cost_share": {
                component: cost / total_cost if total_cost else 0.0
                for component, cost in sorted(components.items())
            },
        }
    if "full" in output["variants"]:
        full_accuracy = output["variants"]["full"]["accuracy"]
        for item in output["variants"].values():
            item["accuracy_delta_vs_full"] = item["accuracy"] - full_accuracy

    verdict_names = ("full", "sc@budget")
    by_name = {
        name: {(str(row["problem_id"]), int(row.get("repeat", 0))): row for row in rows if row["variant"] == name}
        for name in verdict_names
    }
    shared = sorted(set(by_name["full"]) & set(by_name["sc@budget"]))
    verdict_n = len(shared)
    if verdict_n:
        full_cost = sum(by_name["full"][key]["cost_usd"] for key in shared) / verdict_n
        baseline_cost = sum(by_name["sc@budget"][key]["cost_usd"] for key in shared) / verdict_n
        full_acc = sum(bool(by_name["full"][key]["correct"]) for key in shared) / verdict_n
        baseline_acc = sum(bool(by_name["sc@budget"][key]["correct"]) for key in shared) / verdict_n
        gain = full_acc - baseline_acc
        output["verdict"] = {
            "verdict_n": verdict_n,
            "cost_matched_variant": "sc@budget",
            "full_mean_cost_usd": full_cost,
            "baseline_mean_cost_usd": baseline_cost,
            "full_accuracy": full_acc,
            "baseline_accuracy": baseline_acc,
            "gain_over_cost_matched_sc": gain,
            "gain_percentage_points": gain * 100,
        }
    else:
        output["verdict"] = {
            "verdict_n": 0,
            "cost_matched_variant": "sc@budget",
            "full_mean_cost_usd": None,
            "baseline_mean_cost_usd": None,
            "full_accuracy": None,
            "baseline_accuracy": None,
            "gain_over_cost_matched_sc": None,
            "gain_percentage_points": None,
        }
    return output
