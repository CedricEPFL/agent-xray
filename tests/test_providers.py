from core.providers import GeminiProvider


def test_gemini_provider_uses_current_default_model():
    assert GeminiProvider.model == "gemini-3.1-flash-lite"
