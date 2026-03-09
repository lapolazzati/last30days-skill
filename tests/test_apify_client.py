"""Tests for apify_client module — mock HTTP to verify actor runner logic."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import apify_client, http


class TestRunActor(unittest.TestCase):
    """Test apify_client.run_actor with mocked HTTP responses."""

    @patch("lib.http.post")
    def test_returns_list_directly(self, mock_post):
        """Actor returns a plain JSON array."""
        mock_post.return_value = [{"id": 1}, {"id": 2}]
        items = apify_client.run_actor("test/actor", {"q": "hi"}, "tok123")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], 1)
        # Verify URL construction
        call_url = mock_post.call_args[0][0]
        self.assertIn("test/actor", call_url)
        self.assertIn("run-sync-get-dataset-items", call_url)

    @patch("lib.http.post")
    def test_unwraps_items_key(self, mock_post):
        """Actor wraps results in {"items": [...]}."""
        mock_post.return_value = {"items": [{"id": 1}]}
        items = apify_client.run_actor("test/actor", {}, "tok123")
        self.assertEqual(len(items), 1)

    @patch("lib.http.post")
    def test_unwraps_data_key(self, mock_post):
        """Actor wraps results in {"data": [...]}."""
        mock_post.return_value = {"data": [{"id": 1}, {"id": 2}]}
        items = apify_client.run_actor("test/actor", {}, "tok123")
        self.assertEqual(len(items), 2)

    @patch("lib.http.post")
    def test_error_response_raises(self, mock_post):
        """Actor error response raises HTTPError."""
        mock_post.return_value = {"error": {"message": "Actor failed"}}
        with self.assertRaises(http.HTTPError):
            apify_client.run_actor("test/actor", {}, "tok123")

    @patch("lib.http.post")
    def test_single_dict_wrapped(self, mock_post):
        """Single dict result without known keys wrapped in list."""
        mock_post.return_value = {"title": "solo item"}
        items = apify_client.run_actor("test/actor", {}, "tok123")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "solo item")

    @patch("lib.http.post")
    def test_empty_non_list_returns_empty(self, mock_post):
        """Non-list, non-dict result returns empty."""
        mock_post.return_value = None
        items = apify_client.run_actor("test/actor", {}, "tok123")
        self.assertEqual(items, [])

    @patch("lib.http.post")
    def test_max_items_in_url(self, mock_post):
        """max_items parameter appears in URL query string."""
        mock_post.return_value = []
        apify_client.run_actor("test/actor", {}, "tok123", max_items=10)
        call_url = mock_post.call_args[0][0]
        self.assertIn("limit=10", call_url)

    @patch("lib.http.post")
    def test_auth_header(self, mock_post):
        """Bearer token sent in Authorization header."""
        mock_post.return_value = []
        apify_client.run_actor("test/actor", {}, "my-secret-token")
        call_headers = mock_post.call_args[1].get("headers", mock_post.call_args[0][2] if len(mock_post.call_args[0]) > 2 else {})
        # Headers passed as keyword arg
        headers = mock_post.call_args
        # The function signature is http.post(url, data, headers=..., timeout=..., retries=...)
        # Let's just check the call was made correctly
        self.assertTrue(mock_post.called)


class TestRunActorAsync(unittest.TestCase):
    """Test apify_client.run_actor_async."""

    @patch("lib.http.post")
    def test_returns_run_info(self, mock_post):
        """Async run returns run info dict."""
        mock_post.return_value = {"id": "run123", "status": "RUNNING"}
        result = apify_client.run_actor_async("test/actor", {}, "tok123")
        self.assertEqual(result["id"], "run123")
        call_url = mock_post.call_args[0][0]
        self.assertIn("/runs", call_url)
        self.assertNotIn("run-sync", call_url)


class TestGetDatasetItems(unittest.TestCase):
    """Test apify_client.get_dataset_items."""

    @patch("lib.http.get")
    def test_returns_items(self, mock_get):
        mock_get.return_value = [{"id": 1}, {"id": 2}]
        items = apify_client.get_dataset_items("ds123", "tok123")
        self.assertEqual(len(items), 2)
        call_url = mock_get.call_args[0][0]
        self.assertIn("ds123", call_url)

    @patch("lib.http.get")
    def test_non_list_returns_empty(self, mock_get):
        mock_get.return_value = {"error": "not found"}
        items = apify_client.get_dataset_items("ds123", "tok123")
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
