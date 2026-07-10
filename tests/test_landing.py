import json

import pytest
from app.landing.schema import LandingProfile
from app.landing.renderer import render_landing, save_landing


class TestLandingSchema:
    def test_valid_schema(self):
        data = {
            "meta": {"title": "Test", "description": "Desc"},
            "company": {"name": "Co", "city": "City"},
            "hero": {"title": "Hero", "subtitle": "Sub", "cta_text": "CTA"},
            "services": [{"title": "S1", "description": "D1"}],
            "advantages": ["A1"],
            "contacts": {"phone": "+7700"},
            "theme": {"style": "modern", "primary_color": "#000", "accent_color": "#fff"},
        }
        profile = LandingProfile(**data)
        assert profile.meta.title == "Test"
        assert len(profile.services) == 1

    def test_json_roundtrip(self):
        data = {
            "meta": {"title": "Test", "description": "Desc"},
            "company": {"name": "Co", "city": "City"},
            "hero": {"title": "Hero", "subtitle": "Sub", "cta_text": "CTA"},
            "services": [],
            "advantages": [],
            "contacts": {},
            "theme": {"style": "modern", "primary_color": "#000", "accent_color": "#fff"},
        }
        profile = LandingProfile(**data)
        serialized = profile.model_dump_json()
        parsed = json.loads(serialized)
        profile2 = LandingProfile(**parsed)
        assert profile2.meta.title == "Test"


class TestRendering:
    def _make_profile(self):
        return LandingProfile(
            meta={"title": "Test Landing", "description": "Test desc"},
            company={"name": "TestCo", "city": "Алматы", "phone": "+77001112233", "whatsapp_url": "https://wa.me/77001112233"},
            hero={"title": "Hero Title", "subtitle": "Subtitle", "cta_text": "Call"},
            services=[{"title": "Service 1", "description": "Desc 1"}],
            advantages=["Advantage 1", "Advantage 2"],
            contacts={"phone": "+77001112233", "city": "Алматы", "whatsapp_url": "https://wa.me/77001112233"},
        )

    def test_renders_html(self):
        profile = self._make_profile()
        html = render_landing(profile, "test-slug")
        assert "Hero Title" in html
        assert "TestCo" in html
        assert "Service 1" in html
        assert "Advantage 1" in html
        assert "<!DOCTYPE html>" in html

    def test_has_meta_tags(self):
        profile = self._make_profile()
        html = render_landing(profile, "test-slug")
        assert '<meta name="description"' in html
        assert '<meta property="og:title"' in html

    def test_has_whatsapp_button(self):
        profile = self._make_profile()
        html = render_landing(profile, "test-slug")
        assert "whatsapp-float" in html
        assert "wa.me" in html

    def test_save_landing(self):
        profile = self._make_profile()
        html = render_landing(profile, "test-save")
        path = save_landing("test-save", html, profile)
        assert path.exists()
        assert (path / "index.html").exists()
        assert (path / "styles.css").exists()
        assert (path / "profile.json").exists()
