from datetime import date

from demandcheck import letters
from demandcheck.buyers import load_buyers

CSV = """company,contact,street,postcode,city,country,sector
Muster GmbH,Max Mustermann,Beispielstraße 1,80331,München,DE,technical_installation
Beispiel AG,,Weg 2,8001,Zürich,CH,logistik-und-transport
Broken Ltd,,,,,XX,logistics
"""


def test_parse_targets_accepts_ids_and_localized_slugs():
    targets, errors = letters.parse_targets(CSV)
    assert [t.sector for t in targets] == ["technical_installation", "logistics"]
    assert len(errors) == 1 and "Row 4" in errors[0]


def test_parse_targets_reports_missing_columns():
    targets, errors = letters.parse_targets("company,city\nA,B\n")
    assert not targets and "Missing columns" in errors[0]


def test_target_url_points_to_localized_sector_page():
    targets, _ = letters.parse_targets(CSV)
    assert letters.target_url("https://x.test/", "de", targets[0]) == (
        "https://x.test/de/branchen/elektro-und-gebaudetechnik?country=DE&src=letter")


def test_render_letters_one_page_per_target():
    targets, _ = letters.parse_targets(CSV)
    pdf = letters.render_letters(targets, load_buyers(), "https://x.test", today=date(2026, 9, 27))
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 2


def test_german_date():
    assert letters.letter_date(date(2026, 3, 1), "de") == "1. März 2026"
