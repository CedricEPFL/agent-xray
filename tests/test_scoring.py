import pytest

from core.scoring import exact_match, extract_final_number, wilson_interval


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("After checking, the final answer is -17.", "-17"),
        ("Revenue is $1,234.50 in total.", "1234.5"),
        ("Reasoning used 2 and 8. #### 16", "16"),
        ("We get 30 widgets, so the answer is $30 dollars.", "30"),
        ("Intermediate 5; ultimately \\boxed{-1,005}", "-1005"),
        ("No numeric answer here", None),
    ],
)
def test_extract_final_number_edges(text, expected):
    assert extract_final_number(text) == expected


def test_exact_match_normalizes_formatting():
    assert exact_match("Final answer: $1,200.00", "#### 1200")
    assert not exact_match("Final answer: -3", "#### 3")


def test_wilson_interval_contains_observed_rate():
    lower, upper = wilson_interval(40, 50)
    assert lower < 0.8 < upper
    assert wilson_interval(0, 0) == (0.0, 0.0)
