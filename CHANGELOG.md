# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Sector, country and size-band definitions with NACE mapping.
- Deterministic generator for an illustrative, fictional sample of 2,000 buyers
  (no names; types, geography, size ranges, appetite scaled to €52B in total).
- Matching engine: sector, country (region groups expand), revenue and EBITDA
  overlap, positive EBITDA for private equity; breakdowns by buyer type and HQ
  country; privacy threshold that pools groups under five buyers.
- Indicative EV range from sector multiples with a size adjustment; no value is
  shown for negative EBITDA.
- Tests for matching, privacy threshold, sample properties and valuation.
- Owner flow in English: four-question check, instant result with breakdowns
  by buyer type and HQ country, combined appetite, recent buyers, indicative
  value range and next steps; no personal data before the result.
- Opt-in with a separate unticked consent per channel (email, phone, SMS,
  WhatsApp, quarterly updates); consent text, version, language and timestamp
  stored per channel; simulated email double opt-in; unsubscribe link.
- Privacy notice page and sector pages with live buyer counts per industry
  and country.
- Password-protected advisor dashboard: owner inbox, funnel figures, owner
  detail with match snapshot, consent proof table and JSON export, status
  pipeline, outgoing message queue with previews.
- Call brief and anonymous profile drafts through a free LLM chain (Groq
  models, then OpenCode Zen) with template fallback. The profile prompt
  excludes the owner's identity, contact channels and value estimate.
- Buyer-demand refresh: adding a buyer recomputes matches for owners with
  confirmed update consent and queues a localized update email.
- Message catalogs (English) and locale-aware number formatting, ready for
  further languages.

- Finnish, German and Swedish translations of all owner pages, consent texts,
  confirmation and update emails, and the privacy notice.
- Finnish business ID pre-fill: validates the Y-tunnus check digit, reads name
  and main line of business from the PRH open data API (YTJ v3) and maps the
  industry code to a sector; manual entry remains the fallback. The ID is not
  stored.
- Localized sector page URLs (for example `/fi/toimialat/logistiikka-ja-kuljetus`,
  `/de/branchen/logistik-und-transport`) with redirects between languages and
  a per-country buyer count.

- Postal letter generator for DACH: CSV of target companies in, print-ready
  German PDF out, one letter per company with the live buyer count for its
  sector and country, a QR code to the localized sector page, window-envelope
  address layout and a GDPR Art. 14 source notice. Fictional sample targets
  included.

- Embed widget: one script tag (`/embed.js`) renders a compact check in an
  auto-resizing iframe on partner sites; results open in a new tab and the
  partner is recorded as the source. Fictional demo partner page at
  `/demo/partner`.

- Demo seeder with a Finnish owner and a German owner in the DACH size band
  (indicative EV about €41 to 56M) who arrives through a postal letter.
- Turso (libSQL) storage over the Hrana HTTP protocol, selected by
  `DATABASE_URL`/`DATABASE_AUTH_TOKEN`; SQLite remains the default for local
  runs and tests. Same schema on both.
- Vercel deployment: `api/index.py` entry point, `vercel.json` (Dublin region),
  `requirements.txt`, `.vercelignore`; `--env` option on the demo seeder.
- Protected demo reset (`python -m demandcheck.demo --reset --confirm mgx-demand-check`)
  that empties the database and restores the two demo owners with reviewed
  drafts from `data/demo_drafts.json`; no public endpoint.

### Fixed
- Embedded widget no longer grows in a resize loop; it reports the height of
  its card instead of the document.
- Buyer-demand update email uses the singular for exactly one new buyer.
- German confirmation and update emails address the owner by full name.
- Dashboard shows region names correctly (DACH) and the add-buyer
  confirmation next to the form.

### Changed
- Call brief opening lines use the customary form of address (German: "Sie"
  with title and surname); brief and profile prompts restrict statements to
  the given facts, and the profile no longer receives the owner's language.
- README rewritten for reviewers: live links, how buyer data works, privacy
  and consent design, AI-use disclosure.
- Demo companies and sample letter recipients are marked "(Demo)"; test
  fixtures use a synthetic business ID.
- Euro amounts use local notation in Finnish, German and Swedish.
- Buyer sample retuned: exact type mix (private equity 55%, strategic 25%,
  family offices 12%, search funds 8%), one to three sectors and country
  groups per buyer, narrower size ranges. Typical results now land between
  about 10 and 70 and differ clearly by sector, country and size.
- Owner copy no longer states terms that are not confirmed (first-call fees,
  response times); anonymity wording now says "unless you agree".
- Email confirmation is shown in a modal demo inbox opened on request; until confirmed, the page
  asks the owner to confirm and marks email channels as awaiting confirmation.
