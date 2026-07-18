"""Numeric answer extraction and binomial scoring helpers."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation


_NUMBER = r"[-+]?(?:\$\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_NUMBER_RE = re.compile(_NUMBER)
_FINAL_PATTERNS = (
    re.compile(rf"####\s*({_NUMBER})", re.IGNORECASE),
    re.compile(rf"\\boxed\{{\s*({_NUMBER})\s*\}}", re.IGNORECASE),
    re.compile(rf"(?:final\s+answer|answer\s+is|therefore|thus)\s*[:=]?\s*({_NUMBER})", re.IGNORECASE),
)


def _canonical_number(raw: str) -> str | None:
    cleaned = raw.replace("$", "").replace(",", "").replace(" ", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def extract_final_number(text: str) -> str | None:
    """Extract the most likely final numeric answer from free-form model text.

    Explicit GSM8K/final-answer markers take precedence. Otherwise the last
    number is used, which is robust to chain-of-thought containing intermediates.
    """

    if not text:
        return None
    for pattern in _FINAL_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            return _canonical_number(matches[-1])
    matches = _NUMBER_RE.findall(text)
    return _canonical_number(matches[-1]) if matches else None


def exact_match(prediction: str, reference: str) -> bool:
    predicted = extract_final_number(prediction)
    expected = extract_final_number(reference)
    return predicted is not None and expected is not None and predicted == expected


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Return a two-sided Wilson score interval (95% by default)."""

    if total <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))
