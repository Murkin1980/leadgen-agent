from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings

SITES_DIR = Path(__file__).resolve().parent.parent.parent / "sites"


def publish_site(slug: str) -> str:
    src = SITES_DIR / "drafts" / slug
    dst = SITES_DIR / "public" / slug

    if not src.exists():
        raise FileNotFoundError(f"Draft not found: {src}")

    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst)

    preview_url = f"{settings.public_base_url}/{slug}/"
    return preview_url
