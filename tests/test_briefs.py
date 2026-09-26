from demandcheck import briefs

OWNER = {
    "name": "Aino Virtanen", "company": "Example Logistics Oy", "lang": "fi",
    "sector": "logistics", "country": "FI", "revenue_band": "r_10_20", "ebitda_band": "e_1_2",
    "timing": "1_2y", "ownership": "100",
    "snapshot": {"total": 40, "by_type": {"pe_platform": 20, "strategic": 20}, "by_hq": {"FI": 40}},
}


class FakeClient:
    def __init__(self):
        self.prompts = []

    def available(self):
        return True

    def chat_json(self, task, system, user, **kwargs):
        self.prompts.append(user)
        return {"headline": "ok"}, "fake:model"


def test_facts_are_in_english_with_owner_language():
    facts = briefs.owner_facts(OWNER, ["phone"])
    assert facts["owner_language"] == "Finnish"
    assert facts["sector"] == "Logistics and transport"
    assert facts["indicative_ev_range"] == "€6M to €9M"


def test_profile_prompt_excludes_identity_and_value():
    client = FakeClient()
    data, source = briefs.draft("profile", briefs.owner_facts(OWNER, ["phone"]), client)
    assert source == "fake:model"
    prompt = client.prompts[0]
    for secret in ("Aino", "Example Logistics", "€6M", "phone"):
        assert secret not in prompt


def test_brief_prompt_keeps_contact_context():
    client = FakeClient()
    briefs.draft("brief", briefs.owner_facts(OWNER, ["phone"]), client)
    assert "Aino Virtanen" in client.prompts[0]


def test_template_fallback_without_client():
    data, source = briefs.draft("brief", briefs.owner_facts(OWNER, []), None)
    assert source == "template" and len(data["questions"]) == 5
