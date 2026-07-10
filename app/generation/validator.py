from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.enrichment.enricher import normalize_phone
from app.generation.base import GeneratedProfile
from app.generation.context import GenerationContext


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_json(self) -> str:
        return json.dumps({
            "errors": self.errors,
            "warnings": self.warnings,
            "is_valid": self.is_valid,
        }, ensure_ascii=False)


FORBIDDEN_CLAIM_PATTERNS = [
    r"\b\d+\s*лет\s*(опыта|на\s*рынке)\b",
    r"\b\s*гарантия\s*\d+\b",
    r"\b\s*скидк\w*\s*\d+%\b",
    r"\b\s*цена\s+от\s+\d+\b",
    r"\b\s*более\s+\d+\s+проектов\b",
    r"\b\s*выполнено\s+\d+\b",
    r"\b\s*сертифицирован\w*\b",
    r"\b\s*наград\w*\b",
]

SCRIPT_PATTERN = re.compile(r"<script[\s>]", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[a-z][^>]*>", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"(sk-|api[_-]?key[_=]\s*\S{10,})", re.IGNORECASE)


class GeneratedContentValidator:
    def __init__(self, max_field_length: int = 2000):
        self.max_field_length = max_field_length

    def validate(
        self,
        profile: GeneratedProfile,
        context: GenerationContext,
    ) -> ValidationResult:
        result = ValidationResult()
        data = profile.data

        self._validate_schema(data, result)
        self._validate_forbidden_claims(data, result)
        self._validate_phone_consistency(data, context, result)
        self._validate_company_consistency(data, context, result)
        self._validate_city_consistency(data, context, result)
        self._validate_no_html_in_text(data, result)
        self._validate_no_scripts(data, result)
        self._validate_no_api_keys(data, result)
        self._validate_field_lengths(data, result)
        self._validate_hero_and_cta(data, result)
        self._validate_no_duplicate_services(data, result)

        return result

    def _validate_schema(self, data: dict, result: ValidationResult) -> None:
        required_keys = ["meta", "company", "hero", "contacts"]
        for key in required_keys:
            if key not in data:
                result.errors.append(f"Missing required key: {key}")

        if "meta" in data:
            meta = data["meta"]
            for field in ("title", "description"):
                if field not in meta or not meta[field]:
                    result.errors.append(f"meta.{field} is missing or empty")

        if "hero" in data:
            hero = data["hero"]
            for field in ("title", "subtitle", "cta_text"):
                if field not in hero or not hero[field]:
                    result.errors.append(f"hero.{field} is missing or empty")

    def _validate_forbidden_claims(self, data: dict, result: ValidationResult) -> None:
        all_text = self._collect_text(data)
        for pattern in FORBIDDEN_CLAIM_PATTERNS:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                result.warnings.append(f"Potentially unsupported claim detected: {matches[0]}")

        claims = data.get("claims", [])
        if isinstance(claims, list):
            for claim in claims:
                if isinstance(claim, dict) and not claim.get("verified", True):
                    result.errors.append(
                        f"Unsupported claim: {claim.get('text', 'unknown')}"
                    )

    def _validate_phone_consistency(
        self, data: dict, context: GenerationContext, result: ValidationResult
    ) -> None:
        company_phone = data.get("company", {}).get("phone")
        contacts_phone = data.get("contacts", {}).get("phone")

        if company_phone and contacts_phone:
            norm_company = normalize_phone(company_phone)
            norm_contacts = normalize_phone(contacts_phone)
            if norm_company and norm_contacts and norm_company != norm_contacts:
                result.errors.append(
                    f"Phone mismatch: company={company_phone} vs contacts={contacts_phone}"
                )

        context_phone = normalize_phone(context.phone) if context.phone else None
        if company_phone and context_phone:
            norm_company = normalize_phone(company_phone)
            if norm_company and norm_company != context_phone:
                result.errors.append(
                    f"Phone does not match lead data: {company_phone} vs {context.phone}"
                )

    def _validate_company_consistency(
        self, data: dict, context: GenerationContext, result: ValidationResult
    ) -> None:
        company_name = data.get("company", {}).get("name", "")
        if context.company_name and company_name:
            if company_name.lower().strip() != context.company_name.lower().strip():
                result.warnings.append(
                    f"Company name differs from lead: '{company_name}' vs '{context.company_name}'"
                )

    def _validate_city_consistency(
        self, data: dict, context: GenerationContext, result: ValidationResult
    ) -> None:
        city = data.get("company", {}).get("city") or data.get("contacts", {}).get("city")
        if context.city and city:
            if city.lower().strip() != context.city.lower().strip():
                result.errors.append(
                    f"City mismatch: '{city}' vs '{context.city}'"
                )

    def _validate_no_html_in_text(self, data: dict, result: ValidationResult) -> None:
        text_fields = self._get_text_fields(data)
        for path, value in text_fields:
            if HTML_TAG_PATTERN.search(str(value)):
                result.errors.append(f"HTML tag found in text field: {path}")

    def _validate_no_scripts(self, data: dict, result: ValidationResult) -> None:
        all_text = self._collect_text(data)
        if SCRIPT_PATTERN.search(all_text):
            result.errors.append("Script tags detected in output")

    def _validate_no_api_keys(self, data: dict, result: ValidationResult) -> None:
        all_text = self._collect_text(data)
        if API_KEY_PATTERN.search(all_text):
            result.errors.append("API key-like string detected in output")

    def _validate_field_lengths(self, data: dict, result: ValidationResult) -> None:
        text_fields = self._get_text_fields(data)
        for path, value in text_fields:
            if len(str(value)) > self.max_field_length:
                result.errors.append(f"Field {path} exceeds max length ({self.max_field_length})")

    def _validate_hero_and_cta(self, data: dict, result: ValidationResult) -> None:
        hero = data.get("hero", {})
        if not hero.get("title", "").strip():
            result.errors.append("Hero title is empty")
        if not hero.get("cta_text", "").strip():
            result.errors.append("CTA text is empty")

    def _validate_no_duplicate_services(self, data: dict, result: ValidationResult) -> None:
        services = data.get("services", [])
        if isinstance(services, list):
            titles = [s.get("title", "") for s in services if isinstance(s, dict)]
            seen = set()
            for t in titles:
                normalized = t.lower().strip()
                if normalized in seen:
                    result.errors.append(f"Duplicate service: {t}")
                seen.add(normalized)

    def _collect_text(self, data: dict) -> str:
        parts = []
        for key, value in data.items():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                parts.append(self._collect_text(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.append(self._collect_text(item))
        return " ".join(parts)

    def _get_text_fields(self, data: dict, prefix: str = "") -> list[tuple[str, str]]:
        fields = []
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str):
                fields.append((path, value))
            elif isinstance(value, dict):
                fields.extend(self._get_text_fields(value, path))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, str):
                        fields.append((f"{path}[{i}]", item))
                    elif isinstance(item, dict):
                        fields.extend(self._get_text_fields(item, f"{path}[{i}]"))
        return fields
