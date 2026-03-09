"""X/Twitter search via Apify actor for /last30days.

Uses the scraper_one/x-posts-search actor to search X by keyword.
Requires APIFY_API_TOKEN in config.

Provides the same interface as xai_x so the orchestrator
can swap between backends transparently.
"""

from typing import Any, Dict, List

from . import apify_client, apify_common, http

ACTOR_ID = "scraper_one/x-posts-search"

# Depth configurations
DEPTH_CONFIG = {
    "quick":   {"max_items": 15},
    "default": {"max_items": 30},
    "deep":    {"max_items": 60},
}

_log = apify_common.make_logger("Apify-X")


def search_x(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    token: str = None,
) -> Dict[str, Any]:
    """Search X/Twitter via Apify scraper_one/x-posts-search.

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

    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    core_topic = apify_common.extract_core_subject(topic)

    _log(f"Searching X for '{core_topic}' (depth={depth})")

    # Build Twitter advanced search query with date range
    search_query = f"{core_topic} since:{from_date} until:{to_date}"

    run_input = {
        "searchTerms": [search_query],
        "maxItems": config["max_items"],
        "sort": "Top",
        "tweetLanguage": "en",
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

    items = _parse_items(raw_items, core_topic, from_date, to_date)
    _log(f"Found {len(items)} X posts")
    return {"items": items}


_DATE_KEYS = ("createdAt", "created_at", "date", "timestamp")


def _parse_date(raw: Dict[str, Any]) -> str | None:
    """Extract date from Apify tweet item."""
    return apify_common.parse_date_from_keys(raw, _DATE_KEYS)


def _parse_items(
    raw_items: List[Dict[str, Any]],
    query: str,
    from_date: str,
    to_date: str,
) -> List[Dict[str, Any]]:
    """Parse Apify tweet items to normalized format."""
    items = []
    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue

        # Text content
        text = str(raw.get("full_text", raw.get("text", raw.get("tweet", "")))).strip()
        if not text:
            continue

        # Author
        user = raw.get("user") or raw.get("author") or {}
        if isinstance(user, dict):
            author_handle = user.get("screen_name", user.get("username", ""))
        else:
            author_handle = str(user)
        author_handle = author_handle.lstrip("@")

        # URL
        tweet_id = str(raw.get("id_str", raw.get("id", raw.get("tweetId", ""))))
        url = raw.get("url", "")
        if not url and author_handle and tweet_id:
            url = f"https://x.com/{author_handle}/status/{tweet_id}"

        if not url:
            continue

        # Engagement
        likes = raw.get("favorite_count", raw.get("likeCount", raw.get("likes", 0))) or 0
        retweets = raw.get("retweet_count", raw.get("retweetCount", raw.get("reposts", 0))) or 0
        replies = raw.get("reply_count", raw.get("replyCount", raw.get("replies", 0))) or 0
        quotes = raw.get("quote_count", raw.get("quoteCount", raw.get("quotes", 0))) or 0

        engagement = {
            "likes": int(likes) if likes else None,
            "reposts": int(retweets) if retweets else None,
            "replies": int(replies) if replies else None,
            "quotes": int(quotes) if quotes else None,
        }

        date_str = _parse_date(raw)

        # Relevance from engagement
        total_eng = (likes or 0) + (retweets or 0) * 2
        relevance = min(1.0, max(0.3, 0.5 + (total_eng / 1000)))

        items.append({
            "id": f"X{i+1}",
            "text": text[:500],
            "url": url,
            "author_handle": author_handle,
            "date": date_str,
            "engagement": engagement,
            "why_relevant": f"X post about {query}",
            "relevance": relevance,
        })

    return apify_common.filter_by_date_range(items, from_date, to_date, _log, "posts")


def parse_x_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse search_x response to item list (for orchestrator compat)."""
    return response.get("items", [])
