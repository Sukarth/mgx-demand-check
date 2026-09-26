import json
import re
import string

import pytest

from demandcheck.i18n import (
    I18N_DIR, _flatten, format_eur, format_int, pick_language, resolve_sector_slug, sector_path, slugify,
)
from demandcheck.sectors import SECTOR_IDS

EN = _flatten(json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8")))


def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


@pytest.mark.parametrize("lang", ["fi", "de", "sv"])
def test_catalog_complete_with_matching_placeholders(lang):
    cat = _flatten(json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8")))
    optional = ("letter.",) if lang != "de" else ()
    missing = [k for k in EN if k not in cat and not k.startswith(optional or ("\0",))]
    assert not missing
    for key, text in cat.items():
        assert _fields(text) <= _fields(EN[key]), key


@pytest.mark.parametrize("lang", ["en", "fi", "de", "sv"])
def test_sector_slugs_unique_and_resolvable(lang):
    slugs = [sector_path(lang, s).rsplit("/", 1)[1] for s in SECTOR_IDS]
    assert len(set(slugs)) == len(slugs)
    assert all(re.fullmatch(r"[a-z0-9-]+", s) for s in slugs)
    assert [resolve_sector_slug(s, SECTOR_IDS) for s in slugs] == list(SECTOR_IDS)


def test_localized_sector_paths():
    assert sector_path("fi", "logistics") == "/fi/toimialat/logistiikka-ja-kuljetus"
    assert sector_path("de", "logistics", "DE") == "/de/branchen/logistik-und-transport?country=DE"
    assert slugify("Städ- och fastighetsservice") == "stad-och-fastighetsservice"


def test_number_formats():
    assert format_eur(6_500_000, "en") == "€6.5M"
    assert format_eur(6_500_000, "fi") == "6,5 M€"
    assert format_eur(45_000_000, "de") == "45 Mio. €"
    assert format_eur(1_700_000_000, "sv") == "1,7 mdr €"
    assert format_int(2000, "de") == "2.000"


def test_pick_language():
    assert pick_language("fi-FI,fi;q=0.9,en;q=0.8") == "fi"
    assert pick_language("fr-FR") == "en"
