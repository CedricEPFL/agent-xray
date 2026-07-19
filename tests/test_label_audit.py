import json
from pathlib import Path

from core.label_audit import construct_audit_sheet, render_audit_markdown, write_audit_sheet


TEST_DIR = Path(__file__).parent


def _row(variant, problem_id, prediction, *, reference, correct, problem, math=True):
    row = {
        "variant": variant,
        "problem_id": problem_id,
        "prediction": prediction,
        "reference": reference,
        "correct": correct,
        "problem": problem,
        "scoring_method": "sympy_equiv" if math else "exact_match",
    }
    if math:
        row["level"] = 4
    return row


def _write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_audit_sheet_combines_consensus_and_random_sample_without_system_identities():
    math_checkpoint = TEST_DIR / "checkpoint__audit_math500.jsonl"
    gsm_checkpoint = TEST_DIR / "checkpoint__audit_gsm8k.jsonl"
    output_json = TEST_DIR / "audit_sheet.json"
    output_md = TEST_DIR / "audit_sheet.md"
    artifacts = [math_checkpoint, gsm_checkpoint, output_json, output_md]
    for path in artifacts:
        path.unlink(missing_ok=True)
    _write(
        math_checkpoint,
        [
            _row("full", "consensus", r"Final answer: \boxed{7}", reference="8", correct=False, problem="Compute q."),
            _row("sc@budget", "consensus", r"Thus \boxed{7}", reference="8", correct=False, problem="Compute q."),
            _row("full", "disagree", r"\boxed{2}", reference="2", correct=True, problem="Compute r."),
            _row("sc@budget", "disagree", r"\boxed{3}", reference="2", correct=False, problem="Compute r."),
        ],
    )
    _write(
        gsm_checkpoint,
        [
            _row("full", "gsm-one", "Final answer: 4", reference="4", correct=True, problem="Count items.", math=False),
            _row("cot@1", "gsm-one", "Final answer: 4", reference="4", correct=True, problem="Count items.", math=False),
        ],
    )
    try:
        sheet = construct_audit_sheet(
            [math_checkpoint, gsm_checkpoint], sample_size=2, seed=42
        )
        assert sheet["metadata"]["union_items"] == 3
        assert sheet["metadata"]["consensus_candidates"] == 1
        assert sheet["metadata"]["random_sample_selected"] == 2
        assert len(sheet["items"]) == 3
        assert sum(item["selection_reason"] == "consensus_candidate" for item in sheet["items"]) == 1
        assert all(item["verdict"] == "" and item["notes"] == "" for item in sheet["items"])
        blinded_items = json.dumps(sheet["items"])
        assert '"variant"' not in blinded_items
        assert '"system"' not in blinded_items
        assert "sc@budget" not in blinded_items
        assert '"full"' not in blinded_items
        repeated = construct_audit_sheet(
            [math_checkpoint, gsm_checkpoint], sample_size=2, seed=42
        )
        assert repeated == sheet

        written_json, written_md = write_audit_sheet(sheet, TEST_DIR)
        assert written_json == output_json and written_md == output_md
        markdown = render_audit_markdown(sheet)
        assert "Consensus candidates: 1" in markdown
        assert "**Verdict:** " in markdown and "**Notes:** " in markdown
    finally:
        for path in artifacts:
            path.unlink(missing_ok=True)
