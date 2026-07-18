from core.report import render_report


def _results(model: str):
    names = ("full", "-critique", "-revise", "-vote", "cot@1", "sc@3", "sc@5")
    variants = {
        name: {
            "accuracy": 0.5,
            "accuracy_delta_vs_full": 0.0,
            "ci": {"lower": 0.3, "upper": 0.7},
            "mean_cost_usd": 0.001,
            "cost_per_success_usd": 0.002,
            "per_component_cost_share": {"generate": 1.0},
        }
        for name in names
    }
    return {
        "metadata": {"model": model, "sample_size": 10, "seed": 42, "temperature": 0.7},
        "variants": variants,
        "verdict": {
            "verdict_n": 10,
            "cost_matched_variant": "sc@5",
            "baseline_mean_cost_usd": 0.001,
            "full_mean_cost_usd": 0.001,
            "gain_percentage_points": 0.0,
        },
    }


def test_mock_report_starts_with_synthetic_banner():
    report = render_report(_results("mock-gsm8k"))
    assert report.startswith(
        "> ⚠️ SYNTHETIC MOCK DATA — illustrates the pipeline; numbers are simulated, NOT empirical."
    )
    assert "sampling from three candidates to one" in report
    assert "n=10 shared problems" in report


def test_live_report_does_not_show_mock_banner():
    report = render_report(_results("gemini-3.1-flash-lite"))
    assert report.startswith("# Agent X-Ray Experiment Report")
    assert "sampling from three candidates to one" in report
