"""Shared helpers for Apify-backed social media modules.

Contains text processing, relevance scoring, date parsing, and common
patterns shared across apify_reddit, apify_x, apify_tiktok, and
apify_instagram.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

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

# Depth configurations shared by TikTok and Instagram
DEPTH_CONFIG = {
    "quick":   {"max_items": 10, "max_captions": 3},
    "default": {"max_items": 20, "max_captions": 5},
    "deep":    {"max_items": 40, "max_captions": 8},
}

# Module-level constants for extract_core_subject
_QUERY_PREFIXES = [
    'what are the best', 'what is the best', 'what are the latest',
    'what are people saying about', 'what do people think about',
    'how do i use', 'how to use', 'how to',
    'what are', 'what is', 'tips for', 'best practices for',
]

_NOISE_WORDS = frozenset({
    'best', 'top', 'good', 'great', 'awesome', 'killer',
    'latest', 'new', 'news', 'update', 'updates',
    'trending', 'hottest', 'popular', 'viral',
    'practices', 'features', 'recommendations', 'advice',
    'prompt', 'prompts', 'prompting',
    'methods', 'strategies', 'approaches',
})


def make_logger(tag: str) -> Callable[[str], None]:
    """Create a stderr logger with a given tag prefix."""
    def _log(msg: str):
        if sys.stderr.isatty():
            sys.stderr.write(f"[{tag}] {msg}\n")
            sys.stderr.flush()
    return _log


def tokenize(text: str) -> Set[str]:
    """Tokenize text, removing stopwords and expanding synonyms."""
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    tokens = {w for w in words if w not in STOPWORDS and len(w) > 1}
    expanded = set(tokens)
    for t in tokens:
        if t in SYNONYMS:
            expanded.update(SYNONYMS[t])
    return expanded


def compute_relevance(query: str, text: str, hashtags: List[str] = None,
                      _q_tokens: Set[str] = None) -> float:
    """Compute relevance score between query and text+hashtags.

    Args:
        query: Search query string.
        text: Content text to compare against.
        hashtags: Optional list of hashtags to include.
        _q_tokens: Pre-tokenized query tokens (avoids re-tokenizing
            the same query for every item in a batch).
    """
    q_tokens = _q_tokens if _q_tokens is not None else tokenize(query)
    if not q_tokens:
        return 0.5
    combined = text
    if hashtags:
        combined = f"{text} {' '.join(hashtags)}"
    t_tokens = tokenize(combined)
    if hashtags:
        for tag in hashtags:
            tag_lower = tag.lower()
            for qt in q_tokens:
                if qt in tag_lower and qt != tag_lower:
                    t_tokens.add(qt)
    overlap = len(q_tokens & t_tokens)
    ratio = overlap / len(q_tokens)
    return max(0.1, min(1.0, ratio))


def extract_core_subject(topic: str) -> str:
    """Extract core subject from verbose query by stripping prefixes and noise."""
    text = topic.lower().strip()
    for p in _QUERY_PREFIXES:
        if text.startswith(p + ' '):
            text = text[len(p):].strip()
    words = text.split()
    filtered = [w for w in words if w not in _NOISE_WORDS]
    result = ' '.join(filtered) if filtered else text
    return result.rstrip('?!.')


def parse_date_from_keys(raw: Dict[str, Any], keys: List[str]) -> Optional[str]:
    """Extract a YYYY-MM-DD date string from a raw dict, trying multiple keys.

    Handles ISO strings, YYYY-MM-DD prefixes, Twitter-format dates
    (e.g. "Thu Oct 10 12:00:00 +0000 2024"), and unix timestamps
    (seconds or milliseconds).
    """
    for key in keys:
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, str):
            # Try ISO format
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
            # Try YYYY-MM-DD prefix
            match = re.match(r'(\d{4}-\d{2}-\d{2})', val)
            if match:
                return match.group(1)
            # Try Twitter format: "Thu Oct 10 12:00:00 +0000 2024"
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


def filter_by_date_range(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
    log_fn: Callable[[str], None],
    noun: str = "items",
) -> List[Dict[str, Any]]:
    """Filter items to those within [from_date, to_date].

    Falls back to keeping all items if none are in range.
    """
    in_range = [i for i in items if i["date"] and from_date <= i["date"] <= to_date]
    out_of_range = len(items) - len(in_range)
    if in_range:
        if out_of_range:
            log_fn(f"Filtered {out_of_range} {noun} outside date range")
        return in_range
    log_fn(f"No {noun} within date range, keeping all {len(items)}")
    return items


def caption_snippet(text: str) -> str:
    """Truncate text to CAPTION_MAX_WORDS words."""
    if not text:
        return ""
    words = text.split()
    snippet = ' '.join(words[:CAPTION_MAX_WORDS])
    if len(words) > CAPTION_MAX_WORDS:
        snippet += '...'
    return snippet


def timeout_for_depth(depth: str) -> int:
    """Return HTTP timeout seconds for a given depth."""
    return 90 if depth == "quick" else 150 if depth == "default" else 240
