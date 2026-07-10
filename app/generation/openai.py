from __future__ import annotations

import json
import logging
import re
import time

from app.config import settings
from app.generation.base import GeneratedProfile, GeneratedProfileClaim
from app.generation.context import GenerationContext

logger = logging.getLogger(__name__)

PROMPT_DIR = "app/generation/prompts"


class OpenAITextGenerationAdapter:
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Set TEXT_GENERATOR_PROVIDER=template or provide a valid API key."
            )
        if not settings.openai_model:
            raise ValueError("OPENAI_MODEL is required when using OpenAI provider.")

    def generate(self, context: GenerationContext) -> GeneratedProfile:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )

        system_prompt = self._load_prompt("system_v1.txt")
        user_prompt = self._load_prompt("landing_profile_v1.txt")
        user_prompt = user_prompt.replace("{{CONTEXT_JSON}}", json.dumps(
            {
                "company_name": context.company_name,
                "city": context.city,
                "category": context.category,
                "phone": context.phone,
                "whatsapp_url": context.whatsapp_url,
                "social_links": context.social_links,
                "rating": context.rating,
                "reviews_count": context.reviews_count,
                "address": context.address,
                "services": context.services,
                "language": context.language,
                "notes": context.notes,
            },
            ensure_ascii=False,
            indent=2,
        ))

        start = time.time()
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_output_tokens,
            response_format={"type": "json_object"},
        )
        elapsed = time.time() - start

        content = response.choices[0].message.content or "{}"
        usage = response.usage

        try:
            profile_dict = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Model returned invalid JSON: {e}")

        raw_claims = profile_dict.pop("claims", [])
        claims = [
            GeneratedProfileClaim(
                text=c.get("text", ""),
                source_field=c.get("source_field", "unknown"),
                verified=c.get("verified", False),
            )
            for c in raw_claims
        ]

        logger.info(
            "OpenAI generation completed in %.2fs, tokens: in=%d out=%d",
            elapsed,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )

        return GeneratedProfile(data=profile_dict, claims=claims)

    def _load_prompt(self, filename: str) -> str:
        from pathlib import Path

        path = Path(PROMPT_DIR) / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
