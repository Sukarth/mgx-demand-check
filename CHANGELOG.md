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
