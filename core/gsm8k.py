"""GSM8K download, caching, sampling, and reference-answer parsing."""

from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .scoring import extract_final_number


HF_JSONL_URLS = (
    "https://huggingface.co/datasets/openai/gsm8k/resolve/main/data/test.jsonl",
    "https://huggingface.co/datasets/openai/gsm8k/resolve/main/test.jsonl",
)
HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows?dataset=openai%2Fgsm8k"
    "&config=main&split=test&offset={offset}&length=100"
)


@dataclass(frozen=True)
class Problem:
    problem_id: str
    question: str
    answer: str
    numeric_answer: str


def numeric_reference(answer: str) -> str:
    marker = answer.rsplit("####", 1)
    if len(marker) != 2:
        raise ValueError("GSM8K answer is missing the '#### <number>' marker")
    number = extract_final_number("#### " + marker[1])
    if number is None:
        raise ValueError(f"Could not parse GSM8K numeric reference from {answer!r}")
    return number


def _parse_rows(rows: list[dict[str, str]]) -> list[Problem]:
    problems = []
    for index, row in enumerate(rows):
        question = row["question"]
        answer = row["answer"]
        problems.append(Problem(str(index), question, answer, numeric_reference(answer)))
    return problems


def _download_jsonl() -> list[dict[str, str]]:
    headers = {"User-Agent": "agent-xray-poc/0.1"}
    last_error: Exception | None = None
    for url in HF_JSONL_URLS:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                text = response.read().decode("utf-8")
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            if rows:
                return rows
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            last_error = exc

    # Official Hugging Face datasets-server fallback, still plain HTTPS/JSON.
    rows: list[dict[str, str]] = []
    offset = 0
    try:
        while True:
            url = HF_ROWS_URL.format(offset=offset)
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            page = [item["row"] for item in payload.get("rows", [])]
            rows.extend(page)
            offset += len(page)
            if not page or offset >= int(payload.get("num_rows_total", offset)):
                break
        if rows:
            return rows
    except (OSError, ValueError, KeyError, urllib.error.HTTPError) as exc:
        last_error = exc
    raise RuntimeError("Unable to download GSM8K from Hugging Face") from last_error


def _mock_rows(count: int = 100) -> list[dict[str, str]]:
    """Offline GSM-style fixtures used only by the mock experiment."""

    rows = []
    for i in range(count):
        boxes = i + 7
        items = (i % 9) + 3
        sold = i % 5
        result = boxes * items - sold
        rows.append(
            {
                "question": f"A shop has {boxes} boxes with {items} pencils each and sells {sold} pencils. How many remain?",
                "answer": f"There are {boxes * items} pencils before sales. After sales, {boxes * items}-{sold}={result}. #### {result}",
            }
        )
    return rows


def load_gsm8k(
    *,
    n: int = 50,
    seed: int = 42,
    data_dir: Path | None = None,
    offline_mock: bool = False,
) -> list[Problem]:
    if n <= 0:
        raise ValueError("n must be positive")
    data_dir = data_dir or Path(__file__).resolve().parents[1] / "data"
    cache = data_dir / "gsm8k_test.jsonl"
    if cache.exists():
        rows = [json.loads(line) for line in cache.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif offline_mock:
        rows = _mock_rows(max(100, n))
    else:
        rows = _download_jsonl()
        data_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    if n > len(rows):
        raise ValueError(f"Requested {n} problems, but only {len(rows)} are available")
    sampled_indices = random.Random(seed).sample(range(len(rows)), n)
    all_problems = _parse_rows(rows)
    return [all_problems[index] for index in sampled_indices]
