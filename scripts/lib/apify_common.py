"""Shared helpers for Apify-backed social media modules.

Contains text processing, relevance scoring, and date parsing utilities
shared between apify_tiktok and apify_instagram.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

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


def tokenize(text: str) -> Set[str]:
    """Tokenize text, removing stopwords and expanding synonyms."""
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    tokens = {w for w in words if w not in STOPWORDS and len(w) > 1}
    expanded = set(tokens)
    for t in tokens:
        if t in SYNONYMS:
            expanded.update(SYNONYMS[t])
    return expanded


def compute_relevance(query: str, text: str, hashtags: List[str] = None) -> float:
    """Compute relevance score between query and text+hashtags."""
    q_tokens = tokenize(query)
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
    if not q_tokens:
        return 0.5
    overlap = len(q_tokens & t_tokens)
    ratio = overlap / len(q_tokens)
    return max(0.1, min(1.0, ratio))


def extract_core_subject(topic: str) -> str:
    """Extract core subject from verbose query by stripping prefixes and noise."""
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


def parse_date_from_keys(raw: Dict[str, Any], keys: List[str]) -> Optional[str]:
    """Extract a YYYY-MM-DD date string from a raw dict, trying multiple keys.

    Handles ISO strings, YYYY-MM-DD prefixes, and unix timestamps
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
