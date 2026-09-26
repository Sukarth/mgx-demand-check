"""Sectors, countries and size bands shared by the owner form, matching and valuation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sector:
    id: str
    nace: tuple[str, ...]
    weight: float  # relative share of buyers targeting the sector in the sample


SECTORS: tuple[Sector, ...] = (
    Sector("industrial_services", ("33", "43.2"), 1.4),
    Sector("technical_installation", ("43.21", "43.22", "43.29"), 1.4),
    Sector("facility_services", ("81.1", "81.2"), 1.1),
    Sector("logistics", ("49.4", "52.1", "52.29"), 1.3),
    Sector("waste_circular", ("38", "39"), 1.0),
    Sector("construction_services", ("41", "42", "43.3", "43.9"), 1.2),
    Sector("technical_wholesale", ("46.6", "46.7"), 1.0),
    Sector("software_it", ("62", "63.1"), 1.5),
    Sector("health_products", ("21", "32.5", "46.46"), 0.9),
    Sector("healthcare_services", ("86", "87"), 0.8),
    Sector("manufacturing", ("25", "28"), 1.0),
    Sector("food_production", ("10", "11"), 0.6),
    Sector("business_services", ("69", "70.2", "78", "82"), 0.9),
    Sector("engineering_consulting", ("71",), 0.9),
    Sector("retail_ecommerce", ("47",), 0.5),
)
SECTOR_IDS = tuple(s.id for s in SECTORS)
SECTORS_BY_ID = {s.id: s for s in SECTORS}

COUNTRIES = ("FI", "SE", "NO", "DK", "EE", "DE", "AT", "CH", "NL")

REGIONS: dict[str, tuple[str, ...]] = {
    "NORDICS": ("FI", "SE", "NO", "DK"),
    "BALTICS": ("EE",),
    "DACH": ("DE", "AT", "CH"),
    "BENELUX": ("NL",),
    "EUROPE": COUNTRIES,
}


def expand_regions(codes: list[str] | tuple[str, ...]) -> set[str]:
    """Expand region codes (``NORDICS``, ``DACH``...) into country codes."""
    out: set[str] = set()
    for code in codes:
        out.update(REGIONS.get(code, (code,)))
    return out


@dataclass(frozen=True)
class Band:
    id: str
    low: float   # EUR, inclusive
    high: float  # EUR, exclusive; ``inf`` for open-ended

    @property
    def mid(self) -> float:
        if self.high == float("inf"):
            return self.low * 1.5
        if self.low < 0:
            return self.low / 2 if self.high <= 0 else 0.0
        return (self.low + self.high) / 2


M = 1_000_000
INF = float("inf")

REVENUE_BANDS: tuple[Band, ...] = (
    Band("r_lt2", 0, 2 * M),
    Band("r_2_5", 2 * M, 5 * M),
    Band("r_5_10", 5 * M, 10 * M),
    Band("r_10_20", 10 * M, 20 * M),
    Band("r_20_50", 20 * M, 50 * M),
    Band("r_50_100", 50 * M, 100 * M),
    Band("r_100p", 100 * M, INF),
)

EBITDA_BANDS: tuple[Band, ...] = (
    Band("e_neg", -5 * M, 0),
    Band("e_0_05", 0, 0.5 * M),
    Band("e_05_1", 0.5 * M, 1 * M),
    Band("e_1_2", 1 * M, 2 * M),
    Band("e_2_5", 2 * M, 5 * M),
    Band("e_5_10", 5 * M, 10 * M),
    Band("e_10_20", 10 * M, 20 * M),
    Band("e_20p", 20 * M, INF),
)

REVENUE_BY_ID = {b.id: b for b in REVENUE_BANDS}
EBITDA_BY_ID = {b.id: b for b in EBITDA_BANDS}

TIMING_OPTIONS = ("now", "1_2y", "3y_plus", "curious")
OWNERSHIP_OPTIONS = ("100", "50_99", "lt50")
