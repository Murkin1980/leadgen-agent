"""WhatsApp template sync with Meta Graph API."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import settings
from app.models.whatsapp import WhatsAppTemplate, WhatsAppTemplateStatus

logger = logging.getLogger(__name__)


class TemplateSyncResult:
    """Result of a template sync operation."""

    def __init__(self) -> None:
        self.created: int = 0
        self.updated: int = 0
        self.errors: list[str] = []


@dataclass
class RemoteTemplate:
    """Representation of a template from the Meta Graph API."""

    name: str
    language_code: str
    category: str
    status: str
    provider_template_id: str
    body_text: str = ""


class TemplateSyncAdapter(Protocol):
    """Protocol for fetching templates from a provider."""

    def fetch_templates(self) -> list[RemoteTemplate]: ...


class MetaTemplateSyncAdapter:
    """Fetches templates from Meta WhatsApp Cloud API.

    No real Meta calls are made in CI tests; use MockTemplateSyncAdapter instead.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._enabled = bool(
            settings.whatsapp_cloud_api_token
            and settings.whatsapp_cloud_business_account_id
        )
        self._url = (
            f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
            f"{settings.whatsapp_cloud_business_account_id}/message_templates"
        )
        self._headers = {
            "Authorization": f"Bearer {settings.whatsapp_cloud_api_token}",
        }

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    def fetch_templates(self) -> list[RemoteTemplate]:
        if not self._enabled:
            logger.warning("MetaTemplateSyncAdapter: not configured, skipping")
            return []

        client = self._client or httpx.Client(timeout=30)
        close_client = self._client is None
        try:
            resp = client.get(self._url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Failed to fetch templates from Meta: %s", exc)
            return []
        finally:
            if close_client:
                client.close()

        templates: list[RemoteTemplate] = []
        for item in data.get("data", []):
            components = item.get("components", [])
            body_text = ""
            for comp in components:
                if comp.get("type") == "BODY":
                    body_text = comp.get("text", "")
                    break
            templates.append(RemoteTemplate(
                name=item.get("name", ""),
                language_code=item.get("language", ""),
                category=item.get("category", ""),
                status=item.get("status", "").lower(),
                provider_template_id=item.get("id", ""),
                body_text=body_text,
            ))
        return templates


class MockTemplateSyncAdapter:
    """Mock adapter for testing. Returns configurable templates."""

    def __init__(self, templates: list[RemoteTemplate] | None = None) -> None:
        self._templates = templates or []

    def fetch_templates(self) -> list[RemoteTemplate]:
        return list(self._templates)


def sync_templates(db, adapter: TemplateSyncAdapter) -> TemplateSyncResult:
    """Upsert templates from remote provider into local DB.

    Upserts by (name, language_code). Updates status and provider_template_id.
    """
    result = TemplateSyncResult()
    remote_templates = adapter.fetch_templates()

    for remote in remote_templates:
        if not remote.name or not remote.language_code:
            result.errors.append(f"Skipping template with empty name or language: {remote}")
            continue

        existing = (
            db.query(WhatsAppTemplate)
            .filter(
                WhatsAppTemplate.name == remote.name,
                WhatsAppTemplate.language_code == remote.language_code,
            )
            .first()
        )

        status = _normalize_status(remote.status)

        if existing:
            existing.status = status
            existing.provider_template_id = remote.provider_template_id
            existing.category = remote.category or existing.category
            if remote.body_text:
                existing.body_template = remote.body_text
            result.updated += 1
        else:
            template = WhatsAppTemplate(
                id=str(uuid.uuid4())[:12],
                name=remote.name,
                language_code=remote.language_code,
                category=remote.category,
                status=status,
                body_template=remote.body_text or "",
                provider_template_id=remote.provider_template_id,
            )
            db.add(template)
            result.created += 1

    db.commit()
    return result


def _normalize_status(raw: str) -> str:
    """Map Meta status to our WhatsAppTemplateStatus values."""
    mapping = {
        "approved": WhatsAppTemplateStatus.approved.value,
        "rejected": WhatsAppTemplateStatus.rejected.value,
        "pending": WhatsAppTemplateStatus.pending.value,
        "disabled": WhatsAppTemplateStatus.disabled.value,
        "IN_PROGRESS": WhatsAppTemplateStatus.pending.value,
        "ACTIVE": WhatsAppTemplateStatus.approved.value,
    }
    return mapping.get(raw, WhatsAppTemplateStatus.pending.value)
