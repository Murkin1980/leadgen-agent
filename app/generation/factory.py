from __future__ import annotations

from app.config import settings


def create_text_generator(provider: str | None = None):
    provider = provider or settings.text_generator_provider

    if provider == "openai":
        from app.generation.openai import OpenAITextGenerationAdapter
        return OpenAITextGenerationAdapter()
    elif provider == "mock":
        from app.generation.mock import MockTextGenerationAdapter
        return MockTextGenerationAdapter()
    else:
        from app.generation.template import TemplateTextGenerationAdapter
        return TemplateTextGenerationAdapter()


def get_available_text_providers() -> list[str]:
    providers = ["template"]
    if settings.openai_api_key:
        providers.append("openai")
    providers.append("mock")
    return providers
