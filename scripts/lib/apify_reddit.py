"""Reddit search via Apify actor for /last30days.

Uses the trudax/reddit-scraper actor to search Reddit by keyword.
Requires APIFY_API_TOKEN in config.

Provides the same interface as openai_reddit so the orchestrator
can swap between backends transparently.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import apify_client, http

ACTOR_ID = "trudax/reddit-scraper"

# Depth configurations: how many results to request
DEPTH_CONFIG = {
    "quick":   {"max_items": 25},
    "default": {"max_items": 50},
    "deep":    {"max_items": 100},
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[Apify-Reddit] {msg}\n")
        sys.stderr.flush()


def _extract_core_subject(topic: str) -> str:
    """Extract core subject from verbose query."""
    noise = ['best', 'top', 'how to', 'tips for', 'practices', 'features',
             'killer', 'guide', 'tutorial', 'recommendations', 'advice',
             'prompting', 'using', 'for', 'with', 'the', 'of', 'in', 'on']
    words = topic.lower().split()
    result = [w for w in words if w not in noise]
    return ' '.join(result[:5]) or topic


def search_reddit(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    token: str = None,
) -> Dict[str, Any]:
    """Search Reddit via Apify trudax/reddit-scraper.

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

    _log(f"Searching Reddit for '{core_topic}' (depth={depth})")

    run_input = {
        "searchMode": "posts",
        "searchTerms": [core_topic],
        "sort": "relevance",
        "time": "month",
        "maxItems": config["max_items"],
        "searchPosts": True,
        "searchComments": False,
        "searchCommunities": False,
        "includeNSFW": False,
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
    _log(f"Found {len(items)} Reddit posts")
    return {"items": items}


def _parse_date(raw: Dict[str, Any]) -> Optional[str]:
    """Extract date from Apify Reddit item."""
    # Try created_utc / createdAt / created
    for key in ("createdAt", "created_utc", "created", "date"):
        val = raw.get(key)
        if not val:
            continue
        # ISO string
        if isinstance(val, str):
            match = re.match(r'(\d{4}-\d{2}-\d{2})', val)
            if match:
                return match.group(1)
        # Unix timestamp
        try:
            ts = float(val)
            if ts > 1e12:
                ts /= 1000  # milliseconds
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
    """Parse Apify Reddit items to normalized format."""
    items = []
    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue

        # Extract URL — prefer permalink
        url = raw.get("url", "")
        permalink = raw.get("permalink", "")
        if permalink and "reddit.com" not in permalink:
            url = f"https://www.reddit.com{permalink}"
        elif permalink:
            url = permalink
        if not url or "reddit.com" not in url:
            continue

        # Must be a post URL with /comments/
        if "/comments/" not in url:
            continue

        title = str(raw.get("title", "")).strip()
        if not title:
            continue

        subreddit = str(raw.get("subreddit", raw.get("communityName", ""))).strip()
        subreddit = subreddit.lstrip("r/")

        date_str = _parse_date(raw)

        # Score/upvotes for relevance
        score = raw.get("score", raw.get("upvotes", raw.get("ups", 0))) or 0
        num_comments = raw.get("numberOfComments", raw.get("num_comments", raw.get("numComments", 0))) or 0

        # Basic relevance from score
        relevance = min(1.0, max(0.3, 0.5 + (score / 500)))

        items.append({
            "id": f"R{i+1}",
            "title": title,
            "url": url,
            "subreddit": subreddit,
            "date": date_str,
            "score": score,
            "num_comments": num_comments,
            "why_relevant": f"Reddit post about {query}",
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


def parse_reddit_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse search_reddit response to item list (for orchestrator compat)."""
    return response.get("items", [])
