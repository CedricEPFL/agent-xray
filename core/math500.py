"""MATH-500 download, caching, and level-stratified sampling."""

from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows?dataset=HuggingFaceH4%2FMATH-500"
    "&config=default&split=test&offset={offset}&length=100"
)


@dataclass(frozen=True)
class MathProblem:
    problem_id: str
    problem: str
    solution: str
    answer: str
    level: int
    subject: str

    @property
    def question(self) -> str:
        return self.problem


def _level_number(value: object) -> int:
    match = re.search(r"[1-5]", str(value))
    if not match:
        raise ValueError(f"Invalid MATH level: {value!r}")
    return int(match.group())


def _parse_rows(rows: list[dict[str, object]]) -> list[MathProblem]:
    return [
        MathProblem(
            problem_id=str(row.get("id", index)),
            problem=str(row["problem"]),
            solution=str(row["solution"]),
            answer=str(row["answer"]),
            level=_level_number(row["level"]),
            subject=str(row["subject"]),
        )
        for index, row in enumerate(rows)
    ]


def _download_rows() -> list[dict[str, object]]:
    headers = {"User-Agent": "agent-xray-study-v2/0.2"}
    rows: list[dict[str, object]] = []
    offset = 0
    try:
        while True:
            request = urllib.request.Request(HF_ROWS_URL.format(offset=offset), headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            page = [item["row"] for item in payload.get("rows", [])]
            rows.extend(page)
            offset += len(page)
            if not page or offset >= int(payload.get("num_rows_total", offset)):
                break
    except (OSError, ValueError, KeyError, urllib.error.HTTPError) as exc:
        raise RuntimeError("Unable to download MATH-500 from Hugging Face") from exc
    if not rows:
        raise RuntimeError("Hugging Face returned no MATH-500 rows")
    return rows


def _mock_rows(count: int = 100) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        level = index % 5 + 1
        denominator = index % 7 + 2
        numerator = (index * 3) % denominator + 1
        rows.append(
            {
                "id": f"mock-math-{index}",
                "problem": f"Simplify the rational expression {numerator}/{denominator} + {denominator}/{denominator}.",
                "solution": f"Combining denominators gives ({numerator}+{denominator})/{denominator}.",
                "answer": rf"\frac{{{numerator + denominator}}}{{{denominator}}}",
                "level": level,
                "subject": ("Algebra", "Geometry", "Number Theory", "Counting & Probability", "Precalculus")[index % 5],
            }
        )
    return rows


def stratified_sample(problems: list[MathProblem], n: int, seed: int) -> list[MathProblem]:
    if n <= 0:
        raise ValueError("n must be positive")
    if n > len(problems):
        raise ValueError(f"Requested {n} problems, but only {len(problems)} are available")
    by_level: dict[int, list[MathProblem]] = {}
    for problem in problems:
        by_level.setdefault(problem.level, []).append(problem)
    levels = sorted(by_level)
    if not levels:
        return []
    rng = random.Random(seed)
    for items in by_level.values():
        rng.shuffle(items)
    quotas = {level: n // len(levels) for level in levels}
    for level in levels[: n % len(levels)]:
        quotas[level] += 1
    selected: list[MathProblem] = []
    leftovers: list[MathProblem] = []
    for level in levels:
        take = min(quotas[level], len(by_level[level]))
        selected.extend(by_level[level][:take])
        leftovers.extend(by_level[level][take:])
    if len(selected) < n:
        rng.shuffle(leftovers)
        selected.extend(leftovers[: n - len(selected)])
    rng.shuffle(selected)
    return selected


def load_math500(
    *,
    n: int,
    seed: int,
    data_dir: Path | None = None,
    offline_mock: bool = False,
) -> list[MathProblem]:
    data_dir = data_dir or Path(__file__).resolve().parents[1] / "data"
    cache = data_dir / "math500_test.jsonl"
    if cache.exists():
        rows = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif offline_mock:
        rows = _mock_rows(max(100, n))
    else:
        rows = _download_rows()
        data_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return stratified_sample(_parse_rows(rows), n, seed)
