"""Instagram search via Apify actor for /last30days.

Uses the apify/instagram-reel-scraper actor to search Instagram Reels.
Requires APIFY_API_TOKEN in config.

Provides the same interface as instagram.py (ScrapeCreators) so the
orchestrator can swap between backends transparently.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from . import apify_client, http

ACTOR_ID = "apify/instagram-reel-scraper"

# Depth configurations
DEPTH_CONFIG = {
    "quick":   {"max_items": 10, "max_captions": 3},
    "default": {"max_items": 20, "max_captions": 5},
    "deep":    {"max_items": 40, "max_captions": 8},
}

CAPTION_MAX_WORDS = 500

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
        sys.stderr.write(f"[Apify-Instagram] {msg}\n")
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


def _extract_hashtags(caption_text: str) -> List[str]:
    if not caption_text:
        return []
    return re.findall(r'#(\w+)', caption_text)


def search_and_enrich(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    token: str = None,
) -> Dict[str, Any]:
    """Search Instagram Reels via Apify and return enriched results.

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

    _log(f"Searching Instagram for '{core_topic}' (depth={depth})")

    # The reel scraper accepts hashtags or usernames
    # Convert topic to hashtag format for discovery
    hashtag = core_topic.replace(' ', '').lower()

    run_input = {
        "hashtags": [hashtag],
        "resultsLimit": config["max_items"],
        "onlyPostsNewerThan": from_date,
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
    _log(f"Found {len(items)} Instagram reels")
    return {"items": items}


def _parse_date(raw: Dict[str, Any]) -> Optional[str]:
    """Extract date from Apify Instagram item."""
    for key in ("taken_at", "timestamp", "takenAt", "createdAt", "date"):
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, str):
            # ISO format
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
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
) -> List[Dict[str, Any]]:
    """Parse Apify Instagram items to normalized format."""
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        reel_pk = str(raw.get("id", raw.get("pk", "")))
        shortcode = raw.get("shortcode", raw.get("code", raw.get("shortCode", "")))

        # Caption
        caption_obj = raw.get("caption", "")
        if isinstance(caption_obj, dict):
            text = caption_obj.get("text", "")
        elif isinstance(caption_obj, str):
            text = caption_obj
        else:
            text = raw.get("text", raw.get("description", ""))

        # Engagement
        play_count = raw.get("videoPlayCount", raw.get("video_play_count", raw.get("viewCount", 0))) or 0
        like_count = raw.get("likesCount", raw.get("like_count", raw.get("likeCount", 0))) or 0
        comment_count = raw.get("commentsCount", raw.get("comment_count", raw.get("commentCount", 0))) or 0

        # Author
        owner = raw.get("owner") or raw.get("user") or raw.get("ownerUsername") or {}
        if isinstance(owner, dict):
            author_name = owner.get("username", owner.get("unique_id", ""))
        elif isinstance(owner, str):
            author_name = owner
        else:
            author_name = ""

        duration = raw.get("videoDuration", raw.get("video_duration"))
        date_str = _parse_date(raw)
        hashtags = _extract_hashtags(text)
        relevance = _compute_relevance(query, text, hashtags)

        # URL
        url = raw.get("url", "")
        if not url and shortcode:
            url = f"https://www.instagram.com/reel/{shortcode}"

        # Caption snippet
        caption = ""
        if text:
            words = text.split()
            caption = ' '.join(words[:CAPTION_MAX_WORDS])
            if len(words) > CAPTION_MAX_WORDS:
                caption += '...'

        items.append({
            "video_id": reel_pk,
            "text": text,
            "url": url,
            "author_name": author_name,
            "date": date_str,
            "engagement": {
                "views": play_count,
                "likes": like_count,
                "comments": comment_count,
            },
            "hashtags": hashtags,
            "duration": duration,
            "relevance": relevance,
            "why_relevant": f"Instagram: {text[:60]}" if text else f"Instagram: {query}",
            "caption_snippet": caption,
        })

    # Hard date filter
    in_range = [i for i in items if i["date"] and from_date <= i["date"] <= to_date]
    out_of_range = len(items) - len(in_range)
    if in_range:
        items = in_range
        if out_of_range:
            _log(f"Filtered {out_of_range} reels outside date range")
    else:
        _log(f"No reels within date range, keeping all {len(items)}")

    # Sort by views descending
    items.sort(key=lambda x: x["engagement"]["views"], reverse=True)

    return items


def parse_instagram_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse response to item list (for orchestrator compat)."""
    return response.get("items", [])
