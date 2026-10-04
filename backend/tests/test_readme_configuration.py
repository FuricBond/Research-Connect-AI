"""
Fix 9/9 — the README configuration table keeps up with the settings it documents.

Every email and SMTP setting (Phase 5.16) has a row, and the defaults the table states for them
and for the research refresh cap are the ones the Settings class actually uses.
"""
from __future__ import annotations

from pathlib import Path
import re

from app.core.config import Settings

README = Path(__file__).resolve().parents[2] / "README.md"


def _configuration_rows() -> dict[str, str]:
    """Maps each documented variable to its Default cell (a row may document two, `A` / `B`)."""
    text = README.read_text(encoding="utf-8")
    section = text.split("## Configuration", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].startswith("`"):
            continue
        names = re.findall(r"`([A-Z_]+)`", cells[0])
        defaults = [part.strip() for part in cells[1].split(" / ")]
        for index, name in enumerate(names):
            rows[name] = defaults[index] if len(defaults) == len(names) else cells[1]
    return rows


def test_every_email_and_smtp_setting_is_documented():
    documented = _configuration_rows()
    expected = {
        name.upper()
        for name in Settings.model_fields
        if name.startswith(("email_", "smtp_")) and name != "smtp_timeout_seconds"
    } | {"APP_PUBLIC_URL"}
    assert expected <= set(documented), sorted(expected - set(documented))


def test_documented_defaults_match_the_settings():
    documented = _configuration_rows()
    defaults = Settings(_env_file=None)
    assert documented["EMAIL_PROVIDER"] == f"`{defaults.email_provider}`"
    assert documented["SMTP_PORT"] == f"`{defaults.smtp_port}`"
    assert documented["SMTP_SECURITY"] == f"`{defaults.smtp_security}`"
    assert documented["EMAIL_FROM_NAME"] == f"`{defaults.email_from_name}`"
    assert documented["APP_PUBLIC_URL"] == f"`{defaults.app_public_url}`"
    assert documented["RESEARCH_REFRESH_MAX_WORKS"] == f"`{defaults.research_refresh_max_works}`"
    assert documented["EMAIL_RECIPIENT_ALLOWLIST"].startswith("empty") and defaults.email_recipient_allowlist == ""
