"""
tests/test_utils.py
====================
Unit tests for all utility modules in utils/.
Run with:  python -m pytest tests/test_utils.py -v

Tests use mocking to avoid hitting live APIs.
"""
import tempfile
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# quota_manager tests
# ─────────────────────────────────────────────────────────────────────────────
class TestQuotaManager(unittest.TestCase):

    def setUp(self):
        # Patch the state file path so tests don't touch real filesystem
        self.patcher = patch("utils.quota_manager.QUOTA_STATE_FILE", "/tmp/test_quota_state.json")
        self.patcher.start()
        # Remove stale state file if present
        try:
            os.remove("/tmp/test_quota_state.json")
        except FileNotFoundError:
            pass
        from utils.quota_manager import QuotaManager
        self.qm = QuotaManager()

    def tearDown(self):
        self.patcher.stop()

    def test_initial_state_is_zero(self):
        self.assertEqual(self.qm.get_usage("gemini-2.5-flash"), 0)

    def test_increment_usage(self):
        self.qm.increment("gemini-2.5-flash", tokens=1000)
        self.assertGreater(self.qm.get_usage("gemini-2.5-flash"), 0)

    def test_quota_not_exceeded_under_limit(self):
        self.assertFalse(self.qm.is_quota_exceeded("gemini-2.5-flash"))

    def test_quota_exceeded_at_limit(self):
        from utils.quota_manager import DAILY_LIMITS
        limit = DAILY_LIMITS.get("gemini-2.5-flash", 1_000_000)
        # Simulate usage at 101%
        self.qm.state["gemini-2.5-flash"]["tokens"] = int(limit * 1.01)
        self.assertTrue(self.qm.is_quota_exceeded("gemini-2.5-flash"))

    def test_fallback_model_returned_on_exceeded(self):
        from utils.quota_manager import DAILY_LIMITS
        limit = DAILY_LIMITS.get("gemini-2.5-flash", 1_000_000)
        self.qm.state["gemini-2.5-flash"]["tokens"] = int(limit * 1.01)
        fallback = self.qm.get_active_model()
        self.assertEqual(fallback, "gemini-1.5-flash")

    def test_primary_model_returned_under_limit(self):
        model = self.qm.get_active_model()
        self.assertEqual(model, "gemini-2.5-flash")

    def test_state_persists_to_disk(self):
        self.qm.increment("gemini-2.5-flash", tokens=500)
        self.qm.save()
        # Re-load and verify
        from utils.quota_manager import QuotaManager
        qm2 = QuotaManager()
        self.assertEqual(
            qm2.get_usage("gemini-2.5-flash"),
            self.qm.get_usage("gemini-2.5-flash")
        )

    def test_daily_reset_on_new_day(self):
        """If state date != today, counters reset to 0."""
        import datetime
        self.qm.state["gemini-2.5-flash"]["tokens"] = 99999
        self.qm.state["_date"] = "2000-01-01"  # old date
        self.qm.save()
        from utils.quota_manager import QuotaManager
        qm2 = QuotaManager()
        self.assertEqual(qm2.get_usage("gemini-2.5-flash"), 0)


# ─────────────────────────────────────────────────────────────────────────────
# dedup_checker tests
# ─────────────────────────────────────────────────────────────────────────────
class TestDedupChecker(unittest.TestCase):

    def setUp(self):
        self.log_path = os.path.join(
    tempfile.gettempdir(),
    "test_published_posts.json"
)
        # Write a small fake post log
        posts = [
            {"title": "How Transformers Work: A Complete Guide", "url": "https://example.blogspot.com/p1"},
            {"title": "Top 10 AI Tools in 2024", "url": "https://example.blogspot.com/p2"},
        ]
        with open(self.log_path, "w") as f:
            json.dump(posts, f)
        self.patcher = patch("utils.dedup_checker.PUBLISHED_POSTS_LOG", self.log_path)
        self.patcher.start()
        from utils.dedup_checker import DedupChecker
        self.dc = DedupChecker()

    def tearDown(self):
        self.patcher.stop()
        try:
            os.remove(self.log_path)
        except FileNotFoundError:
            pass

    def test_exact_duplicate_detected(self):
        self.assertTrue(self.dc.is_duplicate("How Transformers Work: A Complete Guide"))

    def test_fuzzy_duplicate_detected(self):
        # Slight rewording should still trigger similarity match
        self.assertTrue(self.dc.is_duplicate("How Transformer Models Work: The Complete Guide"))

    def test_new_title_not_duplicate(self):
        self.assertFalse(self.dc.is_duplicate("Quantum Computing in Healthcare: 2025 Outlook"))

    def test_empty_title_returns_false(self):
        self.assertFalse(self.dc.is_duplicate(""))

    def test_add_new_entry(self):
        new_title = "New Article About Climate Change"
        new_url   = "https://example.blogspot.com/p3"
        self.dc.add_entry(new_title, new_url)
        self.assertTrue(self.dc.is_duplicate(new_title))


# ─────────────────────────────────────────────────────────────────────────────
# link_validator tests
# ─────────────────────────────────────────────────────────────────────────────
class TestLinkValidator(unittest.TestCase):

    def setUp(self):
        from utils.link_validator import LinkValidator
        self.lv = LinkValidator()

    @patch("utils.link_validator.requests.head")
    def test_valid_url_passes(self, mock_head):
        mock_head.return_value = MagicMock(status_code=200)
        result = self.lv.validate("https://arxiv.org/abs/1706.03762")
        self.assertTrue(result["valid"])
        self.assertIsNone(result["archive_url"])

    @patch("utils.link_validator.requests.head")
    def test_404_url_triggers_archive_lookup(self, mock_head):
        mock_head.return_value = MagicMock(status_code=404)
        with patch(
            "utils.link_validator._get_archive_url",
            return_value="https://web.archive.org/web/20240101/https://dead-url.com",
        ) as mock_arch:
            result = self.lv.validate("https://dead-url.com/article")
            self.assertFalse(result["valid"])
            self.assertIsNotNone(result["archive_url"])
            mock_arch.assert_called_once()

    @patch("utils.link_validator.requests.head")
    def test_connection_error_marked_invalid(self, mock_head):
        import requests as req
        mock_head.side_effect = req.exceptions.ConnectionError("Timeout")
        result = self.lv.validate("https://nonexistent-domain-xyz.com")
        self.assertFalse(result["valid"])

    @patch("utils.link_validator.requests.head")
    def test_batch_validate_returns_all(self, mock_head):
        mock_head.return_value = MagicMock(status_code=200)
        urls = [
            "https://arxiv.org/abs/1706.03762",
            "https://arxiv.org/abs/2206.07682",
            "https://who.int/health-topics/coronavirus",
        ]
        results = self.lv.validate_batch(urls)
        self.assertEqual(len(results), len(urls))
        for r in results:
            self.assertIn("valid", r)
            self.assertIn("url", r)


# ─────────────────────────────────────────────────────────────────────────────
# rss_fetcher tests
# ─────────────────────────────────────────────────────────────────────────────
class TestRSSFetcher(unittest.TestCase):

    def setUp(self):
        from utils.rss_fetcher import RSSFetcher
        self.rf = RSSFetcher()

    @patch("utils.rss_fetcher.feedparser.parse")
    def test_trends_returns_list(self, mock_parse):
        mock_parse.return_value = MagicMock(
            entries=[
                MagicMock(title="AI regulation", summary="Summary 1"),
                MagicMock(title="Quantum computing", summary="Summary 2"),
            ]
        )
        results = self.rf.fetch_google_trends()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    @patch("utils.rss_fetcher.feedparser.parse")
    def test_reddit_returns_list(self, mock_parse):
        mock_parse.return_value = MagicMock(
            entries=[
                MagicMock(title="r/technology post 1", summary="Content 1"),
                MagicMock(title="r/technology post 2", summary="Content 2"),
            ]
        )
        results = self.rf.fetch_reddit("technology")
        self.assertIsInstance(results, list)

    @patch("utils.rss_fetcher._fetch_google_trends_serpapi", return_value=[])
    @patch("utils.rss_fetcher.feedparser.parse")
    def test_empty_feed_returns_empty_list(self, mock_parse, _mock_serp):
        mock_parse.return_value = MagicMock(entries=[])
        results = self.rf.fetch_google_trends()
        self.assertEqual(results, [])

    @patch("utils.rss_fetcher._fetch_google_trends_serpapi", return_value=[])
    @patch("utils.rss_fetcher.feedparser.parse")
    def test_malformed_entry_skipped_gracefully(self, mock_parse, _mock_serp):
        # Entry with no 'title' attribute simulates malformed feed item
        bad_entry = MagicMock(spec=[])  # no attributes
        mock_parse.return_value = MagicMock(entries=[bad_entry])
        # Should not raise, should return empty or partial list
        try:
            results = self.rf.fetch_google_trends()
            self.assertIsInstance(results, list)
        except Exception as e:
            self.fail(f"fetch_google_trends raised unexpectedly: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# gemini_client tests  (mocked — no real API calls)
# ─────────────────────────────────────────────────────────────────────────────
class TestGeminiClient(unittest.TestCase):

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def _mock_genai_client(self, side_effect=None, text="This is a generated response."):
        mi = MagicMock()
        if side_effect is not None:
            mi.models.generate_content.side_effect = side_effect
        else:
            mi.models.generate_content.return_value = MagicMock(text=text)
        return mi

    @patch("utils.gemini_client.genai.Client")
    def test_generate_returns_text(self, mock_client_cls):
        mock_client_cls.return_value = self._mock_genai_client()
        from utils.gemini_client import GeminiClient

        gc = GeminiClient()
        result = gc.generate("Write a test sentence.")
        self.assertIsInstance(result, str)
        self.assertIn("generated", result.lower())

    @patch("utils.gemini_client.genai.Client")
    def test_quota_exceeded_triggers_fallback(self, mock_client_cls):
        """First call fails, second succeeds (retry path)."""
        mock_client_cls.return_value = self._mock_genai_client(
            side_effect=[
                RuntimeError("rate limited"),
                MagicMock(text="Fallback response."),
            ]
        )
        from utils.gemini_client import GeminiClient

        gc = GeminiClient()
        result = gc.generate("Test prompt")
        self.assertEqual(mock_client_cls.return_value.models.generate_content.call_count, 2)
        self.assertIn("Fallback", result)

    @patch("utils.gemini_client.genai.Client")
    def test_network_error_raises_after_retries(self, mock_client_cls):
        mock_client_cls.return_value = self._mock_genai_client(
            side_effect=RuntimeError("Network down"),
        )
        from utils.gemini_client import GeminiClient

        gc = GeminiClient(max_retries=2)
        with self.assertRaises(RuntimeError):
            gc.generate("Test prompt")

    @patch("utils.gemini_client.genai.Client")
    def test_malformed_response_raises_value_error(self, mock_client_cls):
        mi = MagicMock()
        mi.models.generate_content.return_value = MagicMock(text=None)
        mock_client_cls.return_value = mi
        from utils.gemini_client import GeminiClient

        gc = GeminiClient()
        with self.assertRaises(RuntimeError):
            gc.generate("Test prompt")


# ─────────────────────────────────────────────────────────────────────────────
# blogger_client tests  (mocked)
# ─────────────────────────────────────────────────────────────────────────────
class TestBloggerClient(unittest.TestCase):

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "BLOGGER_BLOG_ID": "123456789",
            "BLOGGER_ACCESS_TOKEN": "fake_access_token",
        })
        self.env_patcher.start()
        from utils.blogger_client import BloggerClient

        self.bc = BloggerClient()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("utils.blogger_client.BloggerClient._get_token", return_value="test-access-token")
    @patch("utils.blogger_client.BloggerClient._post")
    def test_publish_post_returns_url(self, mock_post, _mock_token):
        mock_post.return_value = {
            "id": "987654321",
            "url": "https://example.blogspot.com/2025/01/test-post.html",
            "published": "2025-01-15T10:00:00Z",
        }
        result = self.bc.publish_post(
            title="Test Post Title",
            content="<p>Test content.</p>",
            labels=["Technology", "AI"],
        )
        self.assertIn("url", result)
        self.assertIn("blogspot.com", result["url"])

    @patch("utils.blogger_client.BloggerClient._get_token", return_value="test-access-token")
    @patch("utils.blogger_client.BloggerClient._post")
    def test_publish_post_handles_401(self, mock_post, _mock_token):
        from utils.blogger_client import BloggerAPIError

        mock_post.side_effect = BloggerAPIError(401, "Unauthorized")
        with self.assertRaises(BloggerAPIError) as ctx:
            self.bc.publish_post("Title", "<p>Body</p>", [])
        self.assertIn("401", str(ctx.exception))


# ─────────────────────────────────────────────────────────────────────────────
# firebase_client tests  (mocked)
# ─────────────────────────────────────────────────────────────────────────────
class TestFirebaseClient(unittest.TestCase):

    @patch("utils.firebase_client.firebase_admin.initialize_app")
    @patch("utils.firebase_client.firebase_admin.credentials.Certificate")
    def setUp(self, mock_cert, mock_init):
        self.env_patcher = patch.dict(os.environ, {
            "FIREBASE_CREDENTIALS_JSON": '{"type": "service_account"}',
            "FIREBASE_DATABASE_URL": "https://test-project-default-rtdb.firebaseio.com",
        })
        self.env_patcher.start()
        from utils.firebase_client import FirebaseClient
        self.fc = FirebaseClient()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("utils.firebase_client.db.reference")
    def test_get_reactions_returns_dict(self, mock_ref):
        mock_ref.return_value.get.return_value = {"like": 5, "insightful": 2, "helpful": 3}
        result = self.fc.get_reactions("post_123")
        self.assertIsInstance(result, dict)
        self.assertIn("like", result)

    @patch("utils.firebase_client.db.reference")
    def test_get_reactions_on_empty_post_returns_zeros(self, mock_ref):
        mock_ref.return_value.get.return_value = None
        result = self.fc.get_reactions("new_post_xyz")
        self.assertEqual(result.get("like", 0), 0)

    @patch("utils.firebase_client.db.reference")
    def test_increment_reaction(self, mock_ref):
        mock_ref.return_value.get.return_value = {"total": 5, "reactions": {"like": 5}}
        mock_ref.return_value.set.return_value = None
        self.fc.increment_reaction("post_123", "like")
        mock_ref.return_value.set.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)
