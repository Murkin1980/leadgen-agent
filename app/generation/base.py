from __future__ import annotations

from typing import Protocol

from app.generation.context import GenerationContext


class GeneratedProfileClaim:
    def __init__(self, text: str, source_field: str, verified: bool = True):
        self.text = text
        self.source_field = source_field
        self.verified = verified

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source_field": self.source_field,
            "verified": self.verified,
        }


class GeneratedProfile:
    def __init__(self, data: dict, claims: list[GeneratedProfileClaim] | None = None):
        self.data = data
        self.claims = claims or []

    def to_dict(self) -> dict:
        d = dict(self.data)
        d["claims"] = [c.to_dict() for c in self.claims]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GeneratedProfile":
        raw_claims = d.pop("claims", [])
        claims = [
            GeneratedProfileClaim(
                text=c["text"],
                source_field=c["source_field"],
                verified=c.get("verified", True),
            )
            for c in raw_claims
        ]
        return cls(data=d, claims=claims)


class TextGenerationAdapter(Protocol):
    def generate(self, context: GenerationContext) -> GeneratedProfile: ...
