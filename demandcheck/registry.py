"""Finnish trade register lookup (PRH open data, YTJ API v3).

Only the company name and main line of business are read, to pre-fill the
owner form. Nothing is stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from .sectors import SECTORS

PRH_URL = "https://avoindata.prh.fi/opendata-ytj-api/v3/companies"
BUSINESS_ID_RE = re.compile(r"^\d{7}-\d$")
_WEIGHTS = (7, 9, 10, 5, 8, 4, 2)


class RegistryUnavailable(RuntimeError):
    """The register could not be reached or answered unexpectedly."""


@dataclass(frozen=True)
class Company:
    business_id: str
    name: str
    industry_code: str | None
    industry_name: str | None
    sector: str | None


def normalize_business_id(value: str) -> str:
    value = re.sub(r"\s", "", value or "")
    if re.fullmatch(r"\d{8}", value):
        value = f"{value[:7]}-{value[7]}"
    return value


def valid_business_id(value: str) -> bool:
    """Format and check digit of a Finnish business ID (Y-tunnus)."""
    if not BUSINESS_ID_RE.match(value):
        return False
    total = sum(int(d) * w for d, w in zip(value[:7], _WEIGHTS))
    remainder = total % 11
    if remainder == 1:
        return False
    check = 0 if remainder == 0 else 11 - remainder
    return check == int(value[-1])


def _nace_prefixes() -> list[tuple[str, str]]:
    """``(digits, sector_id)`` pairs, longest prefix first."""
    pairs = [(code.replace(".", ""), s.id) for s in SECTORS for code in s.nace]
    return sorted(pairs, key=lambda p: -len(p[0]))


_PREFIXES = _nace_prefixes()


def sector_for_industry_code(code: str | None) -> str | None:
    """Map a TOL/NACE industry code (e.g. ``49410``) to a sector id by longest prefix."""
    digits = re.sub(r"\D", "", code or "")
    if not digits:
        return None
    for prefix, sector in _PREFIXES:
        if digits.startswith(prefix):
            return sector
    return None


def parse_company(payload: dict, lang: str = "fi") -> Company | None:
    companies = payload.get("companies") or []
    if not companies:
        return None
    c = companies[0]
    names = [n for n in c.get("names", []) if str(n.get("type")) == "1" and not n.get("endDate")]
    name = (names or c.get("names") or [{}])[0].get("name", "")
    line = c.get("mainBusinessLine") or {}
    code = line.get("type")
    lang_code = {"fi": "1", "sv": "2"}.get(lang, "3")
    descriptions = {d.get("languageCode"): d.get("description") for d in line.get("descriptions", [])}
    return Company(
        business_id=(c.get("businessId") or {}).get("value", ""),
        name=name,
        industry_code=code,
        industry_name=descriptions.get(lang_code) or descriptions.get("3"),
        sector=sector_for_industry_code(code),
    )


def lookup(business_id: str, lang: str = "fi", http: httpx.Client | None = None,
           timeout: float = 8.0) -> Company | None:
    """Return the company, ``None`` if not found; raise ``RegistryUnavailable`` on errors."""
    client = http or httpx.Client(timeout=timeout)
    try:
        resp = client.get(PRH_URL, params={"businessId": business_id})
    except httpx.HTTPError as exc:
        raise RegistryUnavailable(str(exc)) from exc
    finally:
        if http is None:
            client.close()
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise RegistryUnavailable(f"HTTP {resp.status_code}")
    try:
        return parse_company(resp.json(), lang)
    except ValueError as exc:
        raise RegistryUnavailable("invalid JSON") from exc
