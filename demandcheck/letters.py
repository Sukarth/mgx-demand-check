"""Personalised postal letters with a QR code to the matching sector page.

Postal mail is the channel for a first, unsolicited contact with companies in
Germany, Austria and Switzerland. Each letter states the live buyer count for
the recipient's sector and country, links to the anonymous check and carries
the GDPR Art. 14 information about where the address came from.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .buyers import Buyer
from .i18n import format_int, resolve_sector_slug, sector_path, translate
from .matching import PRIVACY_THRESHOLD, sector_count
from .sectors import COUNTRIES, SECTOR_IDS

CSV_FIELDS = ("company", "contact", "street", "postcode", "city", "country", "sector")
MONTHS_DE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
             "September", "Oktober", "November", "Dezember")


@dataclass(frozen=True)
class Target:
    company: str
    contact: str
    street: str
    postcode: str
    city: str
    country: str
    sector: str


def parse_targets(text: str) -> tuple[list[Target], list[str]]:
    """Parse CSV rows (header ``company,contact,street,postcode,city,country,sector``).

    The sector may be given as an id or as a sector name slug in any language.
    Returns the valid targets and one error message per rejected row.
    """
    reader = csv.DictReader(io.StringIO(text.strip()))
    missing = [f for f in CSV_FIELDS if f not in (reader.fieldnames or [])]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}"]
    targets, errors = [], []
    for n, row in enumerate(reader, start=2):
        row = {k: (v or "").strip() for k, v in row.items() if k}
        country = row["country"].upper()
        sector = resolve_sector_slug(row["sector"].lower().replace(" ", "-"), SECTOR_IDS)
        if not row["company"] or country not in COUNTRIES or not sector:
            errors.append(f"Row {n}: needs a company, a known country code and a known sector")
            continue
        targets.append(Target(row["company"], row["contact"], row["street"], row["postcode"],
                              row["city"], country, sector))
    return targets, errors


def letter_date(d: date, lang: str) -> str:
    if lang == "de":
        return f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"
    return d.strftime("%d %B %Y")


def target_url(base_url: str, lang: str, target: Target) -> str:
    return f"{base_url.rstrip('/')}{sector_path(lang, target.sector, target.country)}&src=letter"


def letter_count(buyers: list[Buyer], target: Target) -> int:
    return sector_count(buyers, target.sector, {target.country})


def _qr_image(url: str) -> ImageReader:
    img = qrcode.make(url, box_size=8, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _wrap(c: canvas.Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if c.stringWidth(trial, font, size) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _paragraph(c: canvas.Canvas, text: str, x: float, y: float, width: float,
               font: str = "Helvetica", size: float = 10.5, leading: float = 14.5) -> float:
    c.setFont(font, size)
    for line in _wrap(c, text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y - leading * 0.5


def render_letters(targets: list[Target], buyers: list[Buyer], base_url: str,
                   lang: str = "de", today: date | None = None) -> bytes:
    """One A4 page per target, as a single PDF."""
    today = today or date.today()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Letters")
    page_w, page_h = A4
    left, right = 25 * mm, 20 * mm
    width = page_w - left - right
    privacy_url = f"{base_url.rstrip('/')}/{lang}/privacy"

    for target in targets:
        n = letter_count(buyers, target)
        count_text = (format_int(n, lang) if n >= PRIVACY_THRESHOLD
                      else translate(lang, "result.fewer_than", n=PRIVACY_THRESHOLD).lower())
        sector = translate(lang, f"sector.{target.sector}")
        country = translate(lang, f"country.{target.country}")
        url = target_url(base_url, lang, target)

        # Sender line and address block positioned for a DIN 5008 window envelope.
        c.setFont("Helvetica", 7.5)
        c.setFillGray(0.35)
        c.drawString(left, page_h - 50 * mm, "Mergero · Frankfurt am Main")
        c.setFillGray(0)
        y = page_h - 56 * mm
        c.setFont("Helvetica", 10.5)
        for line in (target.company, target.contact, target.street,
                     f"{target.postcode} {target.city}".strip(), country.upper()):
            if line:
                c.drawString(left, y, line)
                y -= 13
        c.setFont("Helvetica", 10.5)
        c.drawRightString(page_w - right, page_h - 98 * mm, f"Frankfurt am Main, {letter_date(today, lang)}")

        y = page_h - 110 * mm
        y = _paragraph(c, translate(lang, "letter.subject", n=count_text, sector=sector, country=country),
                       left, y, width, font="Helvetica-Bold", size=11.5, leading=15)
        greeting = (translate(lang, "letter.greeting", name=target.contact) if target.contact
                    else translate(lang, "letter.greeting_generic"))
        y = _paragraph(c, greeting, left, y, width)
        y = _paragraph(c, translate(lang, "letter.p1", n=count_text, sector=sector, country=country),
                       left, y, width)
        y = _paragraph(c, translate(lang, "letter.p2"), left, y, width)

        qr_size = 32 * mm
        c.drawImage(_qr_image(url), left, y - qr_size + 4 * mm, qr_size, qr_size)
        c.setFont("Helvetica", 10)
        c.drawString(left + qr_size + 6 * mm, y - 6 * mm, translate(lang, "letter.cta"))
        url_width = width - qr_size - 6 * mm
        url_size = 9.0
        while url_size > 6 and c.stringWidth(url, "Helvetica-Bold", url_size) > url_width:
            url_size -= 0.5
        c.setFont("Helvetica-Bold", url_size)
        c.drawString(left + qr_size + 6 * mm, y - 12 * mm, url)
        y -= qr_size + 4 * mm

        y = _paragraph(c, translate(lang, "letter.p3"), left, y, width)
        y = _paragraph(c, translate(lang, "letter.signoff"), left, y, width)
        _paragraph(c, "Mergero", left, y - 2, width, font="Helvetica-Bold")

        c.setFillGray(0.35)
        foot_y = 30 * mm
        foot_y = _paragraph(c, translate(lang, "letter.art14", privacy_url=privacy_url),
                            left, foot_y, width, size=7.5, leading=9.5)
        _paragraph(c, translate(lang, "letter.sample"), left, foot_y + 3, width, size=7.5, leading=9.5)
        c.setFillGray(0)
        c.showPage()

    c.save()
    return buf.getvalue()
