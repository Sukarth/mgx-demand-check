import re

import pytest
from fastapi.testclient import TestClient

from demandcheck import app as app_module
from demandcheck.consent import CONSENT_VERSION, parse_optin

CHECK = {"sector": "logistics", "country": "FI", "revenue_band": "r_10_20",
         "ebitda_band": "e_1_2", "timing": "1_2y", "ownership": "100"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(app_module.llm, "models", [])  # force template drafts, no network
    return TestClient(app_module.app)


def run_check(client, lang="en"):
    r = client.post(f"/{lang}/check", data=CHECK, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


def test_root_redirects_by_browser_language(client):
    r = client.get("/", headers={"accept-language": "de-DE,de;q=0.9"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] in ("/de", "/en")


def test_unknown_language_is_404(client):
    assert client.get("/xx").status_code == 404


def test_check_requires_four_answers(client):
    r = client.post("/en/check", data={"sector": "logistics"})
    assert r.status_code == 422
    assert "Please answer the four required questions" in r.text


def test_result_shown_without_personal_data(client):
    page = client.get(run_check(client))
    assert page.status_code == 200
    assert "buyers in our network are looking" in page.text
    assert "Illustrative sample data" in page.text
    assert "Indicative value range" in page.text
    # Consent boxes exist and none is pre-ticked.
    boxes = re.findall(r'<input type="checkbox" name="consent_\w+"[^>]*>', page.text)
    assert len(boxes) == 5 and not any("checked" in b for b in boxes)


def test_optin_validation(client):
    url = run_check(client)
    r = client.post(f"{url}/optin", data={"name": "A", "consent_phone": "yes"})
    assert r.status_code == 422
    assert "Please give an email address or a phone number" in r.text


def test_full_owner_and_advisor_flow(client):
    url = run_check(client)
    r = client.post(f"{url}/optin", data={
        "name": "Aino Virtanen", "email": "aino@example.com", "phone": "+358 40 000 0000",
        "company": "Example Logistics Oy", "consent_phone": "yes", "consent_updates": "yes",
        "consent_sms": "no"}, follow_redirects=True)
    assert r.status_code == 200
    assert "confirm your email" in r.text
    token = re.search(r"/confirm/([\w-]+)", r.text).group(1)

    owner = next(o for o in app_module.store.list_owners() if o["email"] == "aino@example.com")
    consents = app_module.store.consents(owner["id"])
    assert {c["channel"] for c in consents} == {"phone", "updates"}
    assert all(c["text_version"] == CONSENT_VERSION and c["granted_at"] for c in consents)

    assert "Email confirmed" in client.get(f"/confirm/{token}").text
    assert "not valid" in client.get(f"/confirm/{token}").text

    # Dashboard requires login.
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    assert client.post("/dashboard/login", data={"password": "wrong"}).status_code == 401
    client.post("/dashboard/login", data={"password": "test-password"})
    dash = client.get("/dashboard")
    assert "Aino Virtanen" in dash.text

    detail = client.get(f"/dashboard/owners/{owner['id']}")
    assert "Consent proof" in detail.text and CONSENT_VERSION in detail.text

    client.post(f"/dashboard/owners/{owner['id']}/draft/brief")
    client.post(f"/dashboard/owners/{owner['id']}/draft/profile")
    drafts = app_module.store.drafts(owner["id"])
    assert drafts["brief"]["model"] == "template" and drafts["brief"]["data"]["questions"]
    assert "Example Logistics" not in str(drafts["profile"]["data"])

    proof = client.get(f"/dashboard/owners/{owner['id']}/consents.json").json()
    assert proof["email_confirmed_at"] and len(proof["consents"]) == 2

    before = app_module.store.get_owner(owner["id"])["snapshot"]["total"]
    r = client.post("/dashboard/buyers", data={
        "display_type": "pe_platform", "hq_country": "SE", "sectors": "logistics",
        "targets": "FI", "ev_min": "5", "ev_max": "40"}, follow_redirects=True)
    assert "update(s) queued" in r.text
    msgs = app_module.store.messages(owner["id"])
    assert msgs and "1 new buyer" in msgs[0]["subject"]
    assert app_module.store.get_owner(owner["id"])["snapshot"]["total"] == before + 1
    assert "/unsubscribe/" in msgs[0]["body"]


def test_sector_pages_localized(client):
    assert "Logistics and transport" in client.get("/en/sectors").text
    assert "Logistiikka ja kuljetus" in client.get("/fi/toimialat/logistiikka-ja-kuljetus").text
    r = client.get("/de/toimialat/logistiikka-ja-kuljetus?country=DE", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/de/branchen/logistik-und-transport?country=DE"
    assert client.get("/en/sectors/logistics", follow_redirects=False).status_code == 301
    assert client.get("/en/sectors/nope").status_code == 404
    assert client.get("/en/nope").status_code == 404


@pytest.mark.parametrize("lang,text", [("fi", "Kuka ostaisi yrityksesi?"), ("de", "Wer würde Ihr Unternehmen kaufen?"),
                                       ("sv", "Vem skulle köpa ditt företag?")])
def test_translated_owner_pages(client, lang, text):
    page = client.get(f"/{lang}")
    assert text in page.text and f'lang="{lang}"' in page.text
    result = client.get(run_check(client, lang))
    assert result.status_code == 200 and "checkbox" in result.text


def test_prh_lookup_endpoint(client, monkeypatch):
    from demandcheck import registry
    company = registry.Company("0536104-0", "Example Oy", "49410", "Freight", "logistics")
    monkeypatch.setattr(registry, "lookup", lambda bid, lang="fi": company)
    data = client.get("/api/prh/0536104-0?lang=fi").json()
    assert data["ok"] and data["sector"] == "logistics" and "Example Oy" in data["message"]
    assert client.get("/api/prh/1234567-8").status_code == 400
    monkeypatch.setattr(registry, "lookup", lambda bid, lang="fi": None)
    assert client.get("/api/prh/0536104-0").status_code == 404


def test_parse_optin_only_counts_explicit_yes():
    data = parse_optin({"email": "a@b.fi", "consent_email": "on", "consent_updates": "yes"})
    assert data.channels == ["updates"]
    assert parse_optin({"email": "a@b.fi"}).errors == ["optin.error_no_consent"]
    assert "optin.error_phone_needed" in parse_optin({"email": "a@b.fi", "consent_sms": "yes"}).errors


def test_letters_page_and_pdf(client):
    assert client.get("/dashboard/letters", follow_redirects=False).status_code == 303
    client.post("/dashboard/login", data={"password": "test-password"})
    page = client.get("/dashboard/letters")
    assert "Muster Elektrotechnik GmbH" in page.text
    csv_text = app_module.LETTER_SAMPLE.read_text(encoding="utf-8")
    r = client.post("/dashboard/letters", data={"csv_text": csv_text, "action": "pdf"})
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    bad = client.post("/dashboard/letters", data={"csv_text": "nope", "action": "pdf"})
    assert "Missing columns" in bad.text


def test_embed_widget(client):
    js = client.get("/embed.js")
    assert js.headers["content-type"].startswith("application/javascript") and "iframe" in js.text
    form = client.get("/fi/embed?src=partner-tilitoimisto")
    assert 'target="_blank"' in form.text and 'value="partner-tilitoimisto"' in form.text
    assert "/embed.js" in client.get("/demo/partner").text
    r = client.post("/fi/check", data={**CHECK, "source": "partner-tilitoimisto"}, follow_redirects=False)
    check_id = r.headers["location"].rsplit("/", 1)[1]
    assert app_module.store.get_check(check_id)["source"] == "partner-tilitoimisto"
