"""AI-drafted call briefs and anonymous company profiles for advisors.

The model only drafts text from facts computed in code; it never decides
matches or values. When no model is reachable a deterministic draft is used so
the advisor always gets a usable starting point. Every draft is reviewed by a
person before anything reaches an owner or a buyer.
"""

from __future__ import annotations

import json

from .i18n import format_eur, translate
from .llm import LLMClient, LLMUnavailable
from .valuation import indicative_value

LANG_NAMES = {"en": "English", "fi": "Finnish", "de": "German", "sv": "Swedish"}
TIMING_EN = {"now": "now or within a year", "1_2y": "in one to two years",
             "3y_plus": "in three years or later", "curious": "just curious, no timeline"}
OWNERSHIP_EN = {"100": "100%", "50_99": "50 to 99%", "lt50": "under 50%"}


def owner_facts(owner: dict, consents: list[str]) -> dict:
    """Facts about an opted-in owner in English, as passed to the model."""
    snap = owner["snapshot"]
    val = indicative_value(owner["sector"], owner["ebitda_band"])
    return {
        "contact_name": owner.get("name") or "(not given)",
        "company": owner.get("company") or "(not given)",
        "owner_language": LANG_NAMES.get(owner["lang"], "English"),
        "sector": translate("en", f"sector.{owner['sector']}"),
        "country": translate("en", f"country.{owner['country']}"),
        "revenue_band": translate("en", f"revenue.{owner['revenue_band']}"),
        "ebitda_band": translate("en", f"ebitda.{owner['ebitda_band']}"),
        "timing": TIMING_EN.get(owner.get("timing") or "", "not given"),
        "ownership_share": OWNERSHIP_EN.get(owner.get("ownership") or "", "not given"),
        "consented_channels": consents,
        "matching_buyers_total": snap.get("total", 0),
        "matching_buyers_by_type": {translate("en", f"buyer_type.{k}"): v
                                    for k, v in snap.get("by_type", {}).items()},
        "matching_buyers_by_hq_country": {translate("en", f"country.{k}"): v
                                          for k, v in list(snap.get("by_hq", {}).items())[:6]},
        "indicative_ev_range": (f"{format_eur(val.ev_low)} to {format_eur(val.ev_high)}"
                                if val else "not meaningful (loss-making)"),
    }


BRIEF_SYSTEM = """You prepare M&A advisors at Mergero for a first call with a business owner who asked to be contacted after using an anonymous buyer-demand check.
Write in English, except the opening line, which must be in the owner's language.
Use only the facts given. Do not invent numbers, names, history or buyer identities. Keep a warm, direct, discreet tone: owners are often cautious and not technical. Lead with continuity, employees and options, not with price.
Return a JSON object with keys:
"summary": two sentences on who this is and why the call matters,
"situation": list of 3 to 5 short bullets on what the owner told us,
"buyer_fit": list of 2 to 4 bullets on which buyer groups match (with their counts) and what that type of buyer usually looks for; do not invent specific buyers, strategies or regions,
"opening_line": one or two sentences the advisor can say to open the call, in the owner's language,
"opening_line_en": English translation of the opening line,
"questions": list of 5 open questions to ask, in English,
"watch_outs": list of 1 to 3 things to be careful about (for example expectations, timing, confidentiality)."""

PROFILE_SYSTEM = """You draft an anonymous company profile (a teaser starter) that Mergero can show to matching buyers in a Soft Launch or Silent Mandate, after the owner agrees.
Write in English. The profile must not identify the company: no company name, no person names, no city, no exact figures beyond the bands given. Country or region is fine.
Use only the facts given. Where a typical teaser point is unknown, write a placeholder in square brackets for the advisor to fill in, for example "[number of employees]". Never invent facts.
Return a JSON object with keys:
"headline": a short anonymous headline such as "Profitable logistics company in Finland",
"summary": three to four sentences,
"key_facts": list of 4 to 6 "Label: value" strings,
"highlights": list of 3 to 5 investment highlight bullets. Each bullet either restates a given fact or is a bracketed placeholder for the advisor, for example "[Customer base and contract length]". Do not claim anything about customers, margins, growth, location or market position that is not in the facts,
"ideal_buyers": one or two sentences on which buyer types fit and why,
"transaction": one sentence on the transaction the owner may consider."""


PROFILE_EXCLUDED = frozenset({"contact_name", "company", "consented_channels", "indicative_ev_range",
                              "matching_buyers_total", "matching_buyers_by_hq_country"})


def _user_prompt(facts: dict) -> str:
    return "Facts:\n" + json.dumps(facts, ensure_ascii=False, indent=1)


def fallback_brief(facts: dict) -> dict:
    types = ", ".join(f"{k} ({v})" for k, v in facts["matching_buyers_by_type"].items()) or "none"
    return {
        "summary": f"{facts['contact_name']} runs a {facts['sector'].lower()} company in {facts['country']} "
                   f"with revenue {facts['revenue_band']} and EBITDA {facts['ebitda_band']}. "
                   f"{facts['matching_buyers_total']} buyers in the network match.",
        "situation": [f"Timing: {facts['timing']}", f"Ownership share: {facts['ownership_share']}",
                      f"Consented channels: {', '.join(facts['consented_channels'])}",
                      f"Indicative EV range shown: {facts['indicative_ev_range']}"],
        "buyer_fit": [f"Matching buyer types: {types}"],
        "opening_line": translate({"Finnish": "fi", "German": "de", "Swedish": "sv"}.get(
            facts["owner_language"], "en"), "result.next_call_body"),
        "opening_line_en": "Thank you for checking buyer demand. I'd like to tell you what these buyers look for.",
        "questions": ["What made you run the check now?", "What matters most to you in a future owner?",
                      "How involved do you want to stay after a transaction?",
                      "How are this year's numbers developing?", "Who else is involved in the decision?"],
        "watch_outs": ["Draft generated without AI: review before use."],
    }


def fallback_profile(facts: dict) -> dict:
    return {
        "headline": f"{facts['sector']} company in {facts['country']}",
        "summary": f"An owner-managed {facts['sector'].lower()} company based in {facts['country']}, "
                   f"with revenue of {facts['revenue_band']} and EBITDA of {facts['ebitda_band']}. "
                   "[Short description of the business and its customers].",
        "key_facts": [f"Sector: {facts['sector']}", f"Country: {facts['country']}",
                      f"Revenue: {facts['revenue_band']}", f"EBITDA: {facts['ebitda_band']}",
                      "Employees: [number]"],
        "highlights": ["[Customer base and contract length]", "[Market position]", "[Growth opportunities]"],
        "ideal_buyers": "Buyer groups matching the stated criteria in the network.",
        "transaction": f"Owner holds {facts['ownership_share']}; timing {facts['timing']}.",
    }


def draft(kind: str, facts: dict, client: LLMClient | None) -> tuple[dict, str]:
    """Return ``(draft, source_label)`` for ``kind`` in ``{"brief", "profile"}``."""
    if kind == "profile":
        # The profile is written for buyers: identity, contact details and our value estimate stay out.
        facts = {k: v for k, v in facts.items() if k not in PROFILE_EXCLUDED}
    system = BRIEF_SYSTEM if kind == "brief" else PROFILE_SYSTEM
    fallback = fallback_brief if kind == "brief" else fallback_profile
    if client is None or not client.available():
        return fallback(facts), "template"
    try:
        data, model = client.chat_json(kind, system, _user_prompt(facts), max_tokens=1400,
                                       use_cache=False)
    except LLMUnavailable:
        return fallback(facts), "template"
    return data, model
