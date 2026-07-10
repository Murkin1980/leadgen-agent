from __future__ import annotations

from typing import Protocol

from app.models.lead import Lead


class TextGenerationAdapter(Protocol):
    def generate_profile(self, lead: Lead) -> dict: ...
