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
