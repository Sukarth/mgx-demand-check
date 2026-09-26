import json

import httpx

from demandcheck.store import LibSQLHTTPBackend, Store


def test_libsql_backend_encodes_args_and_decodes_rows():
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        results = []
        for req in body["requests"]:
            if req["type"] == "close":
                results.append({"type": "ok", "response": {"type": "close"}})
                continue
            results.append({"type": "ok", "response": {"type": "execute", "result": {
                "cols": [{"name": "id"}, {"name": "name"}, {"name": "score"}, {"name": "gone"}],
                "rows": [[{"type": "integer", "value": "7"}, {"type": "text", "value": "Ä"},
                          {"type": "float", "value": 1.5}, {"type": "null"}]],
                "affected_row_count": 1, "last_insert_rowid": "7"}}})
        return httpx.Response(200, json={"baton": None, "base_url": None, "results": results})

    backend = LibSQLHTTPBackend("libsql://db-org.turso.io", "tok",
                                http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert backend.url == "https://db-org.turso.io/v2/pipeline"
    rows, last = backend.execute("SELECT ?, ?, ?, ?", (1, "x", 2.5, None))
    assert rows == [{"id": 7, "name": "Ä", "score": 1.5, "gone": None}] and last == 7
    args = sent[-1]["requests"][0]["stmt"]["args"]
    assert args == [{"type": "integer", "value": "1"}, {"type": "text", "value": "x"},
                    {"type": "float", "value": 2.5}, {"type": "null"}]
    backend.batch([("INSERT INTO t VALUES (?)", (1,))])
    kinds = [r["stmt"]["sql"] for r in sent[-1]["requests"] if r["type"] == "execute"]
    assert kinds == ["BEGIN", "INSERT INTO t VALUES (?)", "COMMIT"]


def test_libsql_backend_raises_on_statement_error():
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"type": "error", "error": {"message": "no such table: x"}}, {"type": "ok"}]})

    backend = LibSQLHTTPBackend("https://db", None, http=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        backend.execute("SELECT * FROM x")
    except Exception as exc:
        assert "no such table" in str(exc)
    else:
        raise AssertionError("expected an error")


def test_sqlite_store_roundtrip(tmp_path):
    store = Store(tmp_path / "s.db")
    cid = store.add_check(lang="en", sector="logistics", country="FI", revenue_band="r_10_20",
                          ebitda_band="e_1_2", timing=None, ownership=None, source=None, match_total=3)
    owner = store.add_owner(check_id=cid, lang="en", name="A", email="a@b.fi", phone="", company="",
                            snapshot={"total": 3}, consents=[("email", "text", "v1")], needs_confirmation=True)
    assert owner["id"] and owner["confirm_token"]
    assert store.active_channels(owner["id"]) == {"email"}
    assert store.queue_message(owner["id"], "k", "s", "b") >= 1
