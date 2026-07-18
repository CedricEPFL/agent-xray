"""LLM provider boundary with live Gemini and deterministic mock backends."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    simulated_latency_ms: float | None = None
    endpoint_model_version: str | None = None
    finish_reason: str | None = None
    blocked: bool = False


class LLMProvider(Protocol):
    model: str

    def generate(
        self,
        prompt: str,
        *,
        variant: str,
        component: str,
        problem_id: str,
        temperature: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse: ...


DEFAULT_ACCURACY = {
    "full": 0.82,
    "-critique": 0.72,
    "-revise": 0.68,
    "-vote": 0.66,
    "cot@1": 0.58,
    "sc@3": 0.70,
    "sc@5": 0.76,
    "sc@9": 0.80,
    "sc@budget": 0.79,
    "escalate_structure": 0.81,
    "escalate_sc": 0.78,
}

DEFAULT_TOKENS = {
    "generate": (115, 78),
    "critique": (150, 48),
    "revise": (185, 64),
    "vote": (210, 24),
}


class MockProvider:
    """Stable simulator with configurable accuracy and component token counts."""

    model = "mock-gsm8k"

    def __init__(
        self,
        seed: int = 42,
        accuracy_by_variant: Mapping[str, float] | None = None,
        tokens_by_component: Mapping[str, tuple[int, int]] | None = None,
        model: str | None = None,
    ) -> None:
        self.seed = seed
        if model is not None:
            self.model = model
        self.accuracy = {**DEFAULT_ACCURACY, **(accuracy_by_variant or {})}
        self.tokens = {**DEFAULT_TOKENS, **(tokens_by_component or {})}

    def _fraction(self, key: str) -> float:
        digest = hashlib.sha256(f"{self.seed}:{key}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def generate(
        self,
        prompt: str,
        *,
        variant: str,
        component: str,
        problem_id: str,
        temperature: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        del temperature
        metadata = metadata or {}
        sample_index = int(metadata.get("sample_index", 0))
        repeat = int(metadata.get("repeat", 0))
        gold = str(metadata.get("gold_answer", "0"))
        threshold = self.accuracy.get(variant, 0.6)
        correct = self._fraction(f"{problem_id}:{variant}:{component}:{sample_index}:{repeat}") < threshold
        try:
            numeric_gold = int(float(gold.replace(",", "")))
            wrong = numeric_gold + 1 + int(self._fraction(f"wrong:{problem_id}:{sample_index}:{repeat}") * 9)
        except ValueError:
            wrong = 1 + int(self._fraction(f"wrong-symbolic:{problem_id}:{sample_index}:{repeat}") * 9)

        if component == "critique":
            text = "Check the arithmetic and units carefully; the approach is plausible."
        elif component == "vote":
            text = f"The majority-supported final answer is {gold if correct else wrong}."
        else:
            text = (
                "I will compute the quantities step by step. The arithmetic gives the result. "
                f"Final answer: {gold if correct else wrong}"
            )

        base_input, base_output = self.tokens[component]
        prompt_variation = int(self._fraction(f"tokens:{problem_id}:{variant}:{component}:{sample_index}:{repeat}") * 9) - 4
        # Include a small prompt-length term so measured costs are not constant.
        input_tokens = max(1, base_input + len(prompt) // 80 + prompt_variation)
        output_tokens = max(1, base_output + prompt_variation // 2)
        latency_ms = 18.0 + self._fraction(f"latency:{problem_id}:{variant}:{component}:{sample_index}:{repeat}") * 7.0
        return LLMResponse(
            text,
            input_tokens,
            output_tokens,
            self.model,
            latency_ms,
            endpoint_model_version=f"{self.model}-seeded-v2",
            finish_reason="STOP",
            blocked=False,
        )


class GeminiProvider:
    """Google Gen AI SDK provider. Import and credential loading are lazy."""

    model = "gemini-3.1-flash-lite"

    def __init__(self, model: str | None = None) -> None:
        from dotenv import load_dotenv
        from google import genai

        repo_root = Path(__file__).resolve().parents[3]
        load_dotenv(repo_root / ".env", override=False)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(f"GEMINI_API_KEY is not set (expected in {repo_root / '.env'})")
        self.model = model or self.model
        self._client = genai.Client(api_key=api_key)

    @staticmethod
    def _fallback_count(text: str) -> int:
        return max(1, len(re.findall(r"\w+|[^\w\s]", text)))

    def generate(
        self,
        prompt: str,
        *,
        variant: str,
        component: str,
        problem_id: str,
        temperature: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        del variant, component, problem_id, metadata
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=2048,
            ),
        )
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        raw_finish_reason = getattr(candidate, "finish_reason", None)
        finish_reason = getattr(raw_finish_reason, "name", None) or (
            str(raw_finish_reason) if raw_finish_reason is not None else None
        )
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None)
        block_name = getattr(block_reason, "name", None) or (
            str(block_reason) if block_reason is not None else ""
        )
        blocked = block_name.upper() not in {"", "0", "NONE", "BLOCK_REASON_UNSPECIFIED"} or (finish_reason or "").upper() in {
            "SAFETY",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
        }
        try:
            text = response.text or ""
        except (ValueError, AttributeError):
            text = ""
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", None) or self._fallback_count(prompt)
        output_tokens = getattr(usage, "candidates_token_count", None) or self._fallback_count(text)
        return LLMResponse(
            text,
            int(input_tokens),
            int(output_tokens),
            self.model,
            endpoint_model_version=getattr(response, "model_version", None) or self.model,
            finish_reason=finish_reason,
            blocked=blocked,
        )
