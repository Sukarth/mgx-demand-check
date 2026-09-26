"""Match an owner's company profile against buyer criteria.

Pure functions only. The public view applies a privacy threshold so that no
individual buyer can be inferred from small counts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from .buyers import Buyer
from .sectors import EBITDA_BY_ID, REVENUE_BY_ID, Band, expand_regions

PRIVACY_THRESHOLD = 5
RECENT_DAYS = 90


@dataclass(frozen=True)
class OwnerProfile:
    sector: str
    country: str
    revenue_band: str
    ebitda_band: str

    @property
    def revenue(self) -> Band:
        return REVENUE_BY_ID[self.revenue_band]

    @property
    def ebitda(self) -> Band:
        return EBITDA_BY_ID[self.ebitda_band]


@dataclass
class MatchResult:
    total: int
    by_type: dict[str, int]
    by_hq: dict[str, int]
    appetite_eur: float
    recent: int
    buyer_ids: list[str] = field(default_factory=list)


def _overlaps(band: Band, lo: float, hi: float) -> bool:
    return band.low <= hi and band.high > lo


def buyer_matches(buyer: Buyer, owner: OwnerProfile) -> bool:
    if not buyer.active:
        return False
    if owner.sector not in buyer.target_sectors:
        return False
    if owner.country not in expand_regions(buyer.target_countries):
        return False
    if not _overlaps(owner.revenue, buyer.revenue_min, buyer.revenue_max):
        return False
    if buyer.is_pe and owner.ebitda.high <= 0:
        return False
    return _overlaps(owner.ebitda, buyer.ebitda_min, buyer.ebitda_max)


def match(buyers: list[Buyer], owner: OwnerProfile, today: date | None = None) -> MatchResult:
    today = today or date.today()
    cutoff = (today - timedelta(days=RECENT_DAYS)).isoformat()
    hits = [b for b in buyers if buyer_matches(b, owner)]
    return MatchResult(
        total=len(hits),
        by_type=dict(Counter(b.display_type for b in hits).most_common()),
        by_hq=dict(Counter(b.hq_country for b in hits).most_common()),
        appetite_eur=sum(b.appetite_eur for b in hits),
        recent=sum(1 for b in hits if b.added_at >= cutoff),
        buyer_ids=[b.id for b in hits],
    )


@dataclass(frozen=True)
class Count:
    """A count safe for public display: exact at or above the threshold, else ``fewer than N``."""
    value: int | None  # ``None`` means below the threshold (and above zero)
    zero: bool = False

    @property
    def below_threshold(self) -> bool:
        return self.value is None and not self.zero


def safe_count(n: int, threshold: int = PRIVACY_THRESHOLD) -> Count:
    if n <= 0:
        return Count(0, zero=True)
    return Count(n if n >= threshold else None)


def _safe_groups(counts: dict[str, int], threshold: int) -> list[tuple[str, Count]]:
    """Keep groups at or above the threshold; pool the rest into ``other``."""
    shown = [(k, Count(v)) for k, v in counts.items() if v >= threshold]
    rest = sum(v for v in counts.values() if v < threshold)
    if rest:
        shown.append(("other", safe_count(rest, threshold)))
    return shown


@dataclass
class PublicView:
    total: Count
    by_type: list[tuple[str, Count]]
    by_hq: list[tuple[str, Count]]
    appetite_eur: float | None  # rounded; ``None`` when the total is below the threshold
    recent: Count


def round_appetite(value: float) -> float:
    if value >= 1000 * 1_000_000:
        step = 100 * 1_000_000
    elif value >= 100 * 1_000_000:
        step = 10 * 1_000_000
    else:
        step = 1_000_000
    return float(int(value // step) * step)


def public_view(result: MatchResult, threshold: int = PRIVACY_THRESHOLD) -> PublicView:
    total = safe_count(result.total, threshold)
    hidden = result.total < threshold
    return PublicView(
        total=total,
        by_type=[] if hidden else _safe_groups(result.by_type, threshold),
        by_hq=[] if hidden else _safe_groups(result.by_hq, threshold),
        appetite_eur=None if hidden else round_appetite(result.appetite_eur),
        recent=safe_count(result.recent, threshold),
    )


def sector_count(buyers: list[Buyer], sector: str, countries: set[str] | None = None) -> int:
    """Active buyers targeting a sector, optionally restricted to buyers covering given countries."""
    n = 0
    for b in buyers:
        if not b.active or sector not in b.target_sectors:
            continue
        if countries and not (expand_regions(b.target_countries) & countries):
            continue
        n += 1
    return n
