# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.9.0] - 2026-03-09

### Highlights

Apify as unified API provider — one `APIFY_API_TOKEN` now covers Reddit, X, TikTok, and Instagram. Existing keys (OpenAI, xAI, ScrapeCreators) remain as alternatives.

### Added

- Apify client module (`scripts/lib/apify_client.py`) — shared runner for synchronous actor execution
- Apify Reddit backend (`scripts/lib/apify_reddit.py`) via `automation-lab/reddit-scraper` actor
- Apify X/Twitter backend (`scripts/lib/apify_x.py`) via `scraper_one/x-posts-search` actor
- Apify TikTok backend (`scripts/lib/apify_tiktok.py`) via `epctex/tiktok-search-scraper` actor
- Apify Instagram backend (`scripts/lib/apify_instagram.py`) via `apify/instagram-reel-scraper` actor
- Shared text processing utilities (`scripts/lib/apify_common.py`) — tokenization, relevance scoring, date parsing
- Tests for all Apify modules (`tests/test_apify_client.py`, `tests/test_apify_social.py`)

### Changed

- `APIFY_API_TOKEN` is now a first-class config option covering all four social sources
- ScrapeCreators takes priority when both `SCRAPECREATORS_API_KEY` and `APIFY_API_TOKEN` are set

## [2.8.0] - 2026-03-04

### Highlights

Instagram Reels as the 8th signal source, TikTok migrated from Apify to ScrapeCreators API, and SKILL.md quality improvements. One API key (`SCRAPECREATORS_API_KEY`) now covers both TikTok and Instagram.

### Added

- Instagram Reels as 8th research source via ScrapeCreators API — keyword search, engagement metrics (views, likes, comments), spoken-word transcript extraction (`scripts/lib/instagram.py`)
- `InstagramItem` dataclass, normalization, scoring (45% relevance / 25% recency / 30% engagement), deduplication, cross-source linking, and rendering
- Instagram in SKILL.md: stats template (`📸 Instagram:`), citation priority, item format description, output footer
- URL-to-name extraction examples in SKILL.md for cleaner web source display
- `--search=instagram` flag support

### Changed

- TikTok backend migrated from Apify to ScrapeCreators API (`api.scrapecreators.com`)
- `APIFY_API_TOKEN` replaced by `SCRAPECREATORS_API_KEY` in config
- SKILL.md version bumped to v2.8
- WebSearch citation instruction strengthened to prevent trailing Sources: blocks
- Security section updated: Apify → ScrapeCreators references

### Fixed

- Web stats line showing full URLs instead of plain domain names
- Trailing "Sources:" block appearing after skill invitation (WebSearch tool mandate conflict)
- Instagram/TikTok not running in web-only mode when `--search=instagram` used without Reddit/X
- `$ARGUMENTS` quoting in SKILL.md for correct flag forwarding

## [2.1.0] - 2026-02-15

### Highlights

Three headline features: watchlists for always-on bots, YouTube transcripts as a 4th source, and Codex CLI compatibility. Plus bundled X search with no external CLI needed.

### Added

- Open-class skill with watchlists, briefings, and history modes (SQLite-backed, FTS5 full-text search, WAL mode) (`feat(open)`)
- YouTube as a 4th research source via yt-dlp -- search, view counts, and auto-generated transcript extraction (`feat: Add YouTube`)
- OpenAI Codex CLI compatibility -- install to `~/.agents/skills/last30days`, invoke with `$last30days` (`feat: Add Codex CLI`)
- Bundled X search -- vendored subset of Bird's Twitter GraphQL client (MIT, originally by @steipete), no external CLI needed (`v2.1: Bundle Bird X search`)
- Native web search backends: Parallel AI, Brave Search, OpenRouter/Perplexity Sonar Pro (`feat(engine)`)
- `--diagnose` flag for checking available sources and authentication status
- `--store` flag for SQLite accumulation (open variant)
- Conversational first-run experience (NUX) with dynamic source status (`feat(nux)`)

### Changed

- Smarter query construction -- strips noise words, auto-retries with shorter queries when X returns 0 results
- Two-phase search architecture -- Phase 1 discovers entities (@handles, r/subreddits), Phase 2 drills into them
- Reddit JSON enrichment -- real upvotes, comments, and upvote ratio from reddit.com/.json endpoint
- Engagement-weighted scoring: relevance 45%, recency 25%, engagement 30% (log1p dampening)
- Model auto-selection with 7-day cache and fallback chain (gpt-4.1 -> gpt-4o -> gpt-4o-mini)
- `--days=N` configurable lookback flag (thanks @jonthebeef, [#18](https://github.com/mvanhorn/last30days-skill/pull/18))
- Model fallback for unverified orgs (thanks @levineam, [#16](https://github.com/mvanhorn/last30days-skill/pull/16))
- Marketplace plugin support via `.claude-plugin/plugin.json` (inspired by @galligan, [#1](https://github.com/mvanhorn/last30days-skill/pull/1))

### Fixed

- YouTube timeout increased to 90s, Reddit 429 rate limit fail-fast
- YouTube soft date filter -- keeps evergreen content instead of filtering to 0 results
- Eager import crash in `__init__.py` that broke Codex environments
- Reddit future timeout (same pattern as YouTube timeout bug)
- Process cleanup on timeout/kill -- tracks child PIDs for clean shutdown
- Windows Unicode fix for cp1252 emoji crash (thanks @JosephOIbrahim, [#17](https://github.com/mvanhorn/last30days-skill/pull/17))
- X search returning 0 results on popular topics due to over-specific queries

### New Contributors

- @JosephOIbrahim -- Windows Unicode fix ([#17](https://github.com/mvanhorn/last30days-skill/pull/17))
- @levineam -- Model fallback for unverified orgs ([#16](https://github.com/mvanhorn/last30days-skill/pull/16))
- @jonthebeef -- `--days=N` configurable lookback ([#18](https://github.com/mvanhorn/last30days-skill/pull/18))

### Credits

- @steipete -- Bird CLI (vendored X search) and yt-dlp/summarize inspiration for YouTube transcripts
- @galligan -- Marketplace plugin inspiration
- @hutchins -- Pushed for YouTube feature

## [1.0.0] - 2026-01-15

Initial public release. Reddit + X search via OpenAI Responses API and xAI API.

[2.9.0]: https://github.com/mvanhorn/last30days-skill/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/mvanhorn/last30days-skill/compare/v2.6.0...v2.8.0
[2.1.0]: https://github.com/mvanhorn/last30days-skill/compare/v1.0.0...v2.1.0
[1.0.0]: https://github.com/mvanhorn/last30days-skill/releases/tag/v1.0.0
