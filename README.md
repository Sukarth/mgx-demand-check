# MGX Demand Check

**Stop chasing owners. Let them come to you.** An anonymous, local-language
buyer-demand check for business owners, built as a prototype for
[Mergero](https://mergero.com/) (Mergero challenge, prompt hackathon, September 2026).

Mergero already shows owners a shortlist of fitting buyers after a first
conversation. This prototype shows a preview of that shortlist *before* the
conversation, self-serve and anonymous, so the preview creates the
conversation:

1. **Result first.** An owner answers four questions (industry, country,
   revenue band, EBITDA band) and immediately sees how many buyers are looking
   for a company like theirs, by buyer type and HQ country, with an indicative
   value range. No name, email or phone number is needed.
2. **Consent second.** Only if the owner wants more (a confidential call, an
   anonymous profile, buyer-demand updates) do they leave contact details and
   tick a separate, unticked box per channel. In Germany and Austria that
   consent is what makes calls, SMS, WhatsApp and email outreach lawful.
3. **Refresh loop.** When new matching buyers join, opted-in owners get a
   "your buyer demand changed" update in their language.

Every opted-in owner is a sell-side lead for Mergero and new off-market supply
for its buy-side clients.

> **Illustrative sample data.** All buyer figures come from a fictional sample
> of 2,000 generated buyers (`data/buyers_sample.json`): no names, and no
> criteria attached to any real firm. The production version would read
> aggregated buyer criteria (counts only, no identities) from the MGX Deal
> Engine. Demo owners and letter recipients are fictional and marked "(Demo)".

## Live demo

| What | Link |
|---|---|
| Owner check (Finnish, German, Swedish, English) | [/fi](https://mgx-demand-check.vercel.app/fi) · [/de](https://mgx-demand-check.vercel.app/de) · [/sv](https://mgx-demand-check.vercel.app/sv) · [/en](https://mgx-demand-check.vercel.app/en) |
| Sector page with live buyer count | [/de/branchen/elektro-und-gebaudetechnik](https://mgx-demand-check.vercel.app/de/branchen/elektro-und-gebaudetechnik?country=DE) · [/fi/toimialat](https://mgx-demand-check.vercel.app/fi/toimialat) |
| Check embedded on a (fictional) partner site | [/demo/partner](https://mgx-demand-check.vercel.app/demo/partner) |
| Advisor dashboard | [/dashboard](https://mgx-demand-check.vercel.app/dashboard) (password in the submission email) |

Try a Finnish business ID (for example any Y-tunnus of a logistics company) on
`/fi` to see the industry pre-filled from the public PRH register.

## What it does

**Owner side**
- Four languages; the root URL picks the browser language.
- Finnish business ID pre-fill from the PRH open data API (YTJ v3); the ID is
  not stored and manual entry always works.
- Privacy threshold: any group under five buyers is pooled or shown as
  "fewer than 5".
- Indicative EV range from sector EBITDA multiples with a size adjustment,
  never a single number; no multiple-based value for loss-making firms.
- Localized sector pages (`/fi/toimialat/…`, `/de/branchen/…`,
  `/sv/branscher/…`) as SEO and ad landing pages.
- Embed widget for accountants, banks and chambers:
  `<script src="https://mgx-demand-check.vercel.app/embed.js" data-lang="fi" data-partner="name" async></script>`.

**Advisor side**
- Owner inbox with sector, size, timing, consents and a match snapshot.
- Consent proof per channel (exact text, version, language, timestamp, email
  double opt-in), exportable as JSON.
- AI-drafted call brief with an opening line in the owner's language, and an
  anonymous company profile draft as the start of a Soft Launch or Silent
  Mandate.
- Status pipeline: new, contacted, call booked, soft launch, mandate, not now.
- "Add a buyer to MGX": recomputes matches and queues localized update emails
  for owners with confirmed update consent.
- DACH postal letters: CSV of target companies in, print-ready German PDF out,
  with the buyer count for each company's sector and country, a QR code to the
  sector page and a GDPR Art. 14 source notice.

## How buyer data works

`demandcheck/matching.py` and `demandcheck/valuation.py` are pure functions
with tests. A buyer matches when it is active, targets the owner's sector and
country (region groups such as Nordics or DACH expand to countries), and its
revenue and EBITDA ranges overlap the owner's bands; private equity requires
positive EBITDA. The sample (`python -m demandcheck.buyers`, seeded and
deterministic) mirrors what Mergero shared about its network: 2,000+ buyers,
about €52B combined appetite, private equity about 55%, strategic acquirers
25%, family offices 12%, search funds 8%. In production the same functions
would run on an aggregated MGX export.

## Privacy and consent design

- The result is shown before any personal data is requested; the anonymous
  answers are not linked to a person unless they opt in.
- One unticked checkbox per channel; consent text is versioned and stored with
  language and timestamp; email consent needs confirmation (double opt-in).
- Every update email has a one-click unsubscribe.
- Buyers are only ever shown as aggregated counts; small groups are hidden.
- AI drafts are internal and reviewed by a person before anything is sent;
  the profile draft never receives the owner's name, company or contacts.
- Legal notes are research, not legal advice; a review by counsel in each
  target country is recommended before launch.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
python -m demandcheck.demo --drafts   # two demo owners with AI drafts (optional)
uvicorn demandcheck.app:app --port 8765
```

Open <http://127.0.0.1:8765/fi> and <http://127.0.0.1:8765/dashboard>
(password `mergero-demo` unless `DASHBOARD_PASSWORD` is set). Without LLM keys
the dashboard uses template drafts. Run the tests with `pytest`.

Restore the seeded demo state (deletes all owners, checks, messages and added
buyers):

```bash
python -m demandcheck.demo --reset --confirm mgx-demand-check [--env .env.production]
```

## Deploy

Runs on Vercel (Python runtime; `api/index.py` exposes the FastAPI app) with a
Turso (libSQL) database, because Vercel's filesystem is not shared between
requests. Local runs and tests use SQLite; `DATABASE_URL` switches to Turso.

1. Create a Turso database and token; put `DATABASE_URL`,
   `DATABASE_AUTH_TOKEN`, `DASHBOARD_PASSWORD` and `SESSION_SECRET` in
   `.env.production` (gitignored).
2. Seed: `python -m demandcheck.demo --drafts --env .env.production`.
3. Add the same variables plus `GROQ_API_KEY` and `OPENCODE_API_KEY` to the
   Vercel project (`vercel env add <NAME> production`), then `vercel deploy --prod`.

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq free tier, tried first for drafts |
| `OPENCODE_API_KEY` | OpenCode Zen fallback |
| `DASHBOARD_PASSWORD` | Advisor dashboard password |
| `SESSION_SECRET` | Cookie signing key; must be set in production |
| `DATABASE_URL`, `DATABASE_AUTH_TOKEN` | Turso database; SQLite is used when unset |
| `DB_PATH` | SQLite path (default `data/demandcheck.db`) |

## AI use

Built with [Claude Code](https://claude.com/claude-code) (Anthropic's AI coding
assistant), which wrote most of the code, tests and translations under the
author's direction. At runtime a
language model (Groq, with OpenCode Zen as fallback) only drafts internal text:
call briefs and anonymous profile drafts. Matching, valuation, consent handling
and emails are deterministic code.

## License

MIT
