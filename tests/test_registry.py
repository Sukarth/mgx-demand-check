import httpx
import pytest

from demandcheck import registry

PAYLOAD = {"totalResults": 1, "companies": [{
    "businessId": {"value": "0536104-0"},
    "names": [
        {"name": "Old Name Oy", "type": "1", "endDate": "2010-01-01"},
        {"name": "Example Logistiikka Oy", "type": "1"},
        {"name": "Aux", "type": "3"},
    ],
    "mainBusinessLine": {"type": "49410", "descriptions": [
        {"languageCode": "1", "description": "Tieliikenteen tavarankuljetus"},
        {"languageCode": "3", "description": "Freight transport by road"},
    ]},
}]}


@pytest.mark.parametrize("value,ok", [
    ("0112038-9", True), ("0536104-0", True), ("1234567-8", False), ("0112038-8", False), ("112038-9", False),
])
def test_business_id_check_digit(value, ok):
    assert registry.valid_business_id(value) is ok


def test_normalize_business_id():
    assert registry.normalize_business_id(" 01120389 ") == "0112038-9"


@pytest.mark.parametrize("code,sector", [
    ("49410", "logistics"), ("43210", "technical_installation"), ("62010", "software_it"),
    ("81210", "facility_services"), ("33120", "industrial_services"), ("70100", None), ("", None),
])
def test_industry_code_to_sector(code, sector):
    assert registry.sector_for_industry_code(code) == sector


def test_parse_company_picks_current_name_and_language():
    c = registry.parse_company(PAYLOAD, "fi")
    assert c.name == "Example Logistiikka Oy"
    assert c.sector == "logistics"
    assert c.industry_name == "Tieliikenteen tavarankuljetus"
    assert registry.parse_company({"companies": []}) is None


def test_lookup_uses_prh_v3_and_handles_errors():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=PAYLOAD)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert registry.lookup("0536104-0", http=client).sector == "logistics"
    assert "opendata-ytj-api/v3/companies?businessId=0536104-0" in seen["url"]

    down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(registry.RegistryUnavailable):
        registry.lookup("0536104-0", http=down)
