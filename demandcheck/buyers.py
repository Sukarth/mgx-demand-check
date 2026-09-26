"""Buyer records: schema, loader and a deterministic generator for the illustrative sample.

The sample is entirely fictional. Buyers carry an id and a type but no name,
so no criteria are ever attached to a real firm. The production version reads
aggregated buyer criteria from MGX instead of this file.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .sectors import SECTORS, M

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_PATH = DATA_DIR / "buyers_sample.json"

BUYER_TYPES = ("pe_platform", "pe_addon", "strategic", "family_office", "search_fund")
PE_TYPES = frozenset({"pe_platform", "pe_addon"})
DEAL_TYPES = ("majority", "minority", "full_exit")

TOTAL_APPETITE_EUR = 52_000 * M
SAMPLE_SIZE = 2000
SAMPLE_SEED = 20260934
SAMPLE_REFERENCE_DATE = date(2026, 9, 26)


@dataclass
class Buyer:
    id: str
    display_type: str
    hq_country: str
    target_sectors: list[str]
    target_countries: list[str]  # country codes or region codes, see ``sectors.REGIONS``
    revenue_min: float
    revenue_max: float
    ebitda_min: float
    ebitda_max: float
    ev_min: float
    ev_max: float
    deal_types: list[str]
    appetite_eur: float
    active: bool = True
    added_at: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def is_pe(self) -> bool:
        return self.display_type in PE_TYPES

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Buyer":
        return cls(**data)


# HQ countries with relative weights, and the region each belongs to.
_HQ_WEIGHTS = {
    "FI": 18, "SE": 20, "NO": 9, "DK": 8, "DE": 16, "CH": 6, "AT": 3,
    "NL": 5, "GB": 7, "FR": 3, "US": 5,
}
_HOME_REGION = {
    "FI": "NORDICS", "SE": "NORDICS", "NO": "NORDICS", "DK": "NORDICS",
    "DE": "DACH", "CH": "DACH", "AT": "DACH", "NL": "BENELUX",
}
_NEIGHBOURS = {
    "FI": ("SE", "EE"), "SE": ("FI", "NO", "DK"), "NO": ("SE", "DK"), "DK": ("SE", "DE"),
    "DE": ("AT", "CH", "NL"), "AT": ("DE", "CH"), "CH": ("DE", "AT"), "NL": ("DE",),
}
_OTHER_REGIONS = ("NORDICS", "DACH", "BENELUX", "BALTICS")
_TYPE_WEIGHTS = {
    "pe_platform": 29, "pe_addon": 26, "strategic": 25, "family_office": 12, "search_fund": 8,
}
_SECTOR_COUNT = {
    "pe_platform": (1, 2), "pe_addon": (1, 1), "strategic": (1, 2),
    "family_office": (1, 3), "search_fund": (1, 3),
}
# EV bands (EUR millions) as (low_min, low_max, width_min, width_max) per buyer type,
# for buyers focused on the Nordics/Benelux and for buyers covering DACH.
_EV_BANDS = {
    "pe_platform": ((8, 20, 2.5, 4.0), (20, 50, 2.5, 4.0)),
    "pe_addon": ((2, 6, 2.5, 4.0), (5, 15, 2.5, 4.0)),
    "strategic": ((4, 15, 2.5, 5.0), (15, 40, 2.5, 5.0)),
    "family_office": ((10, 25, 2.5, 4.0), (20, 50, 2.5, 4.0)),
    "search_fund": ((3, 6, 2.0, 3.0), (5, 10, 2.0, 3.0)),
}


def _round_eur(value: float) -> float:
    step = 100_000 if value < 10 * M else 1 * M
    return max(step, round(value / step) * step)


def _pick_geography(rng: random.Random, hq: str) -> list[str]:
    """One to three country groups (a country code or a region code)."""
    home = _HOME_REGION.get(hq)
    if home is None:
        return rng.sample(_OTHER_REGIONS[:3], k=rng.choice([1, 1, 2]))
    roll = rng.random()
    if roll < 0.35:
        return [hq]
    if roll < 0.60:
        return [hq] + rng.sample(_NEIGHBOURS[hq], k=min(len(_NEIGHBOURS[hq]), rng.choice([1, 2])))
    if roll < 0.88:
        return [home]
    other = rng.choice([r for r in _OTHER_REGIONS if r != home])
    return [home, other]


def _pick_sectors(rng: random.Random, kind: str) -> list[str]:
    lo, hi = _SECTOR_COUNT[kind]
    n = max(lo, min(hi, rng.choices((1, 2, 3), (0.6, 0.3, 0.1))[0]))
    pool = [s.id for s in SECTORS]
    weights = [s.weight for s in SECTORS]
    chosen: list[str] = []
    while len(chosen) < n:
        pick = rng.choices(pool, weights)[0]
        if pick not in chosen:
            chosen.append(pick)
    return chosen


def _pick_ev_range(rng: random.Random, kind: str, geography: list[str]) -> tuple[float, float]:
    countries = {c for g in geography for c in (("DE", "AT", "CH") if g == "DACH" else (g,))}
    dach = bool(countries & {"DE", "AT", "CH"})
    lo_min, lo_max, w_min, w_max = _EV_BANDS[kind][1 if dach else 0]
    lo = rng.uniform(lo_min, lo_max) * M
    hi = lo * rng.uniform(w_min, w_max)
    return _round_eur(lo), _round_eur(min(hi, 250 * M))


def _type_quota(rng: random.Random, n: int) -> list[str]:
    """Buyer types in exact proportion to ``_TYPE_WEIGHTS``, shuffled."""
    total = sum(_TYPE_WEIGHTS.values())
    kinds = [k for k, w in _TYPE_WEIGHTS.items() for _ in range(round(n * w / total))]
    kinds = (kinds + ["strategic"] * n)[:n]
    rng.shuffle(kinds)
    return kinds


def _build_buyer(rng: random.Random, index: int, ref: date, kind: str) -> Buyer:
    hq = rng.choices(list(_HQ_WEIGHTS), list(_HQ_WEIGHTS.values()))[0]
    geography = _pick_geography(rng, hq)
    sectors = _pick_sectors(rng, kind)
    ev_min, ev_max = _pick_ev_range(rng, kind, geography)

    multiple = rng.uniform(5.0, 7.5)
    ebitda_min = _round_eur(ev_min / multiple)
    ebitda_max = _round_eur(ev_max / multiple)
    if kind == "strategic" and rng.random() < 0.15:
        ebitda_min = -2 * M  # open to turnarounds and loss-making targets
    margin_hi, margin_lo = rng.uniform(0.13, 0.18), rng.uniform(0.08, 0.11)
    revenue_min = _round_eur(max(ebitda_min, 0.2 * M) / margin_hi)
    revenue_max = _round_eur(ebitda_max / margin_lo)

    deal_types = ["majority", "full_exit"]
    if kind in ("family_office", "pe_platform") and rng.random() < 0.4:
        deal_types.append("minority")

    appetite = ev_max * rng.uniform(0.6, 2.5) * (2.0 if kind == "pe_platform" else 1.0)
    added = ref - timedelta(days=int(rng.triangular(0, 730, 200)))
    return Buyer(
        id=f"B{index:04d}",
        display_type=kind,
        hq_country=hq,
        target_sectors=sectors,
        target_countries=geography,
        revenue_min=revenue_min,
        revenue_max=revenue_max,
        ebitda_min=ebitda_min,
        ebitda_max=ebitda_max,
        ev_min=ev_min,
        ev_max=ev_max,
        deal_types=deal_types,
        appetite_eur=appetite,
        active=rng.random() < 0.94,
        added_at=added.isoformat(),
    )


def generate_sample(n: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED,
                    total_appetite: float = TOTAL_APPETITE_EUR,
                    reference_date: date = SAMPLE_REFERENCE_DATE) -> list[Buyer]:
    """Generate ``n`` fictional buyers; appetite is scaled so the sum equals ``total_appetite``."""
    rng = random.Random(seed)
    kinds = _type_quota(rng, n)
    buyers = [_build_buyer(rng, i + 1, reference_date, kinds[i]) for i in range(n)]
    scale = total_appetite / sum(b.appetite_eur for b in buyers)
    for b in buyers:
        b.appetite_eur = _round_eur(b.appetite_eur * scale)
    return buyers


def buyer_from_criteria(buyer_id: str, display_type: str, hq_country: str, sectors: list[str],
                        target_countries: list[str], ev_min: float, ev_max: float,
                        appetite_eur: float, added_at: str | None = None) -> Buyer:
    """Build a buyer from the criteria an advisor records; EBITDA and revenue ranges derive from EV."""
    ebitda_min = _round_eur(ev_min / 8.0)
    ebitda_max = _round_eur(ev_max / 5.0)
    return Buyer(
        id=buyer_id,
        display_type=display_type,
        hq_country=hq_country,
        target_sectors=list(sectors),
        target_countries=list(target_countries),
        revenue_min=_round_eur(ebitda_min / 0.25),
        revenue_max=_round_eur(ebitda_max / 0.05),
        ebitda_min=ebitda_min,
        ebitda_max=ebitda_max,
        ev_min=ev_min,
        ev_max=ev_max,
        deal_types=["majority", "full_exit"],
        appetite_eur=appetite_eur,
        active=True,
        added_at=added_at or date.today().isoformat(),
    )


def save_buyers(buyers: list[Buyer], path: Path = SAMPLE_PATH) -> None:
    payload = {
        "notice": "Illustrative, fictional sample. Not real buyers. "
                  "The production version reads aggregated buyer criteria from MGX.",
        "generated_with_seed": SAMPLE_SEED,
        "buyers": [b.to_dict() for b in buyers],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def load_buyers(path: Path = SAMPLE_PATH) -> list[Buyer]:
    if not path.exists():
        return generate_sample()
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Buyer.from_dict(b) for b in data["buyers"]]


if __name__ == "__main__":
    sample = generate_sample()
    save_buyers(sample)
    print(f"Wrote {len(sample)} buyers to {SAMPLE_PATH}")
