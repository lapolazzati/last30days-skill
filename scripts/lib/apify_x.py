"""X/Twitter search via Apify actor for /last30days.

Uses the apidojo/tweet-scraper actor to search X by keyword.
Requires APIFY_API_TOKEN in config.

Provides the same interface as xai_x so the orchestrator
can swap between backends transparently.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import apify_client, http

ACTOR_ID = "apidojo/tweet-scraper"

# Depth configurations
DEPTH_CONFIG = {
    "quick":   {"max_items": 15},
    "default": {"max_items": 30},
    "deep":    {"max_items": 60},
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[Apify-X] {msg}\n")
        sys.stderr.flush()


def _extract_core_subject(topic: str) -> str:
    """Extract core subject from verbose query."""
    text = topic.lower().strip()
    prefixes = [
        'what are the best', 'what is the best', 'what are the latest',
        'what are people saying about', 'what do people think about',
        'how do i use', 'how to use', 'how to',
        'what are', 'what is', 'tips for', 'best practices for',
    ]
    for p in prefixes:
        if text.startswith(p + ' '):
            text = text[len(p):].strip()
    noise = {
        'best', 'top', 'good', 'great', 'awesome', 'killer',
        'latest', 'new', 'news', 'update', 'updates',
        'trending', 'hottest', 'popular', 'viral',
        'practices', 'features', 'recommendations', 'advice',
    }
    words = text.split()
    filtered = [w for w in words if w not in noise]
    result = ' '.join(filtered) if filtered else text
    return result.rstrip('?!.')


def search_x(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    token: str = None,
) -> Dict[str, Any]:
    """Search X/Twitter via Apify apidojo/tweet-scraper.

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
    core_topic = _extract_core_subject(topic)

    _log(f"Searching X for '{core_topic}' (depth={depth})")

    # Build Twitter advanced search query with date range
    search_query = f"{core_topic} since:{from_date} until:{to_date}"

    run_input = {
        "searchTerms": [search_query],
        "maxItems": config["max_items"],
        "sort": "Top",
        "tweetLanguage": "en",
    }

    timeout = 90 if depth == "quick" else 150 if depth == "default" else 240

    try:
        raw_items = apify_client.run_actor(
            ACTOR_ID, run_input, token,
            timeout=timeout,
            max_items=config["max_items"],
        )
    except http.HTTPError as e:
        _log(f"Apify error: {e}")
        return {"items": [], "error": f"{type(e).__name__}: {e}"}
    except Exception as e:
        _log(f"Unexpected error: {e}")
        return {"items": [], "error": f"{type(e).__name__}: {e}"}

    items = _parse_items(raw_items, core_topic, from_date, to_date)
    _log(f"Found {len(items)} X posts")
    return {"items": items}


def _parse_date(raw: Dict[str, Any]) -> Optional[str]:
    """Extract date from Apify tweet item."""
    for key in ("createdAt", "created_at", "date", "timestamp"):
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, str):
            # ISO format or Twitter format
            match = re.match(r'(\d{4}-\d{2}-\d{2})', val)
            if match:
                return match.group(1)
            # Twitter format: "Thu Oct 10 12:00:00 +0000 2024"
            try:
                dt = datetime.strptime(val, "%a %b %d %H:%M:%S %z %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        try:
            ts = float(val)
            if ts > 1e12:
                ts /= 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError):
            continue
    return None


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

    # Hard date filter
    in_range = [item for item in items if item["date"] and from_date <= item["date"] <= to_date]
    out_of_range = len(items) - len(in_range)
    if in_range:
        items = in_range
        if out_of_range:
            _log(f"Filtered {out_of_range} posts outside date range")
    else:
        _log(f"No posts within date range, keeping all {len(items)}")

    return items


def parse_x_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse search_x response to item list (for orchestrator compat)."""
    return response.get("items", [])
