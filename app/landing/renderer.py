from __future__ import annotations

import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.landing.schema import LandingProfile

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
SITES_DIR = Path(__file__).resolve().parent.parent.parent / "sites"


def render_landing(profile: LandingProfile, slug: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
    )
    template = env.get_template("landing.html")
    return template.render(profile=profile.model_dump())


def save_landing(slug: str, html: str, profile: LandingProfile) -> Path:
    output_dir = SITES_DIR / "drafts" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / "profile.json").write_text(
        profile.model_dump_json(indent=2), encoding="utf-8"
    )

    css = generate_css(profile.theme.primary_color, profile.theme.accent_color)
    (output_dir / "styles.css").write_text(css, encoding="utf-8")

    return output_dir


def generate_css(primary: str, accent: str) -> str:
    return f"""\
:root {{
    --primary: {primary};
    --accent: {accent};
    --bg: #f9fafb;
    --text: #111827;
    --text-light: #6b7280;
    --white: #ffffff;
    --radius: 12px;
    --max-w: 1100px;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, sans-serif; color: var(--text); background: var(--bg); line-height: 1.6; }}
.container {{ max-width: var(--max-w); margin: 0 auto; padding: 0 24px; }}
header {{ background: var(--primary); color: var(--white); padding: 60px 0 80px; text-align: center; }}
header h1 {{ font-size: clamp(1.8rem, 4vw, 3rem); margin-bottom: 12px; }}
header p {{ font-size: 1.15rem; opacity: .85; max-width: 600px; margin: 0 auto 24px; }}
.btn {{ display: inline-block; padding: 14px 32px; border-radius: var(--radius); text-decoration: none; font-weight: 600; font-size: 1rem; transition: transform .15s; }}
.btn:hover {{ transform: translateY(-2px); }}
.btn-accent {{ background: var(--accent); color: var(--white); }}
.btn-white {{ background: var(--white); color: var(--primary); }}
section {{ padding: 64px 0; }}
.section-title {{ font-size: 1.6rem; font-weight: 700; text-align: center; margin-bottom: 40px; color: var(--primary); }}
.services-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }}
.service-card {{ background: var(--white); padding: 32px 24px; border-radius: var(--radius); box-shadow: 0 2px 12px rgba(0,0,0,.06); text-align: center; }}
.service-card h3 {{ margin-bottom: 8px; color: var(--primary); }}
.service-card p {{ color: var(--text-light); font-size: .95rem; }}
.advantages {{ background: var(--white); }}
.advantages-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; }}
.advantage {{ display: flex; align-items: center; gap: 12px; padding: 16px; background: var(--bg); border-radius: var(--radius); }}
.advantage .icon {{ width: 40px; height: 40px; border-radius: 50%; background: var(--accent); color: var(--white); display: flex; align-items: center; justify-content: center; font-size: 1.2rem; flex-shrink: 0; }}
.steps {{ background: var(--bg); }}
.steps-list {{ max-width: 700px; margin: 0 auto; counter-reset: step; }}
.step {{ display: flex; gap: 20px; margin-bottom: 32px; align-items: flex-start; }}
.step-num {{ width: 48px; height: 48px; border-radius: 50%; background: var(--accent); color: var(--white); display: flex; align-items: center; justify-content: center; font-size: 1.2rem; font-weight: 700; flex-shrink: 0; }}
.cta-section {{ background: var(--primary); color: var(--white); text-align: center; padding: 64px 0; }}
.cta-section h2 {{ font-size: 1.8rem; margin-bottom: 16px; }}
.cta-section p {{ margin-bottom: 24px; opacity: .85; }}
.contact-section {{ background: var(--white); }}
.contact-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 32px; text-align: center; }}
.contact-item h3 {{ margin-bottom: 8px; color: var(--primary); }}
.whatsapp-float {{ position: fixed; bottom: 24px; right: 24px; width: 60px; height: 60px; border-radius: 50%; background: #25D366; color: var(--white); display: flex; align-items: center; justify-content: center; font-size: 1.8rem; text-decoration: none; box-shadow: 0 4px 16px rgba(0,0,0,.2); z-index: 100; transition: transform .15s; }}
.whatsapp-float:hover {{ transform: scale(1.1); }}
footer {{ background: var(--primary); color: var(--white); text-align: center; padding: 24px 0; font-size: .9rem; opacity: .8; }}
@media (max-width: 768px) {{
    header {{ padding: 40px 0 60px; }}
    section {{ padding: 48px 0; }}
}}
"""
