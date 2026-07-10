import shutil
from pathlib import Path

import pytest
from app.publisher.publisher import publish_site, SITES_DIR
from app.landing.schema import LandingProfile
from app.landing.renderer import render_landing, save_landing


class TestPublisher:
    def test_publish_site(self):
        profile = LandingProfile(
            meta={"title": "Test", "description": "Desc"},
            company={"name": "Co", "city": "City"},
            hero={"title": "Hero", "subtitle": "Sub", "cta_text": "CTA"},
        )
        slug = "test-pub"
        html = render_landing(profile, slug)
        save_landing(slug, html, profile)

        url = publish_site(slug)
        assert url.startswith("http")
        assert slug in url

        public_path = SITES_DIR / "public" / slug
        assert public_path.exists()
        assert (public_path / "index.html").exists()

        shutil.rmtree(SITES_DIR / "drafts" / slug, ignore_errors=True)
        shutil.rmtree(public_path, ignore_errors=True)

    def test_publish_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            publish_site("nonexistent-slug-xyz")
