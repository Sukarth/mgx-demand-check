# MGX Demand Check

An anonymous, self-serve buyer-demand check for business owners, built as a
prototype for [Mergero](https://mergero.com/).

An owner answers four questions (industry, country, revenue band, EBITDA band)
and immediately sees how many buyers in the network are looking for a company
like theirs, broken down by buyer type and HQ country, plus an indicative value
range. No name, email or phone number is needed to see the result.

Only if the owner wants more (a confidential call, an anonymous profile, or
buyer-demand updates) do they leave contact details and tick separate, unticked
consent boxes per channel. Each consent is stored with its exact wording,
version, language and timestamp.

> **Sample data notice.** The buyer figures come from an illustrative,
> fictional sample of 2,000 generated buyers (`data/buyers_sample.json`). No
> buyer has a name and no criteria are attached to any real firm. A production
> version would read aggregated buyer criteria (counts only) from MGX.

## What it does

**Owner side (public)**
- English, Finnish, German and Swedish (`/en`, `/fi`, `/de`, `/sv`; the root
  picks the browser language).
- Four-question check, result first, optional timing and ownership share.
- Finnish companies can pre-fill the industry from their business ID
  (Y-tunnus) via the PRH open data API; manual entry is always possible.
- Buyer count with a privacy threshold: groups under five buyers are pooled or
  shown as "fewer than 5", so no individual buyer can be inferred.
- Indicative EV range from sector EBITDA multiples with a size adjustment,
  clearly labelled as indicative. No multiple-based value for loss-making firms.
- Opt-in with one consent per channel (email, phone, SMS, WhatsApp, quarterly
  updates) and simulated email double opt-in.
- Localized sector pages with a live buyer count per industry and country,
  e.g. `/fi/toimialat/logistiikka-ja-kuljetus`, `/de/branchen/logistik-und-transport`.
- Embed widget for partner sites (accountants, banks, chambers):
  `<script src="https://<host>/embed.js" data-lang="fi" data-partner="name" async></script>`.
  A fictional demo partner page is at `/demo/partner`.
- Privacy notice (GDPR Art. 13 outline).

**Advisor side (`/dashboard`, password protected)**
- Owner inbox with profile, timing, consents and match snapshot.
- Consent proof per channel, exportable as JSON.
- AI-drafted call brief (with an opening line in the owner's language) and
  anonymous company profile as a starting point for a soft launch. Drafts are
  for review by an advisor; the profile draft never receives the owner's name,
  company or contact details.
- Status pipeline: new, contacted, call booked, soft launch, mandate, not now.
- Postal letters for DACH (`/dashboard/letters`): CSV of target companies in,
  print-ready German PDF out, with the buyer count for each company's sector
  and country, a QR code to the sector page and a GDPR Art. 14 source notice.
- Buyer-demand refresh: adding a buyer recomputes matches for every owner with
  confirmed update consent and queues a "buyer demand changed" email in the
  owner's language, with an unsubscribe link.

Matching and valuation are pure, tested Python functions. The language model
only drafts text.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
cp .env.example .env          # optional: add LLM keys and a dashboard password
uvicorn demandcheck.app:app --port 8765
```

Open <http://127.0.0.1:8765/en> for the owner flow and
<http://127.0.0.1:8765/dashboard> for the advisor view. Without
`DASHBOARD_PASSWORD` the password is `mergero-demo`.

Seed two demo owners (a Finnish logistics company and a German installation
company in the DACH size band, arriving via a postal letter), optionally with
AI drafts:

```bash
python -m demandcheck.demo --drafts
```

Regenerate the buyer sample (deterministic, seeded):

```bash
python -m demandcheck.buyers
```

Run the tests:

```bash
pytest
```

## Deploy

The app runs on Vercel (Python runtime, FastAPI detected automatically;
`api/index.py` exposes the app) with a Turso (libSQL) database. Vercel's
filesystem is not shared between requests, so production data lives in Turso;
local runs and tests use a SQLite file.

1. Create a Turso database and a token (Turso CLI or Platform API).
2. Put the production values in `.env.production` (gitignored):
   `DATABASE_URL=libsql://<db>.turso.io`, `DATABASE_AUTH_TOKEN`,
   `DASHBOARD_PASSWORD`, `SESSION_SECRET`.
3. Seed the demo owners and drafts:
   `python -m demandcheck.demo --drafts --env .env.production`
4. Add the same variables plus `GROQ_API_KEY` and `OPENCODE_API_KEY` to the
   Vercel project (`vercel env add <NAME> production`), then deploy:
   `vercel deploy --prod`.

`SESSION_SECRET` must be set in production so dashboard logins survive across
function instances. The buyer sample ships with the code and is read-only.

## Configuration

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq free tier, tried first for drafts |
| `OPENCODE_API_KEY` | OpenCode Zen fallback |
| `DASHBOARD_PASSWORD` | Advisor dashboard password |
| `SESSION_SECRET` | Cookie signing key (random per process if unset) |
| `DATABASE_URL` | Turso/libSQL URL; when set, used instead of SQLite |
| `DATABASE_AUTH_TOKEN` | Turso database token |
| `DB_PATH` | SQLite path when `DATABASE_URL` is unset (default `data/demandcheck.db`) |

Without any LLM key the dashboard falls back to template drafts.

## Notes

- Legal design notes (consent per channel, proof of consent, double opt-in,
  AI disclosure) reflect research, not legal advice. A review by counsel in each
  target country is recommended before launch.
- Built with the help of Claude Code (AI coding assistant).

## License

MIT
