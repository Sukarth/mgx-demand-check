import pytest

from demandcheck.sectors import EBITDA_BANDS, SECTOR_IDS
from demandcheck.valuation import indicative_value, load_multiples


def test_every_sector_has_multiples():
    assert set(load_multiples()["sectors"]) == set(SECTOR_IDS)


def test_negative_ebitda_has_no_multiple_valuation():
    assert indicative_value("logistics", "e_neg") is None


def test_logistics_1_2m():
    v = indicative_value("logistics", "e_1_2")
    # Mid 1.5M EBITDA, multiples 4.5-0.5 and 6.5-0.5.
    assert (v.multiple_low, v.multiple_high) == (4.0, 6.0)
    assert (v.ev_low, v.ev_high) == (6_000_000, 9_000_000)


def test_software_valued_above_cleaning():
    assert indicative_value("software_it", "e_2_5").ev_low > indicative_value("facility_services", "e_2_5").ev_high


@pytest.mark.parametrize("band", [b.id for b in EBITDA_BANDS if b.high > 0])
@pytest.mark.parametrize("sector", SECTOR_IDS)
def test_range_is_ordered_and_positive(sector, band):
    v = indicative_value(sector, band)
    assert 0 < v.ev_low < v.ev_high
    assert v.multiple_low >= 2.0


def test_larger_companies_get_higher_multiples():
    small = indicative_value("logistics", "e_05_1")
    large = indicative_value("logistics", "e_10_20")
    assert large.multiple_low > small.multiple_low
