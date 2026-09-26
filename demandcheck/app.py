"""FastAPI application: public owner flow and the internal advisor dashboard."""

from __future__ import annotations

import hmac
import json
import os
import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import briefs, letters, nurture, registry
from .buyers import BUYER_TYPES, Buyer, buyer_from_criteria, load_buyers
from .consent import CHANNELS, CONSENT_VERSION, consent_text, parse_optin
from .i18n import (
    LANGUAGE_NAMES, available_languages, format_eur, format_int, is_sectors_segment, pick_language,
    resolve_sector_slug, sector_path, sectors_segment, translate,
)
from .llm import LLMClient
from .matching import OwnerProfile, match, public_view, sector_count
from .sectors import (
    COUNTRIES, EBITDA_BANDS, EBITDA_BY_ID, OWNERSHIP_OPTIONS, REGIONS, REVENUE_BANDS,
    REVENUE_BY_ID, SECTOR_IDS, SECTORS_BY_ID, TIMING_OPTIONS, M,
)
from .store import STATUSES, Store
from .valuation import indicative_value

ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT.parent / ".env")

app = FastAPI(title="MGX Demand Check", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
                   same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")
public = APIRouter()

store = Store()
llm = LLMClient(cache=store)
BASE_BUYERS: list[Buyer] = load_buyers()


def current_buyers() -> list[Buyer]:
    return BASE_BUYERS + [Buyer.from_dict(d) for d in store.added_buyers()]


def dashboard_password() -> str:
    return os.environ.get("DASHBOARD_PASSWORD") or "mergero-demo"


# Template helpers --------------------------------------------------------

def render(request: Request, name: str, lang: str = "en", status_code: int = 200, **ctx) -> HTMLResponse:
    def t(key: str, **params) -> str:
        return translate(lang, key, **params)

    ctx.update(
        request=request, lang=lang, t=t, languages=available_languages(),
        language_names=LANGUAGE_NAMES, eur=lambda v: format_eur(v, lang),
        num=lambda v: format_int(v, lang),
        sector_url=lambda sector=None, country=None: sector_path(lang, sector, country),
    )
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _lang_or_404(lang: str) -> str:
    if lang not in available_languages():
        raise HTTPException(404)
    return lang


def form_options() -> dict:
    return dict(sectors=SECTOR_IDS, countries=COUNTRIES, revenue_bands=[b.id for b in REVENUE_BANDS],
                ebitda_bands=[b.id for b in EBITDA_BANDS], timings=TIMING_OPTIONS,
                ownerships=OWNERSHIP_OPTIONS)


# Public owner flow ---------------------------------------------------------

@app.get("/", include_in_schema=False)
def root(request: Request):
    return RedirectResponse(f"/{pick_language(request.headers.get('accept-language'))}", 302)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@public.get("/{lang}", response_class=HTMLResponse)
def check_form(request: Request, lang: str, sector: str = "", country: str = ""):
    lang = _lang_or_404(lang)
    values = {"sector": sector if sector in SECTORS_BY_ID else "",
              "country": country if country in COUNTRIES else ""}
    return render(request, "check.html", lang, values=values, errors=[], **form_options())


@public.post("/{lang}/check")
def submit_check(request: Request, lang: str, sector: str = Form(""), country: str = Form(""),
                 revenue_band: str = Form(""), ebitda_band: str = Form(""),
                 timing: str = Form(""), ownership: str = Form(""), source: str = Form("")):
    lang = _lang_or_404(lang)
    valid = (sector in SECTORS_BY_ID and country in COUNTRIES
             and revenue_band in REVENUE_BY_ID and ebitda_band in EBITDA_BY_ID)
    if not valid:
        values = dict(sector=sector, country=country, revenue_band=revenue_band,
                      ebitda_band=ebitda_band, timing=timing, ownership=ownership)
        return render(request, "check.html", lang, status_code=422, values=values,
                      errors=["form.error_required"], **form_options())
    result = match(current_buyers(), OwnerProfile(sector, country, revenue_band, ebitda_band))
    check_id = store.add_check(
        lang=lang, sector=sector, country=country, revenue_band=revenue_band,
        ebitda_band=ebitda_band, timing=timing if timing in TIMING_OPTIONS else None,
        ownership=ownership if ownership in OWNERSHIP_OPTIONS else None,
        source=source[:40] or None, match_total=result.total)
    return RedirectResponse(f"/{lang}/result/{check_id}", 303)


def _result_context(check: dict) -> dict:
    profile = OwnerProfile(check["sector"], check["country"], check["revenue_band"], check["ebitda_band"])
    result = match(current_buyers(), profile)
    view = public_view(result)
    max_type = max((c.value or 0 for _, c in view.by_type), default=1) or 1
    return dict(check=check, view=view, max_type=max_type,
                valuation=indicative_value(check["sector"], check["ebitda_band"]),
                channels=CHANNELS)


@public.get("/{lang}/result/{check_id}", response_class=HTMLResponse)
def result_page(request: Request, lang: str, check_id: str):
    lang = _lang_or_404(lang)
    check = store.get_check(check_id)
    if not check:
        raise HTTPException(404)
    return render(request, "result.html", lang, optin={}, errors=[], **_result_context(check))


@public.post("/{lang}/result/{check_id}/optin")
async def submit_optin(request: Request, lang: str, check_id: str):
    lang = _lang_or_404(lang)
    check = store.get_check(check_id)
    if not check:
        raise HTTPException(404)
    form = dict(await request.form())
    data = parse_optin(form)
    if data.errors:
        return render(request, "result.html", lang, status_code=422, optin=form,
                      errors=data.errors, **_result_context(check))
    profile = OwnerProfile(check["sector"], check["country"], check["revenue_band"], check["ebitda_band"])
    snap = nurture.snapshot(match(current_buyers(), profile))
    owner = store.add_owner(
        check_id=check_id, lang=lang, name=data.name, email=data.email, phone=data.phone,
        company=data.company, snapshot=snap,
        consents=[(ch, consent_text(lang, ch), CONSENT_VERSION) for ch in data.channels],
        needs_confirmation=data.needs_email_confirmation)
    request.session["thanks"] = {"owner_id": owner["id"]}
    return RedirectResponse(f"/{lang}/thanks", 303)


@public.get("/{lang}/thanks", response_class=HTMLResponse)
def thanks(request: Request, lang: str):
    lang = _lang_or_404(lang)
    info = request.session.get("thanks") or {}
    owner = store.get_owner(info.get("owner_id")) if info.get("owner_id") else None
    if not owner:
        return RedirectResponse(f"/{lang}", 302)
    confirm_url = (str(request.url_for("confirm_email", token=owner["confirm_token"]))
                   if owner["confirm_token"] else None)
    return render(request, "thanks.html", lang, owner=owner, confirm_url=confirm_url,
                  channels=sorted(store.active_channels(owner["id"]), key=CHANNELS.index))


@app.get("/confirm/{token}", response_class=HTMLResponse, name="confirm_email")
def confirm_email(request: Request, token: str):
    owner = store.owner_by_confirm_token(token)
    if not owner:
        return render(request, "message.html", "en", status_code=404,
                      title_key="confirm.done_title", body_key="confirm.invalid")
    store.confirm_email(owner["id"])
    return render(request, "message.html", owner["lang"],
                  title_key="confirm.done_title", body_key="confirm.done_body")


@app.get("/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(request: Request, token: str):
    owner = store.owner_by_unsubscribe_token(token)
    if not owner:
        raise HTTPException(404)
    store.withdraw(owner["id"], "updates")
    return render(request, "message.html", owner["lang"], title_key="unsubscribe.title",
                  body_key="unsubscribe.body")


@public.get("/{lang}/privacy", response_class=HTMLResponse)
def privacy(request: Request, lang: str):
    return render(request, "privacy.html", _lang_or_404(lang))


EMBED_JS = """(function () {
  var script = document.currentScript;
  if (!script) return;
  var origin = new URL(script.src).origin;
  var lang = script.getAttribute('data-lang') || 'en';
  var partner = (script.getAttribute('data-partner') || 'partner').replace(/[^a-z0-9-]/gi, '').slice(0, 30);
  var frame = document.createElement('iframe');
  frame.src = origin + '/' + encodeURIComponent(lang) + '/embed?src=partner-' + partner;
  frame.title = 'MGX Demand Check';
  frame.loading = 'lazy';
  frame.style.cssText = 'width:100%;max-width:560px;border:0;height:640px;display:block';
  window.addEventListener('message', function (e) {
    if (e.origin === origin && e.data && e.data.mgxHeight) frame.style.height = e.data.mgxHeight + 'px';
  });
  script.parentNode.insertBefore(frame, script.nextSibling);
})();
"""


@app.get("/embed.js", include_in_schema=False)
def embed_js():
    return Response(EMBED_JS, media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=300"})


@public.get("/{lang}/embed", response_class=HTMLResponse)
def embed_form(request: Request, lang: str, src: str = "partner"):
    lang = _lang_or_404(lang)
    return render(request, "embed.html", lang, source=src[:40], **form_options())


@app.get("/demo/partner", response_class=HTMLResponse, include_in_schema=False)
def demo_partner(request: Request):
    return templates.TemplateResponse(request, "demo_partner.html", {"request": request})


@app.get("/api/prh/{business_id}")
def prh_lookup(business_id: str, lang: str = "fi"):
    """Look up a Finnish company to pre-fill the form; the ID is not stored."""
    lang = lang if lang in available_languages() else "fi"
    bid = registry.normalize_business_id(business_id)
    if not registry.valid_business_id(bid):
        return JSONResponse({"ok": False, "message": translate(lang, "form.lookup_invalid")}, 400)
    try:
        company = registry.lookup(bid, lang)
    except registry.RegistryUnavailable:
        return JSONResponse({"ok": False, "message": translate(lang, "form.lookup_error")}, 502)
    if company is None:
        return JSONResponse({"ok": False, "message": translate(lang, "form.lookup_not_found")}, 404)
    key = "form.lookup_found" if company.sector else "form.lookup_found_nosector"
    return {"ok": True, "name": company.name, "sector": company.sector, "country": "FI",
            "industry": company.industry_name, "message": translate(lang, key, name=company.name)}


@public.get("/{lang}/{segment}", response_class=HTMLResponse)
def sectors_index(request: Request, lang: str, segment: str):
    lang = _lang_or_404(lang)
    if not is_sectors_segment(segment):
        raise HTTPException(404)
    if segment != sectors_segment(lang):
        return RedirectResponse(sector_path(lang), 301)
    buyers = current_buyers()
    rows = sorted(((s, sector_count(buyers, s)) for s in SECTOR_IDS), key=lambda r: -r[1])
    return render(request, "sectors.html", lang, rows=rows)


@public.get("/{lang}/{segment}/{slug}", response_class=HTMLResponse)
def sector_page(request: Request, lang: str, segment: str, slug: str, country: str = ""):
    lang = _lang_or_404(lang)
    sector = resolve_sector_slug(slug, SECTOR_IDS) if is_sectors_segment(segment) else None
    if not sector:
        raise HTTPException(404)
    country = country if country in COUNTRIES else ""
    canonical = sector_path(lang, sector)
    if request.url.path != canonical:
        return RedirectResponse(sector_path(lang, sector, country or None), 301)
    buyers = current_buyers()
    per_country = [(c, sector_count(buyers, sector, {c})) for c in COUNTRIES]
    return render(request, "sector.html", lang, sector=sector, total=sector_count(buyers, sector),
                  per_country=per_country, country=country,
                  country_total=sector_count(buyers, sector, {country}) if country else None,
                  **form_options())


# Dashboard -----------------------------------------------------------------

def _authed(request: Request) -> bool:
    return request.session.get("dashboard") is True


def _require(request: Request) -> RedirectResponse | None:
    return None if _authed(request) else RedirectResponse("/dashboard/login", 303)


@app.get("/dashboard/login", response_class=HTMLResponse)
def login_form(request: Request):
    return render(request, "dashboard/login.html", error=False)


@app.post("/dashboard/login")
def login(request: Request, password: str = Form("")):
    if hmac.compare_digest(password.encode(), dashboard_password().encode()):
        request.session["dashboard"] = True
        return RedirectResponse("/dashboard", 303)
    return render(request, "dashboard/login.html", status_code=401, error=True)


@app.post("/dashboard/logout")
def logout(request: Request):
    request.session.pop("dashboard", None)
    return RedirectResponse("/dashboard/login", 303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if (r := _require(request)):
        return r
    owners = store.list_owners()
    for o in owners:
        o["channels"] = sorted(store.active_channels(o["id"]), key=CHANNELS.index)
    buyers = current_buyers()
    stats = dict(checks=store.count_checks(), owners=len(owners),
                 buyers=sum(b.active for b in buyers), added=len(store.added_buyers()),
                 appetite=sum(b.appetite_eur for b in buyers if b.active))
    flash = request.session.pop("flash", None)
    return render(request, "dashboard/index.html", owners=owners, stats=stats, flash=flash,
                  messages=store.messages()[:20], statuses=STATUSES, buyer_types=BUYER_TYPES,
                  regions=list(REGIONS), hq_countries=list(COUNTRIES) + ["GB", "US"],
                  **form_options())


@app.get("/dashboard/owners/{owner_id}", response_class=HTMLResponse)
def owner_detail(request: Request, owner_id: int):
    if (r := _require(request)):
        return r
    owner = store.get_owner(owner_id)
    if not owner:
        raise HTTPException(404)
    return render(request, "dashboard/owner.html", owner=owner, consents=store.consents(owner_id),
                  drafts=store.drafts(owner_id), statuses=STATUSES,
                  messages=store.messages(owner_id),
                  valuation=indicative_value(owner["sector"], owner["ebitda_band"]),
                  llm_ready=llm.available(), flash=request.session.pop("flash", None))


@app.post("/dashboard/owners/{owner_id}/status")
def owner_status(request: Request, owner_id: int, status: str = Form(...)):
    if (r := _require(request)):
        return r
    if status in STATUSES:
        store.set_status(owner_id, status)
    return RedirectResponse(f"/dashboard/owners/{owner_id}", 303)


@app.post("/dashboard/owners/{owner_id}/draft/{kind}")
def owner_draft(request: Request, owner_id: int, kind: str):
    if (r := _require(request)):
        return r
    if kind not in ("brief", "profile"):
        raise HTTPException(404)
    owner = store.get_owner(owner_id)
    if not owner:
        raise HTTPException(404)
    channels = sorted(store.active_channels(owner_id), key=CHANNELS.index)
    data, source = briefs.draft(kind, briefs.owner_facts(owner, channels), llm)
    store.save_draft(owner_id, kind, source, data)
    return RedirectResponse(f"/dashboard/owners/{owner_id}#{kind}", 303)


@app.get("/dashboard/owners/{owner_id}/consents.json")
def consent_export(request: Request, owner_id: int):
    if not _authed(request):
        raise HTTPException(401)
    owner = store.get_owner(owner_id)
    if not owner:
        raise HTTPException(404)
    payload = {
        "owner_id": owner_id, "name": owner["name"], "email": owner["email"], "phone": owner["phone"],
        "language": owner["lang"], "opted_in_at": owner["created_at"],
        "email_confirmed_at": owner["email_confirmed_at"], "consents": store.consents(owner_id),
    }
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="consent-proof-{owner_id}.json"'})


@app.post("/dashboard/buyers")
async def add_buyer(request: Request):
    """Record a new buyer, recompute matches and queue update emails for opted-in owners."""
    if (r := _require(request)):
        return r
    form = await request.form()
    sectors = [s for s in form.getlist("sectors") if s in SECTORS_BY_ID]
    targets = [c for c in form.getlist("targets") if c in REGIONS or c in COUNTRIES]
    kind = form.get("display_type") if form.get("display_type") in BUYER_TYPES else "pe_platform"
    try:
        ev_min = float(form.get("ev_min") or 5) * M
        ev_max = float(form.get("ev_max") or 40) * M
    except ValueError:
        ev_min, ev_max = 5 * M, 40 * M
    if not sectors or not targets or ev_min >= ev_max:
        request.session["flash"] = "Choose at least one sector and one target geography, and a valid EV range."
        return RedirectResponse("/dashboard#nurture", 303)
    buyer = buyer_from_criteria(
        f"N{len(store.added_buyers()) + 1:03d}", kind, str(form.get("hq_country") or "SE"),
        sectors, targets, ev_min, ev_max, appetite_eur=ev_max * 2)
    store.add_buyer(buyer.to_dict())
    queued = run_nurture(request)
    request.session["flash"] = (f"Buyer {buyer.id} added. {queued} buyer-demand update(s) queued "
                                "for opted-in owners.")
    return RedirectResponse("/dashboard#nurture", 303)


def run_nurture(request: Request) -> int:
    buyers = current_buyers()
    eligible = []
    for owner in store.list_owners():
        if "updates" in store.active_channels(owner["id"]) and owner["email_confirmed_at"]:
            eligible.append(owner)
    queued = 0
    for change in nurture.changes_for(eligible, buyers):
        owner = next(o for o in eligible if o["id"] == change.owner_id)
        result_url = str(request.base_url).rstrip("/") + f"/{owner['lang']}/result/{owner['check_id']}"
        unsub_url = str(request.url_for("unsubscribe", token=owner["unsubscribe_token"]))
        subject, body = nurture.update_email(owner, change, result_url, unsub_url)
        store.queue_message(owner["id"], "demand_update", subject, body)
        store.set_snapshot(owner["id"], nurture.snapshot(change.result))
        queued += 1
    return queued


LETTER_SAMPLE = ROOT.parent / "data" / "letter_targets_sample.csv"


@app.get("/dashboard/letters", response_class=HTMLResponse)
def letters_form(request: Request):
    if (r := _require(request)):
        return r
    csv_text = LETTER_SAMPLE.read_text(encoding="utf-8") if LETTER_SAMPLE.exists() else ""
    targets, errors = letters.parse_targets(csv_text)
    return render(request, "dashboard/letters.html", csv_text=csv_text, errors=errors,
                  preview=_letter_preview(request, targets))


def _letter_preview(request: Request, targets: list) -> list[dict]:
    buyers = current_buyers()
    base = str(request.base_url)
    return [{"target": t, "count": letters.letter_count(buyers, t),
             "url": letters.target_url(base, "de", t)} for t in targets]


@app.post("/dashboard/letters")
def letters_pdf(request: Request, csv_text: str = Form(""), action: str = Form("pdf")):
    if (r := _require(request)):
        return r
    targets, errors = letters.parse_targets(csv_text)
    if action != "pdf" or errors or not targets:
        return render(request, "dashboard/letters.html", csv_text=csv_text,
                      errors=errors or (["No valid rows."] if not targets else []),
                      preview=_letter_preview(request, targets))
    pdf = letters.render_letters(targets, current_buyers(), str(request.base_url), lang="de")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="letters-de.pdf"'})


@app.get("/dashboard/messages/{message_id}", response_class=HTMLResponse)
def message_preview(request: Request, message_id: int):
    if (r := _require(request)):
        return r
    message = store.get_message(message_id)
    if not message:
        raise HTTPException(404)
    return render(request, "dashboard/message.html", message=message)


# Language-prefixed routes are registered last so fixed paths above take precedence.
app.include_router(public)
