"""Shared Apify API client for last30days skill.

Provides a common interface to run Apify actors synchronously and
retrieve dataset items. Used by apify_reddit, apify_x, apify_tiktok,
and apify_instagram modules.

API docs: https://docs.apify.com/api/v2
"""

import sys
from typing import Any, Dict, List, Optional

from . import http

APIFY_BASE = "https://api.apify.com/v2"


def _log(msg: str):
    """Log to stderr."""
    if sys.stderr.isatty():
        sys.stderr.write(f"[Apify] {msg}\n")
        sys.stderr.flush()


def run_actor(
    actor_id: str,
    run_input: Dict[str, Any],
    token: str,
    timeout: int = 120,
    memory_mbytes: Optional[int] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Run an Apify actor synchronously and return dataset items.

    Uses the run-sync-get-dataset-items endpoint which starts the actor,
    waits for it to finish, and returns the dataset items in one call.

    Args:
        actor_id: Actor ID (e.g. 'trudax/reddit-scraper')
        run_input: Actor input as a dict
        token: Apify API token
        timeout: HTTP timeout in seconds (actor must finish within 300s)
        memory_mbytes: Optional memory allocation in MB
        max_items: Optional limit on returned items

    Returns:
        List of dataset item dicts

    Raises:
        http.HTTPError: On API errors
    """
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"

    params = []
    if max_items is not None:
        params.append(f"limit={max_items}")
    if memory_mbytes is not None:
        params.append(f"memory={memory_mbytes}")
    params.append("clean=true")
    if params:
        url += "?" + "&".join(params)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    _log(f"Running actor {actor_id} (timeout={timeout}s)")

    result = http.post(url, run_input, headers=headers, timeout=timeout, retries=2)

    # The endpoint returns a JSON array of items directly
    if isinstance(result, list):
        _log(f"Got {len(result)} items from {actor_id}")
        return result

    # Some actors wrap in an object
    if isinstance(result, dict):
        # Check for error
        if "error" in result:
            err = result["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise http.HTTPError(f"Apify actor error: {msg}")
        # Try common wrapper keys
        for key in ("items", "data", "results"):
            if key in result and isinstance(result[key], list):
                _log(f"Got {len(result[key])} items from {actor_id}")
                return result[key]
        # Single-item result
        _log(f"Got 1 item from {actor_id}")
        return [result]

    return []


def run_actor_async(
    actor_id: str,
    run_input: Dict[str, Any],
    token: str,
    timeout: int = 120,
    memory_mbytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Start an Apify actor run asynchronously and return run info.

    Use this when the actor may take longer than 300s.

    Args:
        actor_id: Actor ID
        run_input: Actor input
        token: Apify API token
        timeout: HTTP timeout for the start request
        memory_mbytes: Optional memory allocation

    Returns:
        Run info dict with 'id', 'status', etc.
    """
    url = f"{APIFY_BASE}/acts/{actor_id}/runs"

    params = []
    if memory_mbytes is not None:
        params.append(f"memory={memory_mbytes}")
    if params:
        url += "?" + "&".join(params)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    return http.post(url, run_input, headers=headers, timeout=timeout, retries=2)


def get_dataset_items(
    dataset_id: str,
    token: str,
    max_items: Optional[int] = None,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Fetch items from an Apify dataset.

    Args:
        dataset_id: Dataset ID
        token: Apify API token
        max_items: Optional limit
        timeout: HTTP timeout

    Returns:
        List of dataset item dicts
    """
    url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
    params = ["clean=true"]
    if max_items is not None:
        params.append(f"limit={max_items}")
    url += "?" + "&".join(params)

    headers = {
        "Authorization": f"Bearer {token}",
    }

    result = http.get(url, headers=headers, timeout=timeout, retries=2)
    if isinstance(result, list):
        return result
    return []
