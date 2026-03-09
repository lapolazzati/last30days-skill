"""TikTok search via Apify actor for /last30days.

Uses the epctex/tiktok-search-scraper actor to search TikTok by keyword.
Requires APIFY_API_TOKEN in config.

Provides the same interface as tiktok.py (ScrapeCreators) so the
orchestrator can swap between backends transparently.
"""

from typing import Any, Dict, List

from . import apify_client, apify_common, http

ACTOR_ID = "epctex/tiktok-search-scraper"

_log = apify_common.make_logger("Apify-TikTok")


def search_and_enrich(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    token: str = None,
) -> Dict[str, Any]:
    """Search TikTok via Apify and return enriched results.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        token: Apify API token

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    if not token:
        return {"items": [], "error": "No APIFY_API_TOKEN configured"}

    config = apify_common.DEPTH_CONFIG.get(depth, apify_common.DEPTH_CONFIG["default"])
    core_topic = apify_common.extract_core_subject(topic)

    _log(f"Searching TikTok for '{core_topic}' (depth={depth})")

    # Use keyword search URL for TikTok scraper
    search_url = f"https://www.tiktok.com/search?q={core_topic.replace(' ', '%20')}"

    run_input = {
        "startUrls": [search_url],
        "maxItems": config["max_items"],
    }

    timeout = apify_common.timeout_for_depth(depth)

    try:
        raw_items = apify_client.run_actor(
            ACTOR_ID, run_input, token,
            timeout=timeout,
            max_items=config["max_items"],
        )
    except Exception as e:
        _log(f"Error: {e}")
        return {"items": [], "error": f"{type(e).__name__}: {e}"}

    items = _parse_items(raw_items, core_topic, from_date, to_date, config)
    _log(f"Found {len(items)} TikTok videos")
    return {"items": items}


def _parse_date(raw: Dict[str, Any]) -> str | None:
    """Extract date from Apify TikTok item."""
    return apify_common.parse_date_from_keys(
        raw, ["createTime", "create_time", "createdAt", "created_at", "date"]
    )


def _parse_items(
    raw_items: List[Dict[str, Any]],
    query: str,
    from_date: str,
    to_date: str,
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Parse Apify TikTok items to normalized format."""
    q_tokens = apify_common.tokenize(query)
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        video_id = str(raw.get("id", raw.get("aweme_id", raw.get("videoId", ""))))
        text = raw.get("text", raw.get("desc", raw.get("description", ""))) or ""

        # Stats
        stats = raw.get("stats") or raw.get("statistics") or {}
        play_count = stats.get("playCount", stats.get("play_count", raw.get("playCount", 0))) or 0
        digg_count = stats.get("diggCount", stats.get("digg_count", raw.get("diggCount", 0))) or 0
        comment_count = stats.get("commentCount", stats.get("comment_count", raw.get("commentCount", 0))) or 0
        share_count = stats.get("shareCount", stats.get("share_count", raw.get("shareCount", 0))) or 0

        # Author
        author_obj = raw.get("author") or raw.get("authorMeta") or {}
        if isinstance(author_obj, dict):
            author_name = author_obj.get("uniqueId", author_obj.get("unique_id", author_obj.get("name", "")))
        else:
            author_name = str(author_obj)

        # Hashtags
        hashtag_names = []
        hashtags_raw = raw.get("hashtags") or raw.get("challenges") or raw.get("text_extra") or []
        for h in hashtags_raw:
            if isinstance(h, dict):
                name = h.get("name", h.get("title", h.get("hashtag_name", "")))
                if name:
                    hashtag_names.append(name)
            elif isinstance(h, str):
                hashtag_names.append(h)

        # Duration
        duration = raw.get("duration", raw.get("video_duration"))
        if isinstance(raw.get("video"), dict):
            duration = duration or raw["video"].get("duration")

        date_str = _parse_date(raw)
        relevance = apify_common.compute_relevance(query, text, hashtag_names, _q_tokens=q_tokens)

        # URL
        url = raw.get("webVideoUrl", raw.get("url", raw.get("share_url", "")))
        if isinstance(url, str):
            url = url.split("?")[0]
        if not url and author_name and video_id:
            url = f"https://www.tiktok.com/@{author_name}/video/{video_id}"

        caption = apify_common.caption_snippet(text)

        items.append({
            "video_id": video_id,
            "text": text,
            "url": url or "",
            "author_name": author_name,
            "date": date_str,
            "engagement": {
                "views": play_count,
                "likes": digg_count,
                "comments": comment_count,
                "shares": share_count,
            },
            "hashtags": hashtag_names,
            "duration": duration,
            "relevance": relevance,
            "why_relevant": f"TikTok: {text[:60]}" if text else f"TikTok: {query}",
            "caption_snippet": caption,
        })

    items = apify_common.filter_by_date_range(items, from_date, to_date, _log, "videos")
    items.sort(key=lambda x: x["engagement"]["views"], reverse=True)
    return items


def parse_tiktok_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse response to item list (for orchestrator compat)."""
    return response.get("items", [])
