from __future__ import annotations

from app.config import settings
from app.models.lead import Lead


class OpenAITextGenerationAdapter:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Set TEXT_GENERATOR_PROVIDER=template or provide a valid API key."
            )

    def generate_profile(self, lead: Lead) -> dict:
        raise NotImplementedError("OpenAI adapter will be implemented later.")
