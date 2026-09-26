"""Indicative enterprise-value range from sector and EBITDA band. Pure functions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .sectors import EBITDA_BY_ID

MULTIPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "sector_multiples.json"
MIN_MULTIPLE = 2.0


@dataclass(frozen=True)
class Valuation:
    ev_low: float
    ev_high: float
    multiple_low: float
    multiple_high: float
    ebitda_basis: float


@lru_cache(maxsize=1)
def load_multiples(path: Path = MULTIPLES_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _round_ev(value: float) -> float:
    if value < 10_000_000:
        step = 100_000
    elif value < 100_000_000:
        step = 1_000_000
    else:
        step = 5_000_000
    return round(value / step) * step


def indicative_value(sector: str, ebitda_band: str, table: dict | None = None) -> Valuation | None:
    """Return an EV range, or ``None`` when EBITDA is not positive (multiples are not meaningful)."""
    table = table or load_multiples()
    band = EBITDA_BY_ID[ebitda_band]
    if band.high <= 0:
        return None
    low, high = table["sectors"][sector]
    adj = table["size_adjustment"].get(ebitda_band, 0.0)
    m_low, m_high = max(MIN_MULTIPLE, low + adj), max(MIN_MULTIPLE, high + adj)
    basis = band.mid
    return Valuation(
        ev_low=_round_ev(basis * m_low),
        ev_high=_round_ev(basis * m_high),
        multiple_low=m_low,
        multiple_high=m_high,
        ebitda_basis=basis,
    )
