"""MATH answer extraction and symbolic-equivalence scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MathScore:
    correct: bool
    method: str
    prediction: str | None
    reference: str | None


def _balanced_box(text: str) -> str | None:
    marker = r"\boxed{"
    start = text.rfind(marker)
    if start < 0:
        return None
    index = start + len(marker)
    depth = 1
    for end in range(index, len(text)):
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0:
                return text[index:end]
    return None


def extract_math_answer(text: str) -> str | None:
    """Extract a final expression without assuming that it is numeric."""

    if not text:
        return None
    boxed = _balanced_box(text)
    if boxed is not None:
        return boxed.strip()
    if "####" in text:
        return text.rsplit("####", 1)[1].strip().rstrip(". ") or None
    matches = list(
        re.finditer(
            r"(?:final\s+answer(?:\s+is)?|answer\s+is)\s*[:=]?\s*",
            text,
            re.IGNORECASE,
        )
    )
    if matches:
        answer = text[matches[-1].end() :].splitlines()[0].strip().rstrip(". ")
        return answer or None
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    return nonempty[-1].rstrip(". ") if nonempty else None


def _read_braced(value: str, start: int) -> tuple[str, int] | None:
    """Read a balanced braced group, returning its contents and next index."""

    if start >= len(value) or value[start] != "{":
        return None
    depth = 1
    for index in range(start + 1, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[start + 1 : index], index + 1
    return None


def _replace_group_command(
    value: str,
    command: str,
    group_count: int,
    render,
) -> str:
    """Replace LaTeX commands whose arguments are balanced braced groups."""

    pieces: list[str] = []
    cursor = 0
    while True:
        found = value.find(command, cursor)
        if found < 0:
            pieces.append(value[cursor:])
            return "".join(pieces)
        pieces.append(value[cursor:found])
        group_start = found + len(command)
        groups: list[str] = []
        for _ in range(group_count):
            while group_start < len(value) and value[group_start].isspace():
                group_start += 1
            parsed = _read_braced(value, group_start)
            if parsed is None:
                break
            group, group_start = parsed
            groups.append(group)
        if len(groups) != group_count:
            pieces.append(command)
            cursor = found + len(command)
            continue
        pieces.append(render(*groups))
        cursor = group_start


def _replace_latex_groups(value: str) -> str:
    previous = None
    while previous != value:
        previous = value
        value = _replace_group_command(
            value,
            r"\frac",
            2,
            lambda numerator, denominator: f"(({numerator})/({denominator}))",
        )
        value = _replace_group_command(
            value,
            r"\sqrt",
            1,
            lambda radicand: f"sqrt({radicand})",
        )
    return value


def preprocess_latex(value: str, *, percent_as_fraction: bool = False) -> str:
    """Convert common MATH answer LaTeX into a form SymPy can parse.

    MATH-500 answers sometimes use ``%`` as a presentation/unit marker.  The
    default therefore compares ``50%`` with ``50`` as equivalent.  Set
    ``percent_as_fraction=True`` to give percent its arithmetic meaning and
    convert postfix percentages to division by 100 instead.
    """

    normalized = value.strip().lower()
    normalized = normalized.translate(str.maketrans({"−": "-", "–": "-", "—": "-"}))
    normalized = normalized.replace("×", "*").replace("·", "*")
    normalized = normalized.replace("$", "")
    normalized = normalized.replace(r"\(", "").replace(r"\)", "")
    normalized = normalized.replace(r"\[", "").replace(r"\]", "")
    normalized = normalized.replace(r"\left", "").replace(r"\right", "")
    normalized = normalized.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    for spacing in (r"\,", r"\!", r"\:", r"\;", r"\quad", r"\qquad"):
        normalized = normalized.replace(spacing, "")
    normalized = normalized.replace(r"\cdot", "*").replace(r"\times", "*")
    normalized = normalized.replace(r"\pi", "pi")
    normalized = normalized.replace(r"\infty", "oo").replace("∞", "oo")
    normalized = re.sub(r"\^{?\\circ}?", "", normalized)
    normalized = normalized.replace(r"\circ", "").replace("°", "")
    normalized = normalized.replace(r"\%", "%")
    normalized = re.sub(r"\\text\{([^{}]*)\}", r"\1", normalized)
    normalized = _replace_latex_groups(normalized)
    normalized = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", normalized)
    normalized = normalized.replace("{", "(").replace("}", ")")
    normalized = re.sub(r"\s+", "", normalized)
    if percent_as_fraction:
        # Parenthesized groups and ordinary scalar atoms cover MATH answer
        # conventions without attempting to implement a full TeX grammar.
        percent_atom = r"(\([^()]+\)|(?:\d+(?:\.\d*)?|\.\d+|[a-z][a-z0-9_]*))%"
        previous = None
        while previous != normalized:
            previous = normalized
            normalized = re.sub(percent_atom, r"(\1/100)", normalized)
        normalized = normalized.replace("%", "/100")
    else:
        normalized = normalized.replace("%", "")
    return normalized.rstrip(". ")


def normalize_math_string(value: str | None, *, percent_as_fraction: bool = False) -> str:
    if value is None:
        return ""
    return preprocess_latex(value, percent_as_fraction=percent_as_fraction)


def _parse_expression(value: str, *, percent_as_fraction: bool):
    import sympy
    from sympy.parsing.sympy_parser import (
        convert_xor,
        implicit_multiplication_application,
        parse_expr,
        standard_transformations,
    )

    normalized = preprocess_latex(value, percent_as_fraction=percent_as_fraction)
    if not normalized:
        raise ValueError("empty expression")
    if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", normalized):
        normalized = normalized.replace(",", "")
    transformations = standard_transformations + (
        implicit_multiplication_application,
        convert_xor,
    )

    def parse(part: str):
        parsed = parse_expr(
            part,
            local_dict={"sqrt": sympy.sqrt, "pi": sympy.pi, "oo": sympy.oo},
            transformations=transformations,
            evaluate=True,
        )
        if not isinstance(parsed, sympy.Expr):
            raise ValueError("parsed answer is not a scalar expression")
        return parsed

    if normalized.count("=") == 1:
        left, right = normalized.split("=", 1)
        return parse(left) - parse(right)
    return parse(normalized)


def _try_parse(value: str, *, percent_as_fraction: bool):
    try:
        return _parse_expression(value, percent_as_fraction=percent_as_fraction)
    except Exception:
        return None


def _split_top_level_commas(value: str) -> list[str] | None:
    elements: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character in "([{":
            depth += 1
        elif character in ")]}" and depth:
            depth -= 1
        elif character == "," and depth == 0:
            elements.append(value[start:index])
            start = index + 1
    if not elements:
        return None
    elements.append(value[start:])
    return elements if all(elements) else None


def _structured_answer(
    value: str,
    *,
    percent_as_fraction: bool,
) -> tuple[str, str, list[str]] | None:
    """Return visible delimiters and normalized elements for a tuple/interval/set."""

    visible = value.strip().replace("$", "")
    if visible.startswith(r"\(") and visible.endswith(r"\)"):
        visible = visible[2:-2].strip()
    visible = visible.replace(r"\left", "").replace(r"\right", "")
    visible = visible.replace(r"\{", "{").replace(r"\}", "}").strip()
    if len(visible) < 3 or visible[0] not in "([{" or visible[-1] not in ")]}":
        return None
    inner = preprocess_latex(
        visible[1:-1], percent_as_fraction=percent_as_fraction
    )
    elements = _split_top_level_commas(inner)
    if elements is None:
        return None
    return visible[0], visible[-1], elements


def _expressions_equivalent(
    prediction: str,
    reference: str,
    *,
    percent_as_fraction: bool,
) -> bool | None:
    """Return symbolic equivalence, or None if either expression cannot parse."""

    predicted_expr = _try_parse(prediction, percent_as_fraction=percent_as_fraction)
    reference_expr = _try_parse(reference, percent_as_fraction=percent_as_fraction)
    if predicted_expr is None or reference_expr is None:
        return None
    import sympy

    try:
        if predicted_expr == reference_expr:
            return True
        return bool(sympy.simplify(predicted_expr - reference_expr) == 0)
    except Exception:
        return None


def score_math_answer(
    prediction_text: str,
    reference_answer: str,
    *,
    percent_as_fraction: bool = False,
) -> MathScore:
    """Score one MATH answer, recording which comparison method decided it."""

    prediction = extract_math_answer(prediction_text)
    reference = extract_math_answer(reference_answer) or reference_answer.strip() or None
    if prediction is None or reference is None:
        return MathScore(False, "failed", prediction, reference)

    predicted_structure = _structured_answer(
        prediction, percent_as_fraction=percent_as_fraction
    )
    reference_structure = _structured_answer(
        reference, percent_as_fraction=percent_as_fraction
    )
    if predicted_structure is not None or reference_structure is not None:
        if predicted_structure is None or reference_structure is None:
            return MathScore(False, "failed", prediction, reference)
        predicted_open, predicted_close, predicted_elements = predicted_structure
        reference_open, reference_close, reference_elements = reference_structure
        if (predicted_open, predicted_close) != (reference_open, reference_close):
            return MathScore(False, "sympy_equiv", prediction, reference)
        if len(predicted_elements) != len(reference_elements):
            return MathScore(False, "sympy_equiv", prediction, reference)
        comparisons = [
            _expressions_equivalent(
                predicted_element,
                reference_element,
                percent_as_fraction=percent_as_fraction,
            )
            for predicted_element, reference_element in zip(
                predicted_elements, reference_elements
            )
        ]
        if all(comparison is not None for comparison in comparisons):
            return MathScore(all(comparisons), "sympy_equiv", prediction, reference)
        return MathScore(False, "failed", prediction, reference)

    equivalent = _expressions_equivalent(
        prediction,
        reference,
        percent_as_fraction=percent_as_fraction,
    )
    if equivalent is not None:
        return MathScore(equivalent, "sympy_equiv", prediction, reference)

    # A normalized string can only decide the item when neither side has a
    # symbolic interpretation.  Falling back after a one-sided parse would
    # introduce format-correlated false negatives.
    predicted_expr = _try_parse(prediction, percent_as_fraction=percent_as_fraction)
    reference_expr = _try_parse(reference, percent_as_fraction=percent_as_fraction)
    if predicted_expr is None and reference_expr is None:
        predicted_string = normalize_math_string(
            prediction, percent_as_fraction=percent_as_fraction
        )
        reference_string = normalize_math_string(
            reference, percent_as_fraction=percent_as_fraction
        )
        if predicted_string and reference_string:
            return MathScore(
                predicted_string == reference_string,
                "string_match",
                prediction,
                reference,
            )
    return MathScore(False, "failed", prediction, reference)
