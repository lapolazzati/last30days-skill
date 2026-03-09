"""Tests for Apify social modules: apify_reddit, apify_x, apify_tiktok, apify_instagram.

Covers:
- Mock run_actor unit tests for each module
- Normalization of sample API responses
- Date parsing across timestamp formats
- Shared apify_common utilities
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import apify_common
from lib import apify_reddit
from lib import apify_x
from lib import apify_tiktok
from lib import apify_instagram


# ---------------------------------------------------------------------------
# apify_common tests
# ---------------------------------------------------------------------------

class TestApifyCommonTokenize(unittest.TestCase):
    """Test shared tokenizer."""

    def test_basic_tokenization(self):
        tokens = apify_common.tokenize("Claude Code is great")
        self.assertIn("claude", tokens)
        self.assertIn("code", tokens)
        self.assertIn("great", tokens)
        # Stopwords removed
        self.assertNotIn("is", tokens)

    def test_synonym_expansion(self):
        tokens = apify_common.tokenize("javascript tips")
        self.assertIn("javascript", tokens)
        self.assertIn("js", tokens)

    def test_empty_string(self):
        tokens = apify_common.tokenize("")
        self.assertEqual(tokens, set())

    def test_single_char_filtered(self):
        tokens = apify_common.tokenize("a I x")
        # 'a' and 'I' are stopwords; 'x' is single char
        self.assertEqual(tokens, set())


class TestApifyCommonRelevance(unittest.TestCase):
    """Test shared relevance scoring."""

    def test_exact_match(self):
        score = apify_common.compute_relevance("claude code", "Claude Code tricks")
        self.assertGreaterEqual(score, 0.8)

    def test_no_match(self):
        score = apify_common.compute_relevance("quantum physics", "cat dancing video")
        self.assertGreaterEqual(score, 0.1)

    def test_empty_query(self):
        score = apify_common.compute_relevance("", "anything")
        self.assertEqual(score, 0.5)

    def test_hashtag_boost(self):
        without = apify_common.compute_relevance("react", "random video")
        with_ht = apify_common.compute_relevance("react", "random video", ["reactjs"])
        self.assertGreater(with_ht, without)


class TestApifyCommonExtractCore(unittest.TestCase):
    """Test shared core subject extraction."""

    def test_strips_prefix(self):
        result = apify_common.extract_core_subject("what are the best claude code tips")
        self.assertNotIn("what are the best", result)
        self.assertIn("claude", result)

    def test_strips_noise(self):
        result = apify_common.extract_core_subject("latest trending updates on React")
        self.assertNotIn("latest", result)
        self.assertNotIn("trending", result)

    def test_preserves_core(self):
        result = apify_common.extract_core_subject("Claude Code")
        self.assertEqual(result, "claude code")


class TestApifyCommonDateParsing(unittest.TestCase):
    """Test shared date parsing across formats."""

    def test_iso_string(self):
        raw = {"createdAt": "2026-03-01T12:00:00Z"}
        result = apify_common.parse_date_from_keys(raw, ["createdAt"])
        self.assertEqual(result, "2026-03-01")

    def test_unix_timestamp_seconds(self):
        raw = {"created": 1772006400}  # 2026-02-26 approx
        result = apify_common.parse_date_from_keys(raw, ["created"])
        self.assertIsNotNone(result)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2}")

    def test_unix_timestamp_millis(self):
        raw = {"timestamp": 1772006400000}
        result = apify_common.parse_date_from_keys(raw, ["timestamp"])
        self.assertIsNotNone(result)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2}")

    def test_yyyy_mm_dd_prefix(self):
        raw = {"date": "2026-03-05 extra stuff"}
        result = apify_common.parse_date_from_keys(raw, ["date"])
        self.assertEqual(result, "2026-03-05")

    def test_twitter_format(self):
        raw = {"created_at": "Mon Mar 02 15:00:00 +0000 2026"}
        result = apify_common.parse_date_from_keys(raw, ["created_at"])
        self.assertEqual(result, "2026-03-02")

    def test_no_matching_key(self):
        raw = {"unrelated": "value"}
        result = apify_common.parse_date_from_keys(raw, ["createdAt", "date"])
        self.assertIsNone(result)

    def test_empty_value(self):
        raw = {"createdAt": ""}
        result = apify_common.parse_date_from_keys(raw, ["createdAt"])
        self.assertIsNone(result)

    def test_tries_multiple_keys(self):
        raw = {"date": "2026-03-01"}
        result = apify_common.parse_date_from_keys(raw, ["createdAt", "date"])
        self.assertEqual(result, "2026-03-01")


class TestApifyCommonCaptionSnippet(unittest.TestCase):

    def test_short_text(self):
        self.assertEqual(apify_common.caption_snippet("hello world"), "hello world")

    def test_empty_text(self):
        self.assertEqual(apify_common.caption_snippet(""), "")

    def test_none_text(self):
        self.assertEqual(apify_common.caption_snippet(None), "")


class TestApifyCommonTimeout(unittest.TestCase):

    def test_quick(self):
        self.assertEqual(apify_common.timeout_for_depth("quick"), 90)

    def test_default(self):
        self.assertEqual(apify_common.timeout_for_depth("default"), 150)

    def test_deep(self):
        self.assertEqual(apify_common.timeout_for_depth("deep"), 240)


class TestApifyCommonMakeLogger(unittest.TestCase):

    def test_returns_callable(self):
        log = apify_common.make_logger("Test")
        self.assertTrue(callable(log))

    def test_logger_writes_to_stderr(self):
        import io
        log = apify_common.make_logger("Test")
        # When stderr is not a tty, logger is silent (no crash)
        log("test message")  # should not raise


class TestApifyCommonFilterByDateRange(unittest.TestCase):

    def test_filters_out_of_range(self):
        items = [
            {"date": "2026-03-01", "id": 1},
            {"date": "2026-02-15", "id": 2},
            {"date": "2026-03-05", "id": 3},
        ]
        result = apify_common.filter_by_date_range(
            items, "2026-03-01", "2026-03-09", lambda m: None)
        self.assertEqual(len(result), 2)
        self.assertEqual([r["id"] for r in result], [1, 3])

    def test_keeps_all_when_none_in_range(self):
        items = [
            {"date": "2025-01-01", "id": 1},
            {"date": "2025-01-02", "id": 2},
        ]
        result = apify_common.filter_by_date_range(
            items, "2026-03-01", "2026-03-09", lambda m: None)
        self.assertEqual(len(result), 2)

    def test_skips_items_without_date(self):
        items = [
            {"date": None, "id": 1},
            {"date": "2026-03-01", "id": 2},
        ]
        result = apify_common.filter_by_date_range(
            items, "2026-03-01", "2026-03-09", lambda m: None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 2)


class TestApifyCommonRelevancePreTokenized(unittest.TestCase):
    """Test that pre-tokenized query produces same results."""

    def test_same_result_with_pretokenized(self):
        q = "claude code"
        text = "Claude Code is amazing"
        score_normal = apify_common.compute_relevance(q, text)
        q_tokens = apify_common.tokenize(q)
        score_pre = apify_common.compute_relevance(q, text, _q_tokens=q_tokens)
        self.assertEqual(score_normal, score_pre)


# ---------------------------------------------------------------------------
# apify_reddit tests
# ---------------------------------------------------------------------------

SAMPLE_REDDIT_ITEMS = [
    {
        "title": "Claude Code is incredible for AI development",
        "permalink": "/r/ClaudeAI/comments/abc123/claude_code_is_incredible/",
        "subreddit": "ClaudeAI",
        "score": 250,
        "numberOfComments": 45,
        "createdAt": "2026-03-01T10:00:00Z",
    },
    {
        "title": "Best AI coding assistants 2026",
        "url": "https://www.reddit.com/r/programming/comments/def456/best_ai_coding/",
        "communityName": "programming",
        "score": 120,
        "num_comments": 30,
        "created_utc": 1772006400,
    },
]


class TestApifyRedditSearchMock(unittest.TestCase):
    """Test apify_reddit.search_reddit with mocked actor."""

    def test_no_token_returns_error(self):
        result = apify_reddit.search_reddit("test", "2026-02-01", "2026-03-01")
        self.assertEqual(result["items"], [])
        self.assertIn("No APIFY_API_TOKEN", result["error"])

    @patch("lib.apify_client.run_actor")
    def test_parses_reddit_items(self, mock_run):
        mock_run.return_value = SAMPLE_REDDIT_ITEMS
        result = apify_reddit.search_reddit(
            "claude code", "2026-02-01", "2026-03-09", token="tok123"
        )
        items = result["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertIn("reddit.com", items[0]["url"])
        self.assertIn("/comments/", items[0]["url"])

    @patch("lib.apify_client.run_actor")
    def test_date_filtering(self, mock_run):
        mock_run.return_value = SAMPLE_REDDIT_ITEMS
        # Narrow date range that should exclude some items
        result = apify_reddit.search_reddit(
            "claude code", "2026-03-01", "2026-03-09", token="tok123"
        )
        for item in result["items"]:
            if item["date"]:
                self.assertGreaterEqual(item["date"], "2026-03-01")

    @patch("lib.apify_client.run_actor", side_effect=Exception("Network error"))
    def test_handles_exception(self, mock_run):
        result = apify_reddit.search_reddit("test", "2026-02-01", "2026-03-01", token="tok")
        self.assertEqual(result["items"], [])
        self.assertIn("Network error", result["error"])

    def test_actor_id_matches_docs(self):
        self.assertEqual(apify_reddit.ACTOR_ID, "automation-lab/reddit-scraper")


class TestApifyRedditParseDate(unittest.TestCase):

    def test_iso_date(self):
        raw = {"createdAt": "2026-03-01T12:00:00Z"}
        self.assertEqual(apify_reddit._parse_date(raw), "2026-03-01")

    def test_unix_timestamp(self):
        raw = {"created_utc": 1772006400}
        result = apify_reddit._parse_date(raw)
        self.assertIsNotNone(result)

    def test_no_date(self):
        self.assertIsNone(apify_reddit._parse_date({}))


class TestApifyRedditNormalization(unittest.TestCase):

    def test_filters_non_comment_urls(self):
        """Items without /comments/ in URL are skipped."""
        items = [{"title": "test", "url": "https://example.com", "score": 10}]
        result = apify_reddit._parse_items(items, "test", "2000-01-01", "2030-01-01")
        self.assertEqual(len(result), 0)

    def test_skips_empty_title(self):
        items = [{"title": "", "permalink": "/r/test/comments/abc/test/", "score": 10}]
        result = apify_reddit._parse_items(items, "test", "2000-01-01", "2030-01-01")
        self.assertEqual(len(result), 0)

    def test_relevance_from_score(self):
        items = [{"title": "High score post", "permalink": "/r/test/comments/abc/test/",
                  "score": 1000, "createdAt": "2026-03-01"}]
        result = apify_reddit._parse_items(items, "test", "2026-02-01", "2026-03-09")
        self.assertGreater(result[0]["relevance"], 0.5)


# ---------------------------------------------------------------------------
# apify_x tests
# ---------------------------------------------------------------------------

SAMPLE_X_ITEMS = [
    {
        "full_text": "Claude Code just shipped MCP support, this changes everything",
        "user": {"screen_name": "aidev"},
        "id_str": "123456789",
        "favorite_count": 500,
        "retweet_count": 100,
        "reply_count": 20,
        "createdAt": "2026-03-02T15:00:00Z",
    },
    {
        "text": "Another take on AI coding tools",
        "author": {"username": "techwriter"},
        "id": "987654321",
        "likeCount": 50,
        "retweetCount": 10,
        "date": "2026-03-03",
    },
]


class TestApifyXSearchMock(unittest.TestCase):
    """Test apify_x.search_x with mocked actor."""

    def test_no_token_returns_error(self):
        result = apify_x.search_x("test", "2026-02-01", "2026-03-01")
        self.assertEqual(result["items"], [])
        self.assertIn("No APIFY_API_TOKEN", result["error"])

    @patch("lib.apify_client.run_actor")
    def test_parses_x_items(self, mock_run):
        mock_run.return_value = SAMPLE_X_ITEMS
        result = apify_x.search_x("claude code", "2026-02-01", "2026-03-09", token="tok123")
        items = result["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertIn("x.com", items[0]["url"])

    @patch("lib.apify_client.run_actor")
    def test_engagement_parsed(self, mock_run):
        mock_run.return_value = SAMPLE_X_ITEMS
        result = apify_x.search_x("claude code", "2026-02-01", "2026-03-09", token="tok123")
        eng = result["items"][0]["engagement"]
        self.assertEqual(eng["likes"], 500)
        self.assertEqual(eng["reposts"], 100)

    @patch("lib.apify_client.run_actor", side_effect=Exception("Timeout"))
    def test_handles_exception(self, mock_run):
        result = apify_x.search_x("test", "2026-02-01", "2026-03-01", token="tok")
        self.assertEqual(result["items"], [])
        self.assertIn("Timeout", result["error"])

    def test_actor_id_matches_docs(self):
        self.assertEqual(apify_x.ACTOR_ID, "scraper_one/x-posts-search")


class TestApifyXParseDate(unittest.TestCase):

    def test_iso_date(self):
        raw = {"createdAt": "2026-03-02T15:00:00Z"}
        self.assertEqual(apify_x._parse_date(raw), "2026-03-02")

    def test_twitter_format(self):
        raw = {"created_at": "Mon Mar 02 15:00:00 +0000 2026"}
        result = apify_x._parse_date(raw)
        self.assertEqual(result, "2026-03-02")

    def test_no_date(self):
        self.assertIsNone(apify_x._parse_date({}))


class TestApifyXNormalization(unittest.TestCase):

    def test_skips_empty_text(self):
        items = [{"full_text": "", "user": {"screen_name": "a"}, "id_str": "1"}]
        result = apify_x._parse_items(items, "test", "2000-01-01", "2030-01-01")
        self.assertEqual(len(result), 0)

    def test_constructs_url_from_handle_and_id(self):
        items = [{
            "text": "Hello world",
            "user": {"screen_name": "testuser"},
            "id_str": "12345",
            "createdAt": "2026-03-01",
        }]
        result = apify_x._parse_items(items, "test", "2026-02-01", "2026-03-09")
        self.assertEqual(len(result), 1)
        self.assertIn("testuser", result[0]["url"])
        self.assertIn("12345", result[0]["url"])


# ---------------------------------------------------------------------------
# apify_tiktok tests
# ---------------------------------------------------------------------------

SAMPLE_TIKTOK_ITEMS = [
    {
        "id": "7001",
        "text": "Claude Code slash commands tutorial #claudecode #ai",
        "author": {"uniqueId": "aicoach"},
        "stats": {"playCount": 500000, "diggCount": 20000, "commentCount": 300, "shareCount": 1500},
        "hashtags": [{"name": "claudecode"}, {"name": "ai"}],
        "webVideoUrl": "https://www.tiktok.com/@aicoach/video/7001",
        "createTime": 1772006400,
    },
    {
        "id": "7002",
        "desc": "React tips for beginners",
        "authorMeta": {"name": "webdev"},
        "statistics": {"play_count": 100000, "digg_count": 5000, "comment_count": 100, "share_count": 200},
        "challenges": [{"title": "reactjs"}],
        "created_at": "2026-03-03",
    },
]


class TestApifyTikTokSearchMock(unittest.TestCase):
    """Test apify_tiktok.search_and_enrich with mocked actor."""

    def test_no_token_returns_error(self):
        result = apify_tiktok.search_and_enrich("test", "2026-02-01", "2026-03-01")
        self.assertEqual(result["items"], [])
        self.assertIn("No APIFY_API_TOKEN", result["error"])

    @patch("lib.apify_client.run_actor")
    def test_parses_tiktok_items(self, mock_run):
        mock_run.return_value = SAMPLE_TIKTOK_ITEMS
        result = apify_tiktok.search_and_enrich(
            "claude code", "2026-02-01", "2026-03-09", token="tok123"
        )
        items = result["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["engagement"]["views"], 500000)

    @patch("lib.apify_client.run_actor")
    def test_hashtags_parsed(self, mock_run):
        mock_run.return_value = SAMPLE_TIKTOK_ITEMS
        result = apify_tiktok.search_and_enrich(
            "claude code", "2026-02-01", "2026-03-09", token="tok123"
        )
        # Find item with hashtags
        items_with_ht = [i for i in result["items"] if i["hashtags"]]
        self.assertTrue(len(items_with_ht) > 0)
        self.assertIn("claudecode", items_with_ht[0]["hashtags"])

    @patch("lib.apify_client.run_actor")
    def test_sorted_by_views(self, mock_run):
        mock_run.return_value = SAMPLE_TIKTOK_ITEMS
        result = apify_tiktok.search_and_enrich(
            "code", "2026-02-01", "2026-03-09", token="tok123"
        )
        items = result["items"]
        if len(items) >= 2:
            self.assertGreaterEqual(
                items[0]["engagement"]["views"],
                items[1]["engagement"]["views"],
            )

    @patch("lib.apify_client.run_actor", side_effect=Exception("Boom"))
    def test_handles_exception(self, mock_run):
        result = apify_tiktok.search_and_enrich("test", "2026-02-01", "2026-03-01", token="tok")
        self.assertEqual(result["items"], [])
        self.assertIn("Boom", result["error"])

    def test_actor_id_matches_docs(self):
        self.assertEqual(apify_tiktok.ACTOR_ID, "epctex/tiktok-search-scraper")


class TestApifyTikTokParseDate(unittest.TestCase):

    def test_unix_timestamp(self):
        raw = {"createTime": 1772006400}
        result = apify_tiktok._parse_date(raw)
        self.assertIsNotNone(result)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2}")

    def test_iso_string(self):
        raw = {"created_at": "2026-03-03"}
        result = apify_tiktok._parse_date(raw)
        self.assertEqual(result, "2026-03-03")

    def test_no_date(self):
        self.assertIsNone(apify_tiktok._parse_date({}))


class TestApifyTikTokNormalization(unittest.TestCase):

    def test_skips_non_dict(self):
        result = apify_tiktok._parse_items(["not a dict"], "test", "2000-01-01", "2030-01-01", {"max_items": 10})
        self.assertEqual(len(result), 0)

    def test_constructs_url_from_author_and_id(self):
        items = [{
            "id": "123", "text": "hello", "author": {"uniqueId": "user1"},
            "stats": {"playCount": 100}, "createTime": "2026-03-01",
        }]
        result = apify_tiktok._parse_items(items, "test", "2026-02-01", "2026-03-09", {"max_items": 10})
        self.assertIn("user1", result[0]["url"])
        self.assertIn("123", result[0]["url"])

    def test_caption_snippet_populated(self):
        items = [{
            "id": "1", "text": "A " * 100,
            "author": {"uniqueId": "u"}, "stats": {},
            "createTime": "2026-03-01",
        }]
        result = apify_tiktok._parse_items(items, "test", "2026-02-01", "2026-03-09", {"max_items": 10})
        self.assertTrue(len(result[0]["caption_snippet"]) > 0)


class TestApifyTikTokParseResponse(unittest.TestCase):

    def test_extracts_items(self):
        resp = {"items": [{"id": 1}]}
        self.assertEqual(len(apify_tiktok.parse_tiktok_response(resp)), 1)

    def test_empty_response(self):
        self.assertEqual(apify_tiktok.parse_tiktok_response({}), [])


# ---------------------------------------------------------------------------
# apify_instagram tests
# ---------------------------------------------------------------------------

SAMPLE_INSTAGRAM_ITEMS = [
    {
        "id": "3001",
        "shortcode": "ABC123",
        "caption": {"text": "Amazing AI workflow #claudecode #productivity"},
        "videoPlayCount": 200000,
        "likesCount": 8000,
        "commentsCount": 150,
        "owner": {"username": "techinfluencer"},
        "taken_at": 1772006400,
    },
    {
        "pk": "3002",
        "code": "DEF456",
        "caption": "Simple string caption #react",
        "video_play_count": 50000,
        "like_count": 2000,
        "comment_count": 50,
        "user": {"username": "webdevguru"},
        "timestamp": "2026-03-04T09:00:00Z",
    },
]


class TestApifyInstagramSearchMock(unittest.TestCase):
    """Test apify_instagram.search_and_enrich with mocked actor."""

    def test_no_token_returns_error(self):
        result = apify_instagram.search_and_enrich("test", "2026-02-01", "2026-03-01")
        self.assertEqual(result["items"], [])
        self.assertIn("No APIFY_API_TOKEN", result["error"])

    @patch("lib.apify_client.run_actor")
    def test_parses_instagram_items(self, mock_run):
        mock_run.return_value = SAMPLE_INSTAGRAM_ITEMS
        result = apify_instagram.search_and_enrich(
            "claude code", "2026-02-01", "2026-03-09", token="tok123"
        )
        items = result["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["engagement"]["views"], 200000)

    @patch("lib.apify_client.run_actor")
    def test_caption_dict_parsed(self, mock_run):
        """Caption as dict with text key is correctly extracted."""
        mock_run.return_value = SAMPLE_INSTAGRAM_ITEMS
        result = apify_instagram.search_and_enrich(
            "claude code", "2026-02-01", "2026-03-09", token="tok123"
        )
        items = result["items"]
        # First item has caption as dict
        item_with_dict_caption = [i for i in items if "Amazing" in i.get("text", "")]
        self.assertTrue(len(item_with_dict_caption) > 0)

    @patch("lib.apify_client.run_actor")
    def test_hashtags_extracted_from_caption(self, mock_run):
        mock_run.return_value = SAMPLE_INSTAGRAM_ITEMS
        result = apify_instagram.search_and_enrich(
            "claude code", "2026-02-01", "2026-03-09", token="tok123"
        )
        all_hashtags = []
        for item in result["items"]:
            all_hashtags.extend(item["hashtags"])
        self.assertIn("claudecode", all_hashtags)

    @patch("lib.apify_client.run_actor")
    def test_url_from_shortcode(self, mock_run):
        """URL constructed from shortcode when not directly provided."""
        mock_run.return_value = [SAMPLE_INSTAGRAM_ITEMS[0]]
        result = apify_instagram.search_and_enrich(
            "test", "2026-02-01", "2026-03-09", token="tok123"
        )
        items = result["items"]
        self.assertIn("instagram.com/reel/ABC123", items[0]["url"])

    @patch("lib.apify_client.run_actor", side_effect=Exception("API down"))
    def test_handles_exception(self, mock_run):
        result = apify_instagram.search_and_enrich("test", "2026-02-01", "2026-03-01", token="tok")
        self.assertEqual(result["items"], [])
        self.assertIn("API down", result["error"])

    def test_actor_id_matches_docs(self):
        self.assertEqual(apify_instagram.ACTOR_ID, "apify/instagram-reel-scraper")


class TestApifyInstagramParseDate(unittest.TestCase):

    def test_unix_timestamp(self):
        raw = {"taken_at": 1772006400}
        result = apify_instagram._parse_date(raw)
        self.assertIsNotNone(result)

    def test_iso_string(self):
        raw = {"timestamp": "2026-03-04T09:00:00Z"}
        result = apify_instagram._parse_date(raw)
        self.assertEqual(result, "2026-03-04")

    def test_no_date(self):
        self.assertIsNone(apify_instagram._parse_date({}))


class TestApifyInstagramNormalization(unittest.TestCase):

    def test_string_caption(self):
        """String caption (not dict) is handled."""
        items = [{
            "id": "1", "caption": "Just a string #test",
            "videoPlayCount": 100, "likesCount": 10, "commentsCount": 1,
            "owner": {"username": "u"}, "shortcode": "XYZ",
            "taken_at": "2026-03-01",
        }]
        result = apify_instagram._parse_items(items, "test", "2026-02-01", "2026-03-09")
        self.assertEqual(len(result), 1)
        self.assertIn("test", result[0]["hashtags"])

    def test_sorted_by_views(self):
        items = [
            {"id": "1", "caption": "low", "videoPlayCount": 100, "owner": {"username": "a"},
             "shortcode": "A", "taken_at": "2026-03-01"},
            {"id": "2", "caption": "high", "videoPlayCount": 99999, "owner": {"username": "b"},
             "shortcode": "B", "taken_at": "2026-03-01"},
        ]
        result = apify_instagram._parse_items(items, "test", "2026-02-01", "2026-03-09")
        self.assertEqual(result[0]["engagement"]["views"], 99999)


class TestApifyInstagramParseResponse(unittest.TestCase):

    def test_extracts_items(self):
        resp = {"items": [{"id": 1}]}
        self.assertEqual(len(apify_instagram.parse_instagram_response(resp)), 1)

    def test_empty_response(self):
        self.assertEqual(apify_instagram.parse_instagram_response({}), [])


class TestApifyInstagramExtractHashtags(unittest.TestCase):

    def test_extracts_hashtags(self):
        result = apify_instagram._extract_hashtags("Check this out #ai #coding")
        self.assertEqual(result, ["ai", "coding"])

    def test_no_hashtags(self):
        self.assertEqual(apify_instagram._extract_hashtags("No tags here"), [])

    def test_empty_string(self):
        self.assertEqual(apify_instagram._extract_hashtags(""), [])

    def test_none_input(self):
        self.assertEqual(apify_instagram._extract_hashtags(None), [])


if __name__ == "__main__":
    unittest.main()
