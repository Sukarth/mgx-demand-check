"""Message catalogs and locale-aware number formatting."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parent / "i18n"
LANGUAGES = ("en", "fi", "de", "sv")
DEFAULT_LANG = "en"
LANGUAGE_NAMES = {"en": "English", "fi": "Suomi", "de": "Deutsch", "sv": "Svenska"}


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict[str, str]:
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in tree.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, full + "."))
        else:
            out[full] = value
    return out


def available_languages() -> list[str]:
    return [lang for lang in LANGUAGES if lang == DEFAULT_LANG or catalog(lang)]


def translate(lang: str, key: str, **params) -> str:
    text = catalog(lang).get(key) or catalog(DEFAULT_LANG).get(key) or key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def pick_language(accept_language: str | None) -> str:
    """Choose the best supported language from an ``Accept-Language`` header."""
    supported = available_languages()
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in supported:
            return code
    return DEFAULT_LANG


def _decimal(lang: str, text: str) -> str:
    return text.replace(".", ",") if lang in ("fi", "de", "sv") else text


def format_eur(value: float, lang: str = DEFAULT_LANG) -> str:
    """Compact euro amount: ``€6.5M``, ``€1.2B``, ``€450k`` (decimal comma where customary)."""
    units = {"en": ("k", "M", "B"), "fi": (" t", " M", " mrd"),
             "de": (" Tsd.", " Mio.", " Mrd."), "sv": (" tkr", " mn", " md")}.get(lang, ("k", "M", "B"))
    v = abs(value)
    if v >= 1e9:
        num, unit = f"{v / 1e9:.1f}".rstrip("0").rstrip("."), units[2]
    elif v >= 1e6:
        num = f"{v / 1e6:.1f}".rstrip("0").rstrip(".") if v < 1e7 else f"{v / 1e6:.0f}"
        unit = units[1]
    elif v >= 1e3:
        num, unit = f"{v / 1e3:.0f}", units[0]
    else:
        num, unit = f"{v:.0f}", ""
    sign = "-" if value < 0 else ""
    num = _decimal(lang, num)
    if lang == "en":
        return f"{sign}€{num}{unit}"
    return f"{sign}{num}{unit} €"


def format_int(value: int, lang: str = DEFAULT_LANG) -> str:
    text = f"{value:,}"
    return text.replace(",", " ") if lang in ("fi", "sv") else text.replace(",", ".") if lang == "de" else text
