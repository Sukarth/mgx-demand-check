from datetime import date

import pytest

from demandcheck.buyers import Buyer, generate_sample
from demandcheck.matching import (
    OwnerProfile, buyer_matches, match, public_view, round_appetite, safe_count, sector_count,
)

M = 1_000_000


def make_buyer(**overrides) -> Buyer:
    base = dict(
        id="T1", display_type="pe_platform", hq_country="SE",
        target_sectors=["logistics"], target_countries=["NORDICS"],
        revenue_min=5 * M, revenue_max=50 * M, ebitda_min=1 * M, ebitda_max=5 * M,
        ev_min=6 * M, ev_max=30 * M, deal_types=["majority"], appetite_eur=20 * M,
        active=True, added_at="2026-09-01",
    )
    base.update(overrides)
    return Buyer(**base)


OWNER = OwnerProfile("logistics", "FI", "r_10_20", "e_1_2")


def test_matching_buyer():
    assert buyer_matches(make_buyer(), OWNER)


@pytest.mark.parametrize("override", [
    {"active": False},
    {"target_sectors": ["software_it"]},
    {"target_countries": ["DACH"]},
    {"revenue_min": 25 * M},
    {"revenue_max": 8 * M},
    {"ebitda_min": 3 * M},
])
def test_non_matching_buyer(override):
    assert not buyer_matches(make_buyer(**override), OWNER)


def test_region_expands_and_country_code_matches():
    assert buyer_matches(make_buyer(target_countries=["FI"]), OWNER)
    assert buyer_matches(make_buyer(target_countries=["EUROPE"]), OWNER)


def test_band_edges_are_half_open():
    # Owner revenue band is [10M, 20M): a buyer starting exactly at 20M does not overlap.
    assert not buyer_matches(make_buyer(revenue_min=20 * M), OWNER)
    assert buyer_matches(make_buyer(revenue_max=10 * M), OWNER)


def test_pe_requires_positive_ebitda_but_strategic_may_not():
    loss_owner = OwnerProfile("logistics", "FI", "r_10_20", "e_neg")
    assert not buyer_matches(make_buyer(ebitda_min=-2 * M), loss_owner)
    assert buyer_matches(make_buyer(display_type="strategic", ebitda_min=-2 * M), loss_owner)


def test_match_aggregates():
    buyers = [
        make_buyer(id="A"),
        make_buyer(id="B", display_type="strategic", hq_country="DE", added_at="2025-01-01"),
        make_buyer(id="C", active=False),
    ]
    r = match(buyers, OWNER, today=date(2026, 9, 26))
    assert r.total == 2
    assert r.by_type == {"pe_platform": 1, "strategic": 1}
    assert r.by_hq == {"SE": 1, "DE": 1}
    assert r.appetite_eur == 40 * M
    assert r.recent == 1
    assert r.buyer_ids == ["A", "B"]


def test_safe_count_threshold():
    assert safe_count(0).zero
    assert safe_count(3).below_threshold
    assert safe_count(5).value == 5


def test_public_view_hides_small_groups():
    buyers = [make_buyer(id=f"P{i}") for i in range(6)]
    buyers += [make_buyer(id=f"S{i}", display_type="strategic", hq_country="DE") for i in range(2)]
    buyers += [make_buyer(id=f"F{i}", display_type="family_office", hq_country="NO") for i in range(2)]
    view = public_view(match(buyers, OWNER))
    assert view.total.value == 10
    types = dict(view.by_type)
    assert types["pe_platform"].value == 6
    assert "strategic" not in types and "family_office" not in types
    assert types["other"].value is None and types["other"].below_threshold
    hq = dict(view.by_hq)
    assert hq["SE"].value == 6 and hq["other"].below_threshold


def test_public_view_below_threshold_hides_everything():
    view = public_view(match([make_buyer(id="A"), make_buyer(id="B")], OWNER))
    assert view.total.below_threshold
    assert view.by_type == [] and view.by_hq == [] and view.appetite_eur is None


def test_round_appetite_never_rounds_up():
    assert round_appetite(1_234_567_890) == 1_200_000_000
    assert round_appetite(456 * M + 1) == 450 * M
    assert round_appetite(7.9 * M) == 7 * M


def test_sector_count_with_country_filter():
    buyers = [make_buyer(id="A"), make_buyer(id="B", target_countries=["DACH"])]
    assert sector_count(buyers, "logistics") == 2
    assert sector_count(buyers, "logistics", {"DE"}) == 1
    assert sector_count(buyers, "software_it") == 0


def test_sample_is_deterministic_and_matches_stated_scale():
    a, b = generate_sample(n=300), generate_sample(n=300)
    assert [x.to_dict() for x in a] == [x.to_dict() for x in b]
    full = generate_sample()
    assert len(full) == 2000
    assert abs(sum(x.appetite_eur for x in full) - 52_000 * M) < 1_000 * M
    share = {k: sum(x.display_type == k for x in full) / len(full) for k in
             ("pe_platform", "pe_addon", "strategic", "family_office", "search_fund")}
    assert abs(share["pe_platform"] + share["pe_addon"] - 0.55) < 0.01
    assert abs(share["strategic"] - 0.25) < 0.01
    assert abs(share["family_office"] - 0.12) < 0.01
    assert abs(share["search_fund"] - 0.08) < 0.01
    assert all(1 <= len(x.target_sectors) <= 3 and 1 <= len(x.target_countries) <= 3 for x in full)
    assert all(x.ebitda_min > 0 for x in full if x.is_pe)
    assert all(x.revenue_min < x.revenue_max and x.ev_min < x.ev_max for x in full)


@pytest.mark.parametrize("profile,low,high", [
    (("logistics", "FI", "r_10_20", "e_1_2"), 40, 60),
    (("technical_installation", "DE", "r_20_50", "e_2_5"), 30, 70),
    (("technical_installation", "DE", "r_50_100", "e_5_10"), 30, 70),
    (("software_it", "FI", "r_5_10", "e_1_2"), 30, 70),
    (("facility_services", "FI", "r_5_10", "e_05_1"), 10, 40),
    (("retail_ecommerce", "AT", "r_2_5", "e_0_05"), 0, 4),
])
def test_sample_counts_are_realistic(profile, low, high):
    from demandcheck.buyers import load_buyers
    assert low <= match(load_buyers(), OwnerProfile(*profile)).total <= high
