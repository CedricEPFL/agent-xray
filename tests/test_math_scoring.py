import pytest

from core.math_scoring import extract_math_answer, score_math_answer


def test_extract_math_answer_handles_nested_box():
    assert extract_math_answer(r"Reasoning. \boxed{\frac{1}{2}}") == r"\frac{1}{2}"
    assert extract_math_answer(r"The majority-supported final answer is \frac{1}{2}.") == r"\frac{1}{2}"


@pytest.mark.parametrize(
    ("prediction", "reference"),
    [
        (r"2\sqrt{3}", r"\sqrt{12}"),
        (r"\dfrac{3}{4}", r"\frac{3}{4}"),
        (r"5x^2", r"5x^{2}"),
        ("50%", "50"),
        ("5", "5"),
        ("0.5", r"\frac{1}{2}"),
        ("1.250", "1.25"),
    ],
)
def test_sympy_equivalent_answer_styles(prediction, reference):
    score = score_math_answer(prediction, reference)
    assert score.correct
    assert score.method == "sympy_equiv"


def test_percentage_semantics_are_configurable():
    dataset_style = score_math_answer("50%", "50")
    arithmetic_style = score_math_answer("50%", "50", percent_as_fraction=True)
    assert dataset_style.correct
    assert not arithmetic_style.correct
    assert arithmetic_style.method == "sympy_equiv"


@pytest.mark.parametrize(
    ("prediction", "reference"),
    [
        (r"\left(2\,\pi\right)", r"2\cdot\pi"),
        ("−3", "-3"),
        (r"30^{\circ}", "30°"),
        (r"50\%", "50"),
        (r"\frac{1}{\sqrt{4}}", r"\frac{1}{2}"),
    ],
)
def test_latex_preprocessing_conventions(prediction, reference):
    score = score_math_answer(prediction, reference)
    assert score.correct
    assert score.method == "sympy_equiv"


@pytest.mark.parametrize(
    ("prediction", "reference"),
    [("5", "6"), ("x+1", "x+2")],
)
def test_clearly_different_expressions_stay_incorrect(prediction, reference):
    score = score_math_answer(prediction, reference)
    assert not score.correct
    assert score.method == "sympy_equiv"


@pytest.mark.parametrize(
    ("prediction", "reference", "correct"),
    [
        ("(1,2)", r"\left(1, 2\right)", True),
        ("(1,2)", "(2,1)", False),
        (r"[0, \infty)", r"[0,\infty)", True),
    ],
)
def test_structured_answers_compare_element_wise(prediction, reference, correct):
    score = score_math_answer(prediction, reference)
    assert score.correct is correct
    assert score.method == "sympy_equiv"


def test_string_fallback_and_failed_methods_are_recorded():
    matched = score_math_answer(r"Final answer: \boxed{[1,2]}", "[1,2]")
    assert matched.correct
    assert matched.method == "sympy_equiv"

    one_sided_parse = score_math_answer("5", "[5]")
    assert not one_sided_parse.correct
    assert one_sided_parse.method == "failed"

    failed = score_math_answer("", r"\frac{1}{2}")
    assert not failed.correct
    assert failed.method == "failed"
