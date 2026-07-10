import shutil
from pathlib import Path

import pytest
from app.publisher.publisher import publish_site, validate_slug, SITES_DIR
from app.landing.schema import LandingProfile
from app.landing.renderer import render_landing, save_landing


class TestSlugValidation:
    def test_valid_slug(self):
        assert validate_slug("my-company") == "my-company"

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            validate_slug("")

    def test_rejects_single_char(self):
        with pytest.raises(ValueError):
            validate_slug("a")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError):
            validate_slug("../../etc")

    def test_rejects_slash(self):
        with pytest.raises(ValueError):
            validate_slug("a/b")

    def test_rejects_backslash(self):
        with pytest.raises(ValueError):
            validate_slug("a\\b")

    def test_rejects_uppercase(self):
        with pytest.raises(ValueError):
            validate_slug("My-Company")

    def test_rejects_leading_dash(self):
        with pytest.raises(ValueError):
            validate_slug("-my-company")

    def test_rejects_trailing_dash(self):
        with pytest.raises(ValueError):
            validate_slug("my-company-")


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

    def test_publish_invalid_slug_raises(self):
        with pytest.raises(ValueError):
            publish_site("../../etc")

    def test_atomic_publish(self):
        profile = LandingProfile(
            meta={"title": "Atomic", "description": "Test"},
            company={"name": "Co", "city": "City"},
            hero={"title": "H", "subtitle": "S", "cta_text": "C"},
        )
        slug = "atomic-test"
        html = render_landing(profile, slug)
        save_landing(slug, html, profile)

        url = publish_site(slug)
        assert "atomic-test" in url

        public_path = SITES_DIR / "public" / slug
        assert public_path.exists()
        assert not (SITES_DIR / "public" / ".tmp" / slug).exists()

        shutil.rmtree(SITES_DIR / "drafts" / slug, ignore_errors=True)
        shutil.rmtree(public_path, ignore_errors=True)
