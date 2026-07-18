"""Composable workflow operators and the seven fixed experiment variants."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .providers import LLMResponse
from .scoring import extract_final_number


CallLLM = Callable[[str, str, int], LLMResponse]


@dataclass(frozen=True)
class VariantSpec:
    name: str
    components: tuple[str, ...]
    samples: int
    baseline: bool = False


def build_variant_matrix() -> list[VariantSpec]:
    return [
        VariantSpec("full", ("generate", "critique", "revise", "vote"), 3),
        VariantSpec("-critique", ("generate", "revise", "vote"), 3),
        VariantSpec("-revise", ("generate", "critique", "vote"), 3),
        VariantSpec("-vote", ("generate", "critique", "revise"), 1),
        VariantSpec("cot@1", ("generate",), 1, True),
        VariantSpec("sc@3", ("generate",), 3, True),
        VariantSpec("sc@5", ("generate",), 5, True),
    ]


def generate(question: str, call: CallLLM, sample_index: int) -> str:
    prompt = (
        "Solve this grade-school math problem. Show concise reasoning, then finish with "
        "'Final answer: <number>'.\n\nProblem: " + question
    )
    return call(prompt, "generate", sample_index).text


def critique(question: str, draft: str, call: CallLLM, sample_index: int) -> str:
    prompt = (
        "Inspect the proposed solution for arithmetic, logic, and unit errors. Do not solve a different problem.\n\n"
        f"Problem: {question}\n\nProposed solution: {draft}"
    )
    return call(prompt, "critique", sample_index).text


def revise(question: str, draft: str, feedback: str, call: CallLLM, sample_index: int) -> str:
    prompt = (
        "Revise the solution using the critique. Finish with 'Final answer: <number>'.\n\n"
        f"Problem: {question}\n\nDraft: {draft}\n\nCritique: {feedback}"
    )
    return call(prompt, "revise", sample_index).text


def vote(question: str, candidates: Sequence[str], call: CallLLM) -> str:
    rendered = "\n\n".join(f"Candidate {i + 1}: {text}" for i, text in enumerate(candidates))
    prompt = (
        "Select the answer supported by the majority of independently derived candidates. "
        "Recheck ties and finish with 'Final answer: <number>'.\n\n"
        f"Problem: {question}\n\n{rendered}"
    )
    return call(prompt, "vote", 0).text


def local_majority(candidates: Sequence[str]) -> str:
    numbers = [number for text in candidates if (number := extract_final_number(text)) is not None]
    if not numbers:
        return candidates[0] if candidates else ""
    counts = Counter(numbers)
    # Counter preserves first-seen order, providing deterministic tie-breaking.
    answer = max(counts, key=counts.get)
    return f"Final answer: {answer}"


def run_workflow(spec: VariantSpec, question: str, call: CallLLM) -> str:
    drafts = [generate(question, call, index) for index in range(spec.samples)]
    if spec.baseline:
        return drafts[0] if spec.samples == 1 else local_majority(drafts)

    feedback: list[str] = []
    if "critique" in spec.components:
        feedback = [critique(question, draft, call, index) for index, draft in enumerate(drafts)]
    candidates = drafts
    if "revise" in spec.components:
        if not feedback:
            feedback = ["Independently check every arithmetic step." for _ in drafts]
        candidates = [
            revise(question, draft, feedback[index], call, index)
            for index, draft in enumerate(drafts)
        ]
    elif feedback:
        # With revise ablated, critiques still feed the next graph node (vote).
        candidates = [
            f"{draft}\n\nReviewer critique: {feedback[index]}"
            for index, draft in enumerate(drafts)
        ]
    if "vote" in spec.components:
        return vote(question, candidates, call)
    return candidates[0]


def variant_by_name(name: str) -> VariantSpec:
    matrix: Mapping[str, VariantSpec] = {spec.name: spec for spec in build_variant_matrix()}
    return matrix[name]
