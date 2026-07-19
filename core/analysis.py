"""Paired confirmatory analysis for Agent X-Ray checkpoint rows."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Sequence


def mcnemar_exact(b: int, c: int) -> float:
    """Return the two-sided exact McNemar p-value for discordant pairs."""

    if not isinstance(b, int) or not isinstance(c, int) or b < 0 or c < 0:
        raise ValueError("b and c must be non-negative integers")
    discordant = b + c
    if discordant == 0:
        return 1.0
    lower_tail = sum(math.comb(discordant, index) for index in range(min(b, c) + 1))
    return min(1.0, 2.0 * lower_tail / (2**discordant))


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def paired_bootstrap_ci(
    items: list[tuple[bool, bool]],
    n_boot: int = 10_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap the paired item-level accuracy difference A minus B."""

    if not items:
        raise ValueError("items must not be empty")
    if n_boot <= 0:
        raise ValueError("n_boot must be positive")
    differences = [int(a_correct) - int(b_correct) for a_correct, b_correct in items]
    delta_mean = sum(differences) / len(differences)
    rng = random.Random(seed)
    bootstrap_deltas = sorted(
        sum(differences[rng.randrange(len(differences))] for _ in differences)
        / len(differences)
        for _ in range(n_boot)
    )
    return (
        delta_mean,
        _percentile(bootstrap_deltas, 0.025),
        _percentile(bootstrap_deltas, 0.975),
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path.name} line {line_number}") from exc
    return rows


def _level_number(value: object) -> int | None:
    match = re.search(r"\d+", str(value)) if value is not None else None
    return int(match.group()) if match else None


def _scoring_method(row: dict[str, Any]) -> str | None:
    return row.get("scoring_method") or row.get("scorer_method")


def primary_contrast(
    results_dir: str | Path,
    run_id: str,
    system_a: str = "full",
    system_b: str = "sc@budget",
    stratum_levels: set[int] | frozenset[int] = frozenset({4, 5}),
    repeat: int = 0,
    escalated_only: bool = False,
) -> dict[str, Any]:
    """Compute the preregistered paired contrast from one checkpoint."""

    if not run_id or Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("run_id must be a filename-safe identifier")
    levels = {int(level) for level in stratum_levels}
    checkpoint_path = Path(results_dir) / f"checkpoint_{run_id}.jsonl"
    rows = [
        row
        for row in _read_jsonl(checkpoint_path)
        if int(row.get("repeat", 0)) == repeat
        and _level_number(row.get("level")) in levels
    ]

    eligible_ids = {str(row["problem_id"]) for row in rows if row.get("problem_id") is not None}
    by_system: dict[str, dict[str, dict[str, Any]]] = {system_a: {}, system_b: {}}
    for row in rows:
        variant = row.get("variant")
        problem_id = row.get("problem_id")
        if variant in by_system and problem_id is not None:
            # Checkpoint keys are unique; using the last row makes recovery
            # deterministic if a manually repaired checkpoint contains a duplicate.
            by_system[variant][str(problem_id)] = row

    ids_a = set(by_system[system_a])
    ids_b = set(by_system[system_b])
    all_paired_ids = sorted(ids_a & ids_b)
    paired_ids = [
        problem_id
        for problem_id in all_paired_ids
        if not escalated_only
        or bool(by_system[system_a][problem_id].get("escalated", False))
        or bool(by_system[system_b][problem_id].get("escalated", False))
    ]
    both_failed_ids = [
        problem_id
        for problem_id in paired_ids
        if _scoring_method(by_system[system_a][problem_id]) == "failed"
        and _scoring_method(by_system[system_b][problem_id]) == "failed"
    ]
    excluded = set(both_failed_ids)
    analysis_ids = [problem_id for problem_id in paired_ids if problem_id not in excluded]
    items = [
        (
            bool(by_system[system_a][problem_id].get("correct", False)),
            bool(by_system[system_b][problem_id].get("correct", False)),
        )
        for problem_id in analysis_ids
    ]
    b = sum(a_correct and not b_correct for a_correct, b_correct in items)
    c = sum(not a_correct and b_correct for a_correct, b_correct in items)

    missingness = {
        "eligible_problem_ids": len(eligible_ids),
        "paired_before_exclusions": len(paired_ids),
        "system_a_missing": len(eligible_ids - ids_a),
        "system_b_missing": len(eligible_ids - ids_b),
        "unpaired": len(eligible_ids - (ids_a & ids_b)),
        "system_a_scorer_failed": sum(
            _scoring_method(by_system[system_a][problem_id]) == "failed"
            for problem_id in paired_ids
        ),
        "system_b_scorer_failed": sum(
            _scoring_method(by_system[system_b][problem_id]) == "failed"
            for problem_id in paired_ids
        ),
    }
    if escalated_only:
        missingness["paired_before_escalation_filter"] = len(all_paired_ids)
        missingness["not_escalated"] = len(all_paired_ids) - len(paired_ids)
    result: dict[str, Any] = {
        "run_id": run_id,
        "system_a": system_a,
        "system_b": system_b,
        "stratum_levels": sorted(levels),
        "repeat": repeat,
        "escalated_only": escalated_only,
        "n_pairs": len(items),
        "acc_a": sum(item[0] for item in items) / len(items) if items else None,
        "acc_b": sum(item[1] for item in items) / len(items) if items else None,
        "delta": None,
        "discordant": {"b": b, "c": c},
        "discordant_b": b,
        "discordant_c": c,
        "mcnemar_p": mcnemar_exact(b, c) if items else None,
        "bootstrap_ci": {"lower": None, "upper": None, "level": 0.95, "n_boot": 10_000},
        "exclusions": len(excluded),
        "exclusion_reasons": {"both_scorers_failed": len(excluded)},
        "missingness": missingness,
    }
    if items:
        delta, ci_low, ci_high = paired_bootstrap_ci(items)
        result["delta"] = delta
        result["bootstrap_ci"].update({"lower": ci_low, "upper": ci_high})
    return result


def _parse_levels(value: str) -> set[int]:
    try:
        levels = {int(part.strip()) for part in value.split(",") if part.strip()}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("levels must be comma-separated integers") from exc
    if not levels:
        raise argparse.ArgumentTypeError("at least one level is required")
    return levels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a paired MATH checkpoint contrast")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--system-a", default="full")
    parser.add_argument("--system-b", default="sc@budget")
    parser.add_argument("--levels", type=_parse_levels, default={4, 5})
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument(
        "--escalated-only",
        action="store_true",
        help="restrict to pairs where either system row escalated",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results",
        help=argparse.SUPPRESS,
    )
    return parser


def _compact_report(result: dict[str, Any]) -> str:
    ci = result["bootstrap_ci"]
    if result["n_pairs"]:
        metrics = (
            f"A={result['acc_a']:.3f}, B={result['acc_b']:.3f}, "
            f"delta={result['delta']:+.3f}, 95% bootstrap CI=[{ci['lower']:+.3f}, {ci['upper']:+.3f}]"
        )
        test = (
            f"McNemar b/c={result['discordant_b']}/{result['discordant_c']}, "
            f"exact p={result['mcnemar_p']:.6g}"
        )
    else:
        metrics = "No analyzable pairs"
        test = "McNemar and bootstrap unavailable"
    slice_label = "; escalated-only" if result.get("escalated_only") else ""
    return "\n".join(
        (
            f"Primary contrast: {result['system_a']} - {result['system_b']}",
            f"Levels={','.join(map(str, result['stratum_levels']))}; repeat={result['repeat']}"
            f"{slice_label}; n={result['n_pairs']}",
            metrics,
            test,
            f"Exclusions (both scorers failed)={result['exclusions']}; unpaired={result['missingness']['unpaired']}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = primary_contrast(
        args.results_dir,
        args.run_id,
        system_a=args.system_a,
        system_b=args.system_b,
        stratum_levels=args.levels,
        repeat=args.repeat,
        escalated_only=args.escalated_only,
    )
    args.results_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.results_dir / f"analysis_{args.run_id}.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(_compact_report(result))
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
