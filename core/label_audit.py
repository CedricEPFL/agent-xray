"""Build a blinded manual label-audit sheet from experiment checkpoints."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from .math_scoring import extract_math_answer, normalize_math_string
from .scoring import extract_final_number


def _read_checkpoint(path: Path) -> list[dict[str, Any]]:
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


def _dataset_name(path: Path, row: dict[str, Any]) -> str:
    if "math500" in path.name.lower() or "level" in row or "subject" in row:
        return "math500"
    return "gsm8k"


def _problem_lookups(data_dir: Path | None) -> dict[str, dict[str, str]]:
    lookups: dict[str, dict[str, str]] = {"math500": {}, "gsm8k": {}}
    if data_dir is None:
        return lookups
    math_path = data_dir / "math500_test.jsonl"
    if math_path.exists():
        for index, line in enumerate(math_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            problem_id = str(row.get("id", index))
            lookups["math500"][problem_id] = str(row.get("problem", ""))
            if row.get("unique_id") is not None:
                lookups["math500"][str(row["unique_id"])] = str(row.get("problem", ""))
    gsm_path = data_dir / "gsm8k_test.jsonl"
    if gsm_path.exists():
        for index, line in enumerate(gsm_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            lookups["gsm8k"][str(index)] = str(row.get("question", ""))
    return lookups


def _model_answer(row: dict[str, Any], dataset: str) -> tuple[str | None, str]:
    prediction = str(row.get("prediction", ""))
    if dataset == "gsm8k":
        answer = extract_final_number(prediction)
        return answer, answer or ""
    answer = extract_math_answer(prediction)
    return answer, normalize_math_string(answer)


def _scoring_method(row: dict[str, Any], dataset: str) -> str:
    return str(
        row.get("scoring_method")
        or row.get("scorer_method")
        or ("exact_match" if dataset == "gsm8k" else "unknown")
    )


def construct_audit_sheet(
    checkpoint_paths: Sequence[str | Path],
    *,
    data_dir: str | Path | None = None,
    sample_size: int = 50,
    seed: int = 42,
) -> dict[str, Any]:
    """Construct a deterministic blinded audit sheet without writing files."""

    if not checkpoint_paths:
        raise ValueError("at least one checkpoint is required")
    if sample_size < 0:
        raise ValueError("sample_size must be non-negative")
    paths = [Path(path) for path in checkpoint_paths]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    systems_by_dataset: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        for row in _read_checkpoint(path):
            if row.get("problem_id") is None or row.get("variant") is None:
                continue
            dataset = _dataset_name(path, row)
            grouped[(dataset, str(row["problem_id"]))].append(row)
            systems_by_dataset[dataset].add(str(row["variant"]))

    lookups = _problem_lookups(Path(data_dir) if data_dir is not None else None)
    records: list[dict[str, Any]] = []
    consensus_keys: set[tuple[str, str]] = set()
    for key in sorted(grouped):
        dataset, problem_id = key
        rows = grouped[key]
        present_systems = {str(row["variant"]) for row in rows}
        answers = [_model_answer(row, dataset) for row in rows]
        normalized_answers = [normalized for _, normalized in answers]
        is_consensus = (
            len(present_systems) >= 2
            and present_systems == systems_by_dataset[dataset]
            and all(normalized_answers)
            and len(set(normalized_answers)) == 1
            and all("correct" in row and not bool(row["correct"]) for row in rows)
        )
        if is_consensus:
            consensus_keys.add(key)
        raw_answers: list[str] = []
        for raw_answer, _ in answers:
            if raw_answer and raw_answer not in raw_answers:
                raw_answers.append(raw_answer)
        methods = sorted({_scoring_method(row, dataset) for row in rows})
        embedded_problem = next(
            (
                str(row.get("problem") or row.get("question"))
                for row in rows
                if row.get("problem") or row.get("question")
            ),
            "",
        )
        gold_answer = next((str(row.get("reference")) for row in rows if row.get("reference") is not None), "")
        records.append(
            {
                "_key": key,
                "dataset": dataset,
                "problem_id": problem_id,
                "problem": embedded_problem or lookups[dataset].get(problem_id, "[problem text unavailable]"),
                "gold_answer": gold_answer,
                "consensus_answer": raw_answers[0] if is_consensus and raw_answers else None,
                "model_answers": raw_answers,
                "scoring_methods": methods,
                "selection_reason": "consensus_candidate" if is_consensus else "random_sample",
                "verdict": "",
                "notes": "",
            }
        )

    consensus_records = [record for record in records if record["_key"] in consensus_keys]
    sampling_pool = [record for record in records if record["_key"] not in consensus_keys]
    rng = random.Random(seed)
    random_records = rng.sample(sampling_pool, min(sample_size, len(sampling_pool)))
    selected = [*consensus_records, *random_records]
    rng.shuffle(selected)
    items: list[dict[str, Any]] = []
    for index, record in enumerate(selected, 1):
        item = {key: value for key, value in record.items() if key != "_key"}
        item["item_id"] = f"audit-{index:03d}"
        items.append(item)
    return {
        "metadata": {
            "instructions": (
                "Review each item without access to system identities. Set verdict to one of "
                "gold_correct, model_correct, ambiguous, or scorer_error; explain adjudications in notes."
            ),
            "seed": seed,
            "union_items": len(records),
            "consensus_candidates": len(consensus_records),
            "random_sample_requested": sample_size,
            "random_sample_selected": len(random_records),
            "audit_items": len(items),
            "checkpoint_count": len(paths),
        },
        "items": items,
    }


def render_audit_markdown(sheet: dict[str, Any]) -> str:
    metadata = sheet["metadata"]
    lines = [
        "# Agent X-Ray Manual Label Audit",
        "",
        "## Instructions",
        "",
        metadata["instructions"],
        "",
        "System identities are intentionally hidden. Do not attempt to infer them while labeling.",
        "",
        "## Counts",
        "",
        f"- Union items: {metadata['union_items']}",
        f"- Consensus candidates: {metadata['consensus_candidates']}",
        f"- Random sample: {metadata['random_sample_selected']}/{metadata['random_sample_requested']}",
        f"- Total audit items: {metadata['audit_items']}",
        "",
    ]
    for item in sheet["items"]:
        answers = "; ".join(item["model_answers"]) or "[no extractable answer]"
        lines.extend(
            [
                f"## {item['item_id']}",
                "",
                f"**Dataset:** {item['dataset']}  ",
                f"**Problem ID:** {item['problem_id']}  ",
                f"**Selection:** {item['selection_reason']}  ",
                "",
                f"**Problem:** {item['problem']}",
                "",
                f"**Gold answer:** `{item['gold_answer']}`  ",
                f"**Consensus answer:** `{item['consensus_answer'] or ''}`  ",
                f"**Model answer(s):** `{answers}`  ",
                f"**Scoring method(s):** {', '.join(item['scoring_methods'])}",
                "",
                "**Verdict:** ",
                "",
                "**Notes:** ",
                "",
            ]
        )
    return "\n".join(lines)


def write_audit_sheet(sheet: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "audit_sheet.json"
    markdown_path = output_dir / "audit_sheet.md"
    json_path.write_text(json.dumps(sheet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_audit_markdown(sheet), encoding="utf-8")
    return json_path, markdown_path


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build a blinded manual label-audit sheet")
    parser.add_argument("checkpoints", nargs="+", type=Path)
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "results")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sheet = construct_audit_sheet(
        args.checkpoints,
        data_dir=args.data_dir,
        sample_size=args.sample_size,
        seed=args.seed,
    )
    json_path, markdown_path = write_audit_sheet(sheet, args.output_dir)
    metadata = sheet["metadata"]
    print(
        f"Audit items={metadata['audit_items']} "
        f"(consensus={metadata['consensus_candidates']}, random={metadata['random_sample_selected']})"
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
