"""TikTok search via Apify actor for /last30days.

Uses the clockworks/tiktok-scraper actor to search TikTok by keyword.
Requires APIFY_API_TOKEN in config.

Provides the same interface as tiktok.py (ScrapeCreators) so the
orchestrator can swap between backends transparently.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from . import apify_client, http

ACTOR_ID = "clockworks/tiktok-scraper"

# Depth configurations
DEPTH_CONFIG = {
    "quick":   {"max_items": 10, "max_captions": 3},
    "default": {"max_items": 20, "max_captions": 5},
    "deep":    {"max_items": 40, "max_captions": 8},
}

CAPTION_MAX_WORDS = 500

# Stopwords for relevance (shared with tiktok.py)
STOPWORDS = frozenset({
    'the', 'a', 'an', 'to', 'for', 'how', 'is', 'in', 'of', 'on',
    'and', 'with', 'from', 'by', 'at', 'this', 'that', 'it', 'my',
    'your', 'i', 'me', 'we', 'you', 'what', 'are', 'do', 'can',
    'its', 'be', 'or', 'not', 'no', 'so', 'if', 'but', 'about',
    'all', 'just', 'get', 'has', 'have', 'was', 'will',
})

SYNONYMS = {
    'hip': {'rap', 'hiphop'}, 'hop': {'rap', 'hiphop'},
    'rap': {'hip', 'hop', 'hiphop'}, 'hiphop': {'rap', 'hip', 'hop'},
    'js': {'javascript'}, 'javascript': {'js'},
    'ts': {'typescript'}, 'typescript': {'ts'},
    'ai': {'artificial', 'intelligence'}, 'ml': {'machine', 'learning'},
    'react': {'reactjs'}, 'reactjs': {'react'},
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[Apify-TikTok] {msg}\n")
        sys.stderr.flush()


def _tokenize(text: str) -> Set[str]:
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    tokens = {w for w in words if w not in STOPWORDS and len(w) > 1}
    expanded = set(tokens)
    for t in tokens:
        if t in SYNONYMS:
            expanded.update(SYNONYMS[t])
    return expanded


def _compute_relevance(query: str, text: str, hashtags: List[str] = None) -> float:
    q_tokens = _tokenize(query)
    combined = text
    if hashtags:
        combined = f"{text} {' '.join(hashtags)}"
    t_tokens = _tokenize(combined)
    if hashtags:
        for tag in hashtags:
            tag_lower = tag.lower()
            for qt in q_tokens:
                if qt in tag_lower and qt != tag_lower:
                    t_tokens.add(qt)
    if not q_tokens:
        return 0.5
    overlap = len(q_tokens & t_tokens)
    ratio = overlap / len(q_tokens)
    return max(0.1, min(1.0, ratio))


def _extract_core_subject(topic: str) -> str:
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
        'prompt', 'prompts', 'prompting',
        'methods', 'strategies', 'approaches',
    }
    words = text.split()
    filtered = [w for w in words if w not in noise]
    result = ' '.join(filtered) if filtered else text
    return result.rstrip('?!.')


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

    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    core_topic = _extract_core_subject(topic)

    _log(f"Searching TikTok for '{core_topic}' (depth={depth})")

    # Use keyword search URL for TikTok scraper
    search_url = f"https://www.tiktok.com/search?q={core_topic.replace(' ', '%20')}"

    run_input = {
        "startUrls": [search_url],
        "maxItems": config["max_items"],
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

    items = _parse_items(raw_items, core_topic, from_date, to_date, config)
    _log(f"Found {len(items)} TikTok videos")
    return {"items": items}


def _parse_date(raw: Dict[str, Any]) -> Optional[str]:
    """Extract date from Apify TikTok item."""
    for key in ("createTime", "create_time", "createdAt", "created_at", "date"):
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, str):
            match = re.match(r'(\d{4}-\d{2}-\d{2})', val)
            if match:
                return match.group(1)
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
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Parse Apify TikTok items to normalized format."""
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
        relevance = _compute_relevance(query, text, hashtag_names)

        # URL
        url = raw.get("webVideoUrl", raw.get("url", raw.get("share_url", "")))
        if isinstance(url, str):
            url = url.split("?")[0]
        if not url and author_name and video_id:
            url = f"https://www.tiktok.com/@{author_name}/video/{video_id}"

        # Caption snippet — use text as baseline
        caption = ""
        if text:
            words = text.split()
            caption = ' '.join(words[:CAPTION_MAX_WORDS])
            if len(words) > CAPTION_MAX_WORDS:
                caption += '...'

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

    # Hard date filter
    in_range = [i for i in items if i["date"] and from_date <= i["date"] <= to_date]
    out_of_range = len(items) - len(in_range)
    if in_range:
        items = in_range
        if out_of_range:
            _log(f"Filtered {out_of_range} videos outside date range")
    else:
        _log(f"No videos within date range, keeping all {len(items)}")

    # Sort by views descending
    items.sort(key=lambda x: x["engagement"]["views"], reverse=True)

    return items


def parse_tiktok_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse response to item list (for orchestrator compat)."""
    return response.get("items", [])
