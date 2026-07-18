"""Command-line entry point for Agent X-Ray."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .budget import BudgetGuard, BudgetStop
from .experiment import Experiment, ExperimentConfig, aggregate_checkpoint
from .gsm8k import load_gsm8k
from .math500 import load_math500
from .providers import GeminiProvider, MockProvider
from .report import write_reports
from .study_v2 import MathStudyExperiment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an Agent X-Ray experiment")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="run deterministic offline simulation")
    mode.add_argument("--live", action="store_true", help="run Gemini on the selected cached/downloaded study")
    parser.add_argument("--n", type=int, default=50, help="number of fixed-seed problems (default: 50)")
    parser.add_argument("--seed", type=int, default=42, help="sampling/mock seed (default: 42)")
    parser.add_argument("--study", choices=("gsm8k", "math500"), default="gsm8k")
    parser.add_argument("--concurrency", type=int, default=8, help="maximum concurrent provider calls (default: 8)")
    parser.add_argument("--repeats", type=int, default=1, help="stochastic repeats per item (default: 1)")
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="aggregate the existing checkpoint without credentials, network, or model calls",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="seconds between successful calls (default: 0 mock, 4 live)",
    )
    return parser


def run_aggregate_only(
    *,
    results_dir: Path,
    is_mock: bool,
    n: int,
    seed: int,
) -> tuple[dict, Path, Path]:
    """Aggregate and report a checkpoint without constructing an LLM provider."""

    mode = "mock" if is_mock else "live"
    config = ExperimentConfig(
        sleep_seconds=0,
        seed=seed,
        run_id=f"{mode}_n{n}_seed{seed}",
    )
    model = MockProvider.model if is_mock else GeminiProvider.model
    results = aggregate_checkpoint(
        results_dir=results_dir,
        config=config,
        model=model,
        requested_n=n,
    )
    json_path, report_path = write_reports(results, results_dir)
    return results, json_path, report_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    is_mock = bool(args.mock)
    if args.aggregate_only:
        if args.study != "gsm8k":
            raise SystemExit("--aggregate-only currently targets the GSM8K pilot checkpoint")
        _, json_path, report_path = run_aggregate_only(
            results_dir=root / "results",
            is_mock=is_mock,
            n=args.n,
            seed=args.seed,
        )
        print(f"Wrote {json_path}")
        print(f"Wrote {report_path}")
        return 0

    if args.study == "math500":
        provider = (
            MockProvider(seed=args.seed, model="mock-math500")
            if is_mock
            else GeminiProvider()
        )
        sleep_seconds = args.sleep if args.sleep is not None else 0.0
        problems = load_math500(
            n=args.n,
            seed=args.seed,
            data_dir=root / "data",
            offline_mock=is_mock,
        )
        mode = "mock" if is_mock else "live"
        config = ExperimentConfig(
            sleep_seconds=sleep_seconds,
            seed=args.seed,
            run_id=f"{mode}_math500_n{args.n}_seed{args.seed}_r{args.repeats}",
        )
        guard = None if is_mock else BudgetGuard(root / "results")
        study = MathStudyExperiment(
            provider,
            root / "results",
            config,
            concurrency=args.concurrency,
            repeats=args.repeats,
            budget_guard=guard,
        )
        try:
            results = asyncio.run(study.run(problems))
        except BudgetStop as exc:
            print(str(exc))
            return BudgetStop.exit_code
        json_path, report_path = write_reports(results, root / "results")
        print(f"Wrote {json_path}")
        print(f"Wrote {report_path}")
        return 0

    provider = MockProvider(seed=args.seed) if is_mock else GeminiProvider()
    sleep_seconds = args.sleep if args.sleep is not None else (0.0 if is_mock else 4.0)
    problems = load_gsm8k(
        n=args.n,
        seed=args.seed,
        data_dir=root / "data",
        offline_mock=is_mock,
    )
    config = ExperimentConfig(
        sleep_seconds=sleep_seconds,
        seed=args.seed,
        run_id=(
            f"{'mock' if is_mock else 'live'}_n{args.n}_seed{args.seed}"
            + (f"_r{args.repeats}" if args.repeats != 1 else "")
        ),
        repeats=args.repeats,
    )
    guard = None if is_mock else BudgetGuard(root / "results")
    try:
        results = Experiment(
            provider,
            root / "results",
            config,
            budget_guard=guard,
        ).run(problems)
    except BudgetStop as exc:
        print(str(exc))
        return BudgetStop.exit_code
    json_path, report_path = write_reports(results, root / "results")
    print(f"Wrote {json_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
