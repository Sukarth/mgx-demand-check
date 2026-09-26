"""Buyer-demand refresh: recompute matches after buyer changes and compose update emails."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .buyers import Buyer
from .i18n import format_int, translate
from .matching import MatchResult, OwnerProfile, match


def snapshot(result: MatchResult) -> dict:
    return {
        "total": result.total,
        "by_type": result.by_type,
        "by_hq": result.by_hq,
        "appetite_eur": result.appetite_eur,
        "recent": result.recent,
        "buyer_ids": result.buyer_ids,
        "at": date.today().isoformat(),
    }


def owner_profile(owner: dict) -> OwnerProfile:
    return OwnerProfile(owner["sector"], owner["country"], owner["revenue_band"], owner["ebitda_band"])


@dataclass
class DemandChange:
    owner_id: int
    old_total: int
    new_total: int
    new_buyer_ids: list[str]
    result: MatchResult


def changes_for(owners: list[dict], buyers: list[Buyer]) -> list[DemandChange]:
    """Owners whose current matches include buyers not in their last snapshot."""
    out = []
    for owner in owners:
        result = match(buyers, owner_profile(owner))
        seen = set(owner["snapshot"].get("buyer_ids", []))
        new_ids = [b for b in result.buyer_ids if b not in seen]
        if new_ids:
            out.append(DemandChange(owner["id"], owner["snapshot"].get("total", 0),
                                    result.total, new_ids, result))
    return out


def update_email(owner: dict, change: DemandChange, result_url: str,
                 unsubscribe_url: str) -> tuple[str, str]:
    """Subject and plain-text body of a buyer-demand update in the owner's language."""
    lang = owner["lang"]
    n = len(change.new_buyer_ids)
    subject = (translate(lang, "nurture.subject_one") if n == 1
               else translate(lang, "nurture.subject", n=n))
    name = (owner.get("name") or "").split(" ")[0] or ""
    body = "\n\n".join([
        translate(lang, "nurture.greeting", name=name).replace(" ,", ","),
        translate(lang, "nurture.body", n=n,
                  sector=translate(lang, f"sector.{owner['sector']}"),
                  country=translate(lang, f"country.{owner['country']}"),
                  total=format_int(change.new_total, lang)),
        f"{translate(lang, 'nurture.cta')}: {result_url}",
        translate(lang, "nurture.footer", link=unsubscribe_url),
    ])
    return subject, body
