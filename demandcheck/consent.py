"""Versioned consent texts and validation of the opt-in form.

Each channel is a separate consent. The exact wording shown, its version and
language are stored with a timestamp so consent can be proven later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .i18n import translate

CONSENT_VERSION = "2026-09-26.1"
CHANNELS = ("email", "phone", "sms", "whatsapp", "updates")
EMAIL_CHANNELS = frozenset({"email", "updates"})
PHONE_CHANNELS = frozenset({"phone", "sms", "whatsapp"})


def consent_text(lang: str, channel: str) -> str:
    return f"{translate(lang, f'consent.{channel}')} {translate(lang, 'consent.withdraw')}"


@dataclass
class OptIn:
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    channels: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def needs_email_confirmation(self) -> bool:
        return bool(EMAIL_CHANNELS & set(self.channels))


def parse_optin(form: dict) -> OptIn:
    """Validate opt-in fields. Only channels whose checkbox value is exactly ``yes`` count."""
    data = OptIn(
        name=(form.get("name") or "").strip()[:120],
        email=(form.get("email") or "").strip()[:200],
        phone=(form.get("phone") or "").strip()[:40],
        company=(form.get("company") or "").strip()[:160],
        channels=[c for c in CHANNELS if form.get(f"consent_{c}") == "yes"],
    )
    if data.email and ("@" not in data.email or "." not in data.email.split("@")[-1]):
        data.errors.append("optin.error_email_needed")
    if not data.email and not data.phone:
        data.errors.append("optin.error_contact")
    if not data.channels:
        data.errors.append("optin.error_no_consent")
    if EMAIL_CHANNELS & set(data.channels) and not data.email:
        data.errors.append("optin.error_email_needed")
    if PHONE_CHANNELS & set(data.channels) and not data.phone:
        data.errors.append("optin.error_phone_needed")
    data.errors = list(dict.fromkeys(data.errors))
    return data
