import os
from models.gemini_service import GeminiService
from models.openrouter_service import OpenRouterService

_llm_service = None

def get_llm_service():
    global _llm_service
    if _llm_service is None:
        provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
        if provider == "openrouter":
            _llm_service = OpenRouterService()
        else:
            _llm_service = GeminiService()
    return _llm_service
