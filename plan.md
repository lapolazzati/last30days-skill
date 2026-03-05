# Plan: Migrate to Apify as unified API provider

## Goal
Replace ScrapeCreators (TikTok + Instagram), OpenAI Responses API (Reddit), and xAI/Bird (X/Twitter) with Apify actors, consolidating to a single `APIFY_API_TOKEN`.

Keep free sources as-is: Hacker News (Algolia), Polymarket (Gamma), YouTube (yt-dlp).

## APIFY_API_TOKEN placement
- Already registered in `scripts/lib/env.py:207` — loaded from `~/.config/last30days/.env` or `APIFY_API_TOKEN` env var
- Update `get_config()`, availability checks, and `get_missing_keys()` to treat `APIFY_API_TOKEN` as the primary key for Reddit, X, TikTok, and Instagram

## Apify Actor Choices
| Source | Actor | Why |
|--------|-------|-----|
| Reddit | `automation-lab/reddit-scraper` | Keyword search, $1/1K, posts+comments, date filtering |
| X/Twitter | `scraper_one/x-posts-search` | Keyword search, engagement metrics, clean output |
| TikTok | `epctex/tiktok-search-scraper` | Keyword search, video data + hashtags |
| Instagram | `apify/instagram-reel-scraper` + `apify/instagram-hashtag-scraper` | Official actor for reels; hashtag scraper for keyword discovery |

## Files to modify

### 1. `scripts/lib/env.py` — Config & availability
- Update `is_tiktok_available()`, `is_instagram_available()` to check `APIFY_API_TOKEN`
- Add `is_reddit_available()` that checks `OPENAI_API_KEY` OR `APIFY_API_TOKEN`
- Add `is_x_available()` that checks `XAI_API_KEY`, Bird, OR `APIFY_API_TOKEN`
- Update `get_available_sources()` and `get_missing_keys()` to account for Apify covering Reddit/X/TikTok/Instagram
- Add helper `get_reddit_source()` → 'openai' | 'apify' | None
- Add helper `get_tiktok_source()` → 'scrapecreators' | 'apify' | None
- Add helper `get_instagram_source()` → 'scrapecreators' | 'apify' | None

### 2. `scripts/lib/apify_client.py` — NEW shared Apify client
- Shared helper to call Apify actors via `run-sync-get-dataset-items` endpoint
- `run_actor(actor_id, input_data, token, timeout)` → list of result items
- Handles auth, timeouts, error handling
- Single place to manage Apify API calls

### 3. `scripts/lib/apify_reddit.py` — NEW Reddit via Apify
- `search_reddit(topic, from_date, to_date, depth, token)` → same return format as `openai_reddit.search_reddit()`
- Calls `automation-lab/reddit-scraper` with keyword search
- `parse_reddit_response()` → normalized items matching existing schema
- Same interface as `openai_reddit` so orchestrator can swap transparently

### 4. `scripts/lib/apify_x.py` — NEW X/Twitter via Apify
- `search_x(topic, from_date, to_date, depth, token)` → same return format as `xai_x.search_x()`
- Calls `scraper_one/x-posts-search` with keyword search
- `parse_x_response()` → normalized items matching existing schema

### 5. `scripts/lib/apify_tiktok.py` — NEW TikTok via Apify
- `search_and_enrich(topic, from_date, to_date, depth, token)` → same return format as `tiktok.search_and_enrich()`
- Calls `epctex/tiktok-search-scraper` with keyword search
- `parse_tiktok_response()` → normalized items matching existing schema

### 6. `scripts/lib/apify_instagram.py` — NEW Instagram via Apify
- Two-step: hashtag search for discovery → reel scraper for enrichment
- `search_and_enrich(topic, from_date, to_date, depth, token)` → same return format as `instagram.search_and_enrich()`
- `parse_instagram_response()` → normalized items matching existing schema

### 7. `scripts/last30days.py` — Orchestrator updates
- In `_search_reddit()`: check source, dispatch to `openai_reddit` or `apify_reddit`
- In `_search_x()`: check source, dispatch to `xai_x`, `bird_x`, or `apify_x`
- In `_search_tiktok()`: check source, dispatch to `tiktok` (ScrapeCreators) or `apify_tiktok`
- In `_search_instagram()`: check source, dispatch to `instagram` (ScrapeCreators) or `apify_instagram`
- Update source availability logic and skip-reason messages
- Update token passing to use `config.get('APIFY_API_TOKEN')` for Apify sources

### 8. `scripts/lib/normalize.py` — Minor updates
- Ensure normalizers handle any field differences from Apify output vs ScrapeCreators

### 9. Prompt/skill text updates
- Update setup instructions to mention `APIFY_API_TOKEN` as the single-key option
- Keep existing keys as alternatives (backward compat)

## What stays the same
- YouTube (yt-dlp) — free, local
- Hacker News (Algolia) — free
- Polymarket (Gamma) — free
- Existing ScrapeCreators/OpenAI/xAI paths — kept as alternatives (Apify is a new option, not a forced replacement)
- All scoring, deduplication, rendering, caching logic unchanged

## Implementation order
1. `apify_client.py` (shared client)
2. `apify_reddit.py` (Reddit actor)
3. `apify_x.py` (X actor)
4. `apify_tiktok.py` (TikTok actor)
5. `apify_instagram.py` (Instagram actor)
6. `env.py` updates (availability/routing)
7. `last30days.py` orchestrator updates (dispatch logic)
8. Normalize/render adjustments if needed
9. Test with `--mock` or live
