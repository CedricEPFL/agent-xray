"""Machine-readable and Markdown experiment reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


VARIANT_ORDER = ("full", "-critique", "-revise", "-vote", "cot@1", "sc@3", "sc@5")
MATH_SYSTEM_ORDER = ("cot@1", "sc@3", "sc@9", "sc@budget", "full", "escalate_structure", "escalate_sc")


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.6f}"


def render_report(results: Mapping[str, Any]) -> str:
    metadata = results["metadata"]
    variants = results["variants"]
    verdict = results["verdict"]
    study = results.get("study", "gsm8k")
    study_name = study.get("name") if isinstance(study, Mapping) else study
    is_math = study_name == "math500"
    variant_order = MATH_SYSTEM_ORDER if is_math else VARIANT_ORDER
    requested_n = metadata.get("requested_sample_size", metadata["sample_size"])
    completed_n = metadata.get("completed_sample_size", metadata["sample_size"])
    partial_run = bool(metadata.get("partial_run", False))
    if partial_run:
        sample_line = (
            f"Sample: n={completed_n}/{requested_n} problems "
            f"(PARTIAL RUN — free-tier quota interrupted), seed={metadata['seed']}, one repeat per variant  "
        )
    else:
        sample_line = f"Sample: n={metadata['sample_size']}, seed={metadata['seed']}, one repeat per variant  "
    lines: list[str] = []
    if str(metadata["model"]).startswith("mock"):
        lines.extend(
            [
                "> ⚠️ SYNTHETIC MOCK DATA — illustrates the pipeline; numbers are simulated, NOT empirical.",
                "",
            ]
        )
    lines.extend([
        "# Agent X-Ray Experiment Report",
        "",
        f"Model: `{metadata['model']}`  ",
        sample_line,
        f"Sampling temperature: {metadata['temperature']}",
    ])
    if "checkpoint_rows" in metadata:
        lines.append(f"Checkpoint rows: {metadata['checkpoint_rows']}")
    lines.extend([
        "",
        "## Results",
        "",
        "| Variant | Accuracy (95% Wilson CI) | Mean cost/problem | Cost/success |",
        "|---|---:|---:|---:|",
    ])
    for name in variant_order:
        item = variants[name]
        ci = item["ci"]
        lines.append(
            f"| {name} | {item['accuracy']:.1%} ({ci['lower']:.1%}–{ci['upper']:.1%}) "
            f"| {_money(item['mean_cost_usd'])} | {_money(item['cost_per_success_usd'])} |"
        )

    if not is_math:
        lines.extend(
            [
                "",
                "## Ablation attribution",
                "",
                "| Removed component | Accuracy | Delta vs. full | Mean cost saved/problem |",
                "|---|---:|---:|---:|",
            ]
        )
        full_cost = variants["full"]["mean_cost_usd"]
        for name in ("-critique", "-revise", "-vote"):
            item = variants[name]
            lines.append(
                f"| {name.removeprefix('-')} | {item['accuracy']:.1%} | "
                f"{item['accuracy_delta_vs_full'] * 100:+.1f} pp | "
                f"{_money(full_cost - item['mean_cost_usd'])} |"
            )

    lines.extend(["", "## Component cost attribution", ""])
    for name in variant_order:
        shares = variants[name]["per_component_cost_share"]
        rendered = ", ".join(f"{component} {share:.1%}" for component, share in shares.items())
        lines.append(f"- **{name}:** {rendered or 'no calls'}")

    if is_math:
        calibration = study.get("calibration", {})
        lines.extend(
            [
                "",
                "## Study v2 calibration",
                "",
                f"Calibration slice: n={calibration.get('n', 0)}; SC@budget fixed at "
                f"N={calibration.get('sc_budget_n', 'n/a')}; escalation SC adds "
                f"N={calibration.get('escalate_sc_extra_samples', 'n/a')} samples on disagreement.",
                "",
                "## Missingness",
                "",
                "| System | Failed | Blocked | Truncated |",
                "|---|---:|---:|---:|",
            ]
        )
        for name in variant_order:
            missing = results.get("missingness", {}).get(name, {})
            lines.append(
                f"| {name} | {missing.get('failed', 0)} | {missing.get('blocked', 0)} | "
                f"{missing.get('truncated', 0)} |"
            )
        lines.extend(["", "## Scorer validity", ""])
        for name in variant_order:
            methods = results.get("scorer_breakdown", {}).get(name, {})
            lines.append(
                f"- **{name}:** sympy_equiv {methods.get('sympy_equiv', 0)}, "
                f"string_match {methods.get('string_match', 0)}, failed {methods.get('failed', 0)}"
            )

    lines.extend(["", "## Verdict", ""])
    if verdict["verdict_n"]:
        direction = "gain" if verdict["gain_percentage_points"] >= 0 else "loss"
        lines.extend(
            [
                (
                    f"The verdict uses **n={verdict['verdict_n']} shared item-repeats** completed by full and "
                    f"{verdict['cost_matched_variant']}."
                    if is_math
                    else f"The verdict uses **n={verdict['verdict_n']} shared problems** completed by full, "
                    "CoT@1, SC@3, and SC@5."
                ),
                "",
                f"The measured cost-matched self-consistency baseline is **{verdict['cost_matched_variant']}** "
                f"({_money(verdict['baseline_mean_cost_usd'])} per problem versus "
                f"{_money(verdict['full_mean_cost_usd'])} for the full workflow).",
                "",
                f"The full workflow shows a **{abs(verdict['gain_percentage_points']):.1f} percentage-point {direction}** "
                "over that baseline.",
            ]
        )
    else:
        lines.append("No verdict is available because the verdict systems have no shared completed items.")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            (
                "MATH-500 v2 reports item-repeat Wilson intervals and operational missingness; paired confirmatory "
                "inference is performed downstream. Mock runs use deterministic synthetic MATH-style fixtures."
                if is_math
                else "This v1 uses one repeat per variant. Confidence intervals reflect only n-problem binomial "
                "uncertainty, not model-run variance. Mock runs use deterministic offline GSM-style fixtures "
                "and simulated model behavior; only `--live` results are empirical GSM8K measurements."
            ),
            (
                "Agreement-gated arms include their initial SC@3 cost; escalate_sc matches the calibrated mean "
                "incremental structure cost with an integer number of additional samples."
                if is_math
                else "The `-vote` ablation removes the vote call and reduces sampling from three candidates to one, "
                "so its delta measures the combined sampling-and-vote block rather than the vote operator alone."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(results: Mapping[str, Any], results_dir: Path) -> tuple[Path, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "results.json"
    report_path = results_dir / "REPORT.md"
    json_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_report(results), encoding="utf-8")
    return json_path, report_path
