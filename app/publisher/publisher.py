from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from app.config import settings

SITES_DIR = Path(__file__).resolve().parent.parent.parent / "sites"

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


def validate_slug(slug: str) -> str:
    if not slug or not SLUG_PATTERN.match(slug):
        raise ValueError(
            f"Invalid slug: {slug!r}. "
            "Must be lowercase alphanumeric with hyphens, min 3 chars."
        )
    if ".." in slug or "/" in slug or "\\" in slug:
        raise ValueError(f"Unsafe slug: {slug!r}")
    return slug


def publish_site(slug: str) -> str:
    validate_slug(slug)

    src = SITES_DIR / "drafts" / slug
    dst = SITES_DIR / "public" / slug

    if not src.exists():
        raise FileNotFoundError(f"Draft not found: {src}")

    tmp_dir = SITES_DIR / "public" / ".tmp" / slug

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    shutil.copytree(src, tmp_dir)

    if dst.exists():
        shutil.rmtree(dst)

    tmp_dir.rename(dst)

    preview_url = f"{settings.public_base_url}/{slug}/"
    return preview_url
