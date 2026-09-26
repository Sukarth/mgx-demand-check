"""Seed demo owners into the local database.

Creates one Finnish and one German opted-in owner with placeholder names and
confirmed consents, so the advisor dashboard has realistic records. The German
case sits in the DACH size band (indicative EV of roughly €40 to 55M) and
arrives through a postal letter. Usage::

    python -m demandcheck.demo            # add the demo owners
    python -m demandcheck.demo --drafts   # also draft call briefs and profiles
    python -m demandcheck.demo --drafts --env .env.production   # seed the Turso database

The buyer sample itself ships with the code (``data/buyers_sample.json``) and
is read-only; the database holds owners, consents, drafts and added buyers.
"""

from __future__ import annotations

import os
import sys

from . import briefs, nurture
from .buyers import load_buyers
from .consent import CONSENT_VERSION, consent_text
from .llm import LLMClient
from .matching import OwnerProfile, match
from .store import Store

DEMO_OWNERS = (
    {
        "lang": "fi", "sector": "logistics", "country": "FI", "revenue_band": "r_10_20",
        "ebitda_band": "e_1_2", "timing": "1_2y", "ownership": "100", "source": "sector",
        "name": "Matti Meikäläinen", "email": "matti@example.com", "phone": "+358 40 000 0001",
        "company": "Esimerkki Logistiikka Oy", "channels": ("phone", "updates"),
    },
    {
        "lang": "de", "sector": "technical_installation", "country": "DE", "revenue_band": "r_50_100",
        "ebitda_band": "e_5_10", "timing": "1_2y", "ownership": "100", "source": "letter",
        "name": "Max Mustermann", "email": "max@example.com", "phone": "+49 89 000 0001",
        "company": "Muster Elektrotechnik GmbH", "channels": ("email", "phone", "updates"),
    },
)


def seed(store: Store, with_drafts: bool = False) -> list[int]:
    buyers = load_buyers()
    existing = {o["email"] for o in store.list_owners()}
    ids = []
    for d in DEMO_OWNERS:
        if d["email"] in existing:
            continue
        result = match(buyers, OwnerProfile(d["sector"], d["country"], d["revenue_band"], d["ebitda_band"]))
        check_id = store.add_check(lang=d["lang"], sector=d["sector"], country=d["country"],
                                   revenue_band=d["revenue_band"], ebitda_band=d["ebitda_band"],
                                   timing=d["timing"], ownership=d["ownership"], source=d["source"],
                                   match_total=result.total)
        owner = store.add_owner(
            check_id=check_id, lang=d["lang"], name=d["name"], email=d["email"], phone=d["phone"],
            company=d["company"], snapshot=nurture.snapshot(result),
            consents=[(ch, consent_text(d["lang"], ch), CONSENT_VERSION) for ch in d["channels"]],
            needs_confirmation=True)
        store.confirm_email(owner["id"])
        ids.append(owner["id"])
        if with_drafts:
            client = LLMClient(cache=store)
            owner = store.get_owner(owner["id"])
            for kind in ("brief", "profile"):
                data, source = briefs.draft(kind, briefs.owner_facts(owner, list(d["channels"])), client)
                store.save_draft(owner["id"], kind, source, data)
    return ids


def load_env_file(path: str) -> None:
    for line in open(path, encoding="utf-8").read().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


if __name__ == "__main__":
    if "--env" in sys.argv:
        load_env_file(sys.argv[sys.argv.index("--env") + 1])
    store = Store()
    print(f"Database: {type(store.db).__name__}")
    created = seed(store, with_drafts="--drafts" in sys.argv)
    print(f"Created {len(created)} demo owner(s): {created}")
