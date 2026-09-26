"""SQLite persistence for checks, opted-in owners, consents, added buyers and messages."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "demandcheck.db"

STATUSES = ("new", "contacted", "call_booked", "soft_launch", "mandate", "not_now")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    lang TEXT NOT NULL,
    sector TEXT NOT NULL,
    country TEXT NOT NULL,
    revenue_band TEXT NOT NULL,
    ebitda_band TEXT NOT NULL,
    timing TEXT,
    ownership TEXT,
    source TEXT,
    match_total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id TEXT NOT NULL REFERENCES checks(id),
    created_at TEXT NOT NULL,
    lang TEXT NOT NULL,
    name TEXT,
    email TEXT,
    phone TEXT,
    company TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    confirm_token TEXT,
    email_confirmed_at TEXT,
    unsubscribe_token TEXT,
    snapshot TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES owners(id),
    channel TEXT NOT NULL,
    text TEXT NOT NULL,
    text_version TEXT NOT NULL,
    lang TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    withdrawn_at TEXT
);
CREATE TABLE IF NOT EXISTS added_buyers (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES owners(id),
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
);
CREATE TABLE IF NOT EXISTS drafts (
    owner_id INTEGER NOT NULL REFERENCES owners(id),
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    model TEXT,
    data TEXT NOT NULL,
    PRIMARY KEY (owner_id, kind)
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    task TEXT,
    model TEXT,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get("DB_PATH") or DEFAULT_DB)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._all(sql, params)
        return rows[0] if rows else None

    # Checks (anonymous) ---------------------------------------------------

    def add_check(self, *, lang: str, sector: str, country: str, revenue_band: str,
                  ebitda_band: str, timing: str | None, ownership: str | None,
                  source: str | None, match_total: int) -> str:
        check_id = secrets.token_urlsafe(9)
        self._exec(
            "INSERT INTO checks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (check_id, now_iso(), lang, sector, country, revenue_band, ebitda_band,
             timing, ownership, source, match_total))
        return check_id

    def get_check(self, check_id: str) -> dict | None:
        return self._one("SELECT * FROM checks WHERE id = ?", (check_id,))

    def count_checks(self) -> int:
        return self._one("SELECT COUNT(*) AS n FROM checks")["n"]

    # Owners ---------------------------------------------------------------

    def add_owner(self, *, check_id: str, lang: str, name: str, email: str, phone: str,
                  company: str, snapshot: dict, consents: list[tuple[str, str, str]],
                  needs_confirmation: bool) -> dict:
        """Create an owner with one consent row per ``(channel, text, version)``."""
        ts = now_iso()
        token = secrets.token_urlsafe(16) if needs_confirmation else None
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO owners (check_id, created_at, lang, name, email, phone, company, "
                "confirm_token, unsubscribe_token, snapshot) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (check_id, ts, lang, name, email, phone, company, token,
                 secrets.token_urlsafe(16), json.dumps(snapshot)))
            owner_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO consents (owner_id, channel, text, text_version, lang, granted_at) "
                "VALUES (?,?,?,?,?,?)",
                [(owner_id, ch, text, ver, lang, ts) for ch, text, ver in consents])
            self._conn.commit()
        return self.get_owner(owner_id)

    def get_owner(self, owner_id: int) -> dict | None:
        row = self._one(
            "SELECT o.*, c.sector, c.country, c.revenue_band, c.ebitda_band, c.timing, "
            "c.ownership, c.source FROM owners o JOIN checks c ON c.id = o.check_id WHERE o.id = ?",
            (owner_id,))
        if row:
            row["snapshot"] = json.loads(row["snapshot"])
        return row

    def list_owners(self) -> list[dict]:
        rows = self._all(
            "SELECT o.*, c.sector, c.country, c.revenue_band, c.ebitda_band, c.timing, "
            "c.ownership, c.source FROM owners o JOIN checks c ON c.id = o.check_id "
            "ORDER BY o.id DESC")
        for r in rows:
            r["snapshot"] = json.loads(r["snapshot"])
        return rows

    def owner_by_confirm_token(self, token: str) -> dict | None:
        row = self._one("SELECT id FROM owners WHERE confirm_token = ?", (token,))
        return self.get_owner(row["id"]) if row else None

    def confirm_email(self, owner_id: int) -> None:
        self._exec("UPDATE owners SET email_confirmed_at = ?, confirm_token = NULL WHERE id = ?",
                   (now_iso(), owner_id))

    def owner_by_unsubscribe_token(self, token: str) -> dict | None:
        row = self._one("SELECT id FROM owners WHERE unsubscribe_token = ?", (token,))
        return self.get_owner(row["id"]) if row else None

    def set_status(self, owner_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        self._exec("UPDATE owners SET status = ? WHERE id = ?", (status, owner_id))

    def set_snapshot(self, owner_id: int, snapshot: dict) -> None:
        self._exec("UPDATE owners SET snapshot = ? WHERE id = ?", (json.dumps(snapshot), owner_id))

    # Consents -------------------------------------------------------------

    def consents(self, owner_id: int) -> list[dict]:
        return self._all("SELECT * FROM consents WHERE owner_id = ? ORDER BY id", (owner_id,))

    def active_channels(self, owner_id: int) -> set[str]:
        return {r["channel"] for r in self._all(
            "SELECT channel FROM consents WHERE owner_id = ? AND withdrawn_at IS NULL", (owner_id,))}

    def withdraw(self, owner_id: int, channel: str) -> None:
        self._exec("UPDATE consents SET withdrawn_at = ? WHERE owner_id = ? AND channel = ? "
                   "AND withdrawn_at IS NULL", (now_iso(), owner_id, channel))

    # Buyers added at runtime ----------------------------------------------

    def add_buyer(self, buyer: dict) -> None:
        self._exec("INSERT INTO added_buyers VALUES (?,?,?)",
                   (buyer["id"], now_iso(), json.dumps(buyer)))

    def added_buyers(self) -> list[dict]:
        return [json.loads(r["data"]) for r in self._all("SELECT data FROM added_buyers ORDER BY created_at")]

    # Messages -------------------------------------------------------------

    def queue_message(self, owner_id: int, kind: str, subject: str, body: str) -> int:
        return self._exec(
            "INSERT INTO messages (owner_id, created_at, kind, subject, body) VALUES (?,?,?,?,?)",
            (owner_id, now_iso(), kind, subject, body)).lastrowid

    def messages(self, owner_id: int | None = None) -> list[dict]:
        if owner_id is None:
            return self._all("SELECT m.*, o.name, o.email FROM messages m JOIN owners o "
                             "ON o.id = m.owner_id ORDER BY m.id DESC")
        return self._all("SELECT * FROM messages WHERE owner_id = ? ORDER BY id DESC", (owner_id,))

    def get_message(self, message_id: int) -> dict | None:
        return self._one("SELECT m.*, o.name, o.email, o.lang FROM messages m JOIN owners o "
                         "ON o.id = m.owner_id WHERE m.id = ?", (message_id,))

    # LLM drafts and cache ---------------------------------------------------

    def save_draft(self, owner_id: int, kind: str, model: str, data: dict) -> None:
        self._exec("INSERT OR REPLACE INTO drafts VALUES (?,?,?,?,?)",
                   (owner_id, kind, now_iso(), model, json.dumps(data, ensure_ascii=False)))

    def drafts(self, owner_id: int) -> dict[str, dict]:
        out = {}
        for r in self._all("SELECT * FROM drafts WHERE owner_id = ?", (owner_id,)):
            out[r["kind"]] = {"model": r["model"], "created_at": r["created_at"],
                              "data": json.loads(r["data"])}
        return out

    def llm_cache_get(self, key: str) -> dict | None:
        row = self._one("SELECT model, response FROM llm_cache WHERE key = ?", (key,))
        return {"model": row["model"], "response": json.loads(row["response"])} if row else None

    def llm_cache_put(self, key: str, task: str, model: str, response: dict) -> None:
        self._exec("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?)",
                   (key, task, model, json.dumps(response, ensure_ascii=False), now_iso()))
