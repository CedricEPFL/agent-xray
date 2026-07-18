import json
from pathlib import Path

import pytest

from core.analysis import main, mcnemar_exact, paired_bootstrap_ci, primary_contrast


TEST_DIR = Path(__file__).parent


def _row(variant, problem_id, *, level, correct, method="sympy_equiv", repeat=0):
    return {
        "variant": variant,
        "problem_id": problem_id,
        "repeat": repeat,
        "level": level,
        "correct": correct,
        "scoring_method": method,
    }


def _write_checkpoint(results_dir, run_id, rows):
    path = results_dir / f"checkpoint_{run_id}.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_mcnemar_exact_known_case():
    assert mcnemar_exact(8, 2) == pytest.approx(0.109375)
    assert mcnemar_exact(0, 0) == 1.0


def test_paired_bootstrap_preserves_pairing_and_delta_sign():
    items = [(True, False)] * 7 + [(False, True)] * 2 + [(True, True)]
    delta, low, high = paired_bootstrap_ci(items, n_boot=2_000, seed=7)
    assert delta == pytest.approx(0.5)
    assert low <= delta <= high
    assert high > 0
    assert paired_bootstrap_ci(items, n_boot=2_000, seed=7) == (delta, low, high)


def test_primary_contrast_filters_stratum_and_counts_exclusions_and_missingness():
    rows = [
        _row("full", "p1", level=4, correct=True),
        _row("sc@budget", "p1", level=4, correct=False),
        _row("full", "p2", level="Level 5", correct=False),
        _row("sc@budget", "p2", level="Level 5", correct=True),
        _row("full", "outside", level=3, correct=True),
        _row("sc@budget", "outside", level=3, correct=False),
        _row("full", "excluded", level=4, correct=False, method="failed"),
        _row("sc@budget", "excluded", level=4, correct=False, method="failed"),
        _row("full", "missing-b", level=5, correct=True),
        _row("full", "other-repeat", level=4, correct=True, repeat=1),
        _row("sc@budget", "other-repeat", level=4, correct=False, repeat=1),
    ]
    checkpoint = _write_checkpoint(TEST_DIR, "_analysis_synthetic", rows)
    try:
        result = primary_contrast(TEST_DIR, "_analysis_synthetic")

        assert result["n_pairs"] == 2
        assert result["acc_a"] == result["acc_b"] == 0.5
        assert result["delta"] == 0.0
        assert result["discordant"] == {"b": 1, "c": 1}
        assert result["exclusions"] == 1
        assert result["missingness"] == {
            "eligible_problem_ids": 4,
            "paired_before_exclusions": 3,
            "system_a_missing": 0,
            "system_b_missing": 1,
            "unpaired": 1,
            "system_a_scorer_failed": 1,
            "system_b_scorer_failed": 1,
        }
    finally:
        checkpoint.unlink(missing_ok=True)


def test_analysis_cli_writes_json(capsys):
    checkpoint = _write_checkpoint(
        TEST_DIR,
        "cli-test",
        [
            _row("full", "p1", level=4, correct=True),
            _row("sc@budget", "p1", level=4, correct=False),
        ],
    )
    output_path = TEST_DIR / "analysis_cli-test.json"
    try:
        assert main(["--run-id", "cli-test", "--results-dir", str(TEST_DIR)]) == 0
        output = json.loads(output_path.read_text(encoding="utf-8"))
        assert output["n_pairs"] == 1
        assert output["discordant"] == {"b": 1, "c": 0}
        assert "Primary contrast: full - sc@budget" in capsys.readouterr().out
    finally:
        checkpoint.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
