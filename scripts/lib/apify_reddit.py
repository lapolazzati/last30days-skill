"""Reddit search via Apify actor for /last30days.

Uses the automation-lab/reddit-scraper actor to search Reddit by keyword.
Requires APIFY_API_TOKEN in config.

Provides the same interface as openai_reddit so the orchestrator
can swap between backends transparently.
"""

from typing import Any, Dict, List, Optional

from . import apify_client, apify_common, http

ACTOR_ID = "automation-lab/reddit-scraper"

# Depth configurations: how many results to request
DEPTH_CONFIG = {
    "quick":   {"max_items": 25},
    "default": {"max_items": 50},
    "deep":    {"max_items": 100},
}

_log = apify_common.make_logger("Apify-Reddit")


def _extract_core_subject(topic: str) -> str:
    """Extract core subject — Reddit-specific, simpler than the common version.

    Keeps only content words (up to 5) without prefix stripping,
    which works better for Reddit's search API.
    """
    noise = {'best', 'top', 'how', 'to', 'tips', 'for', 'practices', 'features',
             'killer', 'guide', 'tutorial', 'recommendations', 'advice',
             'prompting', 'using', 'with', 'the', 'of', 'in', 'on'}
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
    """Search Reddit via Apify automation-lab/reddit-scraper.

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
    _log(f"Found {len(items)} Reddit posts")
    return {"items": items}


_DATE_KEYS = ("createdAt", "created_utc", "created", "date")


def _parse_date(raw: Dict[str, Any]) -> Optional[str]:
    """Extract date from Apify Reddit item."""
    return apify_common.parse_date_from_keys(raw, _DATE_KEYS)


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

    return apify_common.filter_by_date_range(items, from_date, to_date, _log, "posts")


def parse_reddit_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse search_reddit response to item list (for orchestrator compat)."""
    return response.get("items", [])
