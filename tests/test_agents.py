"""
tests/test_agents.py
=====================
Integration-level tests for pipeline agents (aligned with current agent APIs).
Mocks external APIs (Gemini, Blogger, RSS, etc.).
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


MOCK_ENV = {
    "GEMINI_API_KEY": "fake_key",
    "BLOGGER_BLOG_ID": "123456789",
    "BLOGGER_OAUTH_CREDENTIALS": json.dumps({
        "token": "fake_token",
        "refresh_token": "fake_refresh",
        "client_id": "fake_client",
        "client_secret": "fake_secret",
    }),
    "YOUTUBE_API_KEY": "fake_yt_key",
    "FIREBASE_CREDENTIALS_JSON": '{"type":"service_account"}',
    "FIREBASE_DATABASE_URL": "https://test-rtdb.firebaseio.com",
    "DISQUS_SHORTNAME": "test-blog",
}


def _layer_meta(layer: str = "research-articles"):
    return {
        "slug": layer,
        "label": layer.replace("-", " ").title(),
        "color": "#2563EB",
        "section_template": ["Introduction", "Analysis", "Conclusion"],
    }


def _minimal_task():
    """Minimal task dict for SEO / downstream agents."""
    return {
        "genre_id": "technology",
        "genre_slug": "technology",
        "topic_slug": "ai",
        "genre_label": "Technology",
        "topic_label": "Artificial Intelligence",
        "topic_id": "artificial-intelligence",
        "genre_color": "#2563EB",
        "tone_profile": "professional",
        "layer": "research-articles",
        "layer_meta": _layer_meta(),
        "topic_idea": {
            "title": "Test Article Title",
            "angle": "An analytical angle",
            "keywords": ["AI", "machine learning", "models"],
            "suggested_word_count": 1200,
        },
        "post_draft": {
            "title": "Test Article Title",
            "slug": "test-article-title",
            "meta_description": "A concise meta description for testing.",
            "estimated_word_count": 1200,
            "html_body": "<p>Opening paragraph with a factual claim.</p>",
        },
        "research_brief": {"source_urls": [], "key_facts": [], "statistics": []},
        "post_with_citations": {"html_body": "<p>Body with citations.</p>", "references": []},
        "seo_data": {},
        "images": [],
        "video_data": {"needed": False, "embed_html": ""},
    }


class TestOrchestratorAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    def test_builds_task_packet(self):
        from agents.orchestrator import Orchestrator

        orch = Orchestrator()
        packet = orch.build_task_packet(
            genre="Technology",
            topic="Artificial Intelligence",
            layer="Research Articles",
        )
        self.assertIn("genre", packet)
        self.assertIn("topic", packet)
        self.assertIn("layer", packet)
        self.assertIn("task_id", packet)

    @patch.dict(os.environ, MOCK_ENV)
    def test_rotation_covers_all_genres_over_n_days(self):
        from agents.orchestrator import Orchestrator

        orch = Orchestrator()
        seen = {orch._pick_genre() for _ in range(15)}
        self.assertGreater(len(seen), 1)

    @patch.dict(os.environ, MOCK_ENV)
    def test_posts_per_day_config_respected(self):
        from agents.orchestrator import Orchestrator
        from config.settings import Settings

        settings = Settings()
        orch = Orchestrator()
        tasks = orch.generate_daily_tasks()
        self.assertEqual(len(tasks), settings.POSTS_PER_DAY)


class TestTopicDiscoveryAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.topic_discovery.call_gemini")
    def test_discover_returns_topic_idea(self, mock_cg):
        mock_cg.return_value = json.dumps({
            "title": "AI Regulation: What 2025 Brings",
            "angle": "Policy angle",
            "keywords": ["AI", "regulation"],
            "freshness_reason": "Trending",
            "suggested_word_count": 1200,
        })
        from agents.topic_discovery import TopicDiscoveryAgent

        agent = TopicDiscoveryAgent([])
        idea = agent.discover("technology", "artificial-intelligence", "research-articles")
        self.assertIn("title", idea)
        self.assertIn("keywords", idea)

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.topic_discovery.call_gemini")
    @patch("agents.topic_discovery.is_duplicate", return_value=True)
    def test_discover_suffixes_title_when_duplicate(self, _dup, mock_cg):
        mock_cg.return_value = json.dumps({
            "title": "Duplicate Title",
            "angle": "x",
            "keywords": ["k"],
            "freshness_reason": "r",
            "suggested_word_count": 1000,
        })
        from agents.topic_discovery import TopicDiscoveryAgent

        agent = TopicDiscoveryAgent([])
        idea = agent.discover("technology", "ai", "research-articles")
        self.assertNotEqual(idea["title"], "Duplicate Title")


class TestResearchAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.research.validate_urls", return_value=["https://arxiv.org/test"])
    @patch("agents.research.call_gemini")
    def test_returns_research_brief(self, mock_cg, _vu):
        mock_cg.return_value = json.dumps({
            "title": "LLM Survey",
            "key_facts": [{"fact": "LLMs scale.", "source_url": "https://arxiv.org/test", "source_name": "Paper", "year": 2024}],
            "statistics": [],
            "expert_quotes": [],
            "background_context": "ctx",
            "key_arguments": ["a"],
            "counterarguments": [],
            "source_urls": ["https://arxiv.org/test"],
            "suggested_image_search": "LLM",
            "suggested_video_search": "LLM video",
            "focus_keyword": "large language models",
            "lsi_keywords": ["LLM"],
        })
        from agents.research import ResearchAgent

        task = {
            "genre_label": "Technology",
            "topic_label": "AI",
            "layer": "research-articles",
            "topic_idea": {"title": "T", "angle": "a", "keywords": ["k"]},
            "tone_profile": "neutral",
            "layer_meta": _layer_meta(),
        }
        brief = ResearchAgent().research(task)
        self.assertIn("key_facts", brief)
        self.assertIn("source_urls", brief)
        self.assertIn("focus_keyword", brief)

    @patch.dict(os.environ, MOCK_ENV)
    @patch(
        "agents.research.validate_urls",
        return_value=["https://web.archive.org/web/20240101/https://dead-url.com"],
    )
    @patch("agents.research.call_gemini")
    def test_invalid_urls_can_resolve_to_archive_urls(self, mock_cg, _vu):
        mock_cg.return_value = json.dumps({
            "title": "T",
            "key_facts": [{"fact": "x", "source_url": "https://dead-url.com", "source_name": "S", "year": 2024}],
            "statistics": [],
            "expert_quotes": [],
            "background_context": "",
            "key_arguments": [],
            "counterarguments": [],
            "source_urls": ["https://dead-url.com"],
            "suggested_image_search": "",
            "suggested_video_search": "",
        })
        from agents.research import ResearchAgent

        task = {
            "genre_label": "Technology",
            "topic_label": "AI",
            "layer": "explainers",
            "topic_idea": {"title": "T", "angle": "a", "keywords": ["k"]},
            "tone_profile": "neutral",
            "layer_meta": _layer_meta("explainers"),
        }
        brief = ResearchAgent().research(task)
        self.assertIn("web.archive.org", str(brief))


class TestContentGenerationAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.content_generation.call_gemini")
    def test_returns_post_draft(self, mock_cg):
        research_brief = load_fixture("sample_research_brief.json")
        mock_cg.side_effect = [
            "<h1>Title</h1><p>Generated article body with enough words.</p>",
            "Meta description for SEO purposes here.",
        ]
        from agents.content_generation import ContentGenerationAgent

        task = {
            "genre_id": "technology",
            "genre_label": "Technology",
            "topic_id": "ai",
            "topic_label": "Artificial Intelligence",
            "layer": "research-articles",
            "tone_profile": "professional",
            "topic_idea": {
                "title": "GPT-5 Architecture Breakdown",
                "keywords": ["GPT", "architecture"],
                "suggested_word_count": 1200,
            },
            "layer_meta": _layer_meta(),
            "research_brief": research_brief,
        }
        draft = ContentGenerationAgent().generate(task)
        self.assertIn("title", draft)
        self.assertIn("html_body", draft)
        self.assertIn("meta_description", draft)

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.content_generation.call_gemini", side_effect=RuntimeError("Gemini failure"))
    def test_call_gemini_failure_propagates(self, _mock):
        from agents.content_generation import ContentGenerationAgent

        task = {
            "genre_id": "technology",
            "genre_label": "Technology",
            "topic_id": "ai",
            "topic_label": "AI",
            "layer": "explainers",
            "tone_profile": "neutral",
            "topic_idea": {"title": "T", "keywords": ["k"], "suggested_word_count": 800},
            "layer_meta": _layer_meta("explainers"),
            "research_brief": {},
        }
        with self.assertRaises(RuntimeError):
            ContentGenerationAgent().generate(task)


class TestReferenceCitationAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.reference_citation.call_gemini")
    @patch("agents.reference_citation.validate_url_with_fallback", side_effect=lambda u: u)
    def test_reference_section_lists_urls(self, _vu, mock_cg):
        mock_cg.return_value = "<p>Text <sup>[1]</sup></p>"
        from agents.reference_citation import ReferenceCitationAgent

        brief = load_fixture("sample_research_brief.json")
        agent = ReferenceCitationAgent()
        out = agent.process({
            "research_brief": brief,
            "post_draft": {"html_body": "<p>Claim about transformers.</p>"},
        })
        self.assertIn("[1]", out["html_body"])
        self.assertIn("arxiv.org", out["html_body"])

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.reference_citation.validate_url_with_fallback", return_value="#")
    def test_empty_sources_skips_reference_block_content(self, _vu):
        from agents.reference_citation import ReferenceCitationAgent

        agent = ReferenceCitationAgent()
        out = agent.process({
            "research_brief": {"source_urls": [], "key_facts": [], "statistics": [], "expert_quotes": []},
            "post_draft": {"html_body": "<p>No sources.</p>"},
        })
        self.assertNotIn("References", out["html_body"])


class TestSEOAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    def test_schema_script_contains_json_ld(self):
        from agents.seo import SEOAgent

        task = _minimal_task()
        seo = SEOAgent().optimize(task)
        self.assertIn("schema_script", seo)
        self.assertIn("ScholarlyArticle", seo["schema_script"])

    @patch.dict(os.environ, MOCK_ENV)
    def test_read_time_minutes_present(self):
        from agents.seo import SEOAgent

        task = _minimal_task()
        task["post_draft"]["estimated_word_count"] = 1200
        seo = SEOAgent().optimize(task)
        self.assertGreaterEqual(seo["read_time_minutes"], 1)


class TestImageAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.image_agent.ImageAgent._search_wikimedia")
    @patch("agents.image_agent.ImageAgent._get_unsplash")
    @patch("agents.image_agent.ImageAgent._search_nasa", return_value=None)
    def test_find_images_returns_entries(self, _nasa, mock_unsplash, mock_wm):
        mock_wm.return_value = {
            "url": "https://upload.wikimedia.org/test.jpg",
            "alt": "alt",
            "caption": "cap",
            "attribution": "attr",
            "source": "wikimedia",
        }
        mock_unsplash.return_value = None
        from agents.image_agent import ImageAgent

        task = _minimal_task()
        task["research_brief"] = {"suggested_image_search": "AI"}
        imgs = ImageAgent().find_images(task)
        self.assertTrue(imgs)
        self.assertIn("url", imgs[0])

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.image_agent.ImageAgent._search_wikimedia", return_value=None)
    @patch("agents.image_agent.ImageAgent._get_unsplash", return_value=None)
    @patch("agents.image_agent.ImageAgent._search_nasa", return_value=None)
    @patch("agents.image_agent.ImageAgent._get_pollinations_image")
    def test_pollinations_fallback_when_no_sources(self, mock_poll, *_):
        mock_poll.return_value = {
            "url": "https://image.pollinations.ai/prompt/test",
            "alt": "a",
            "caption": "c",
            "attribution": "p",
            "source": "pollinations",
        }
        from agents.image_agent import ImageAgent

        task = _minimal_task()
        imgs = ImageAgent().find_images(task)
        self.assertTrue(imgs)
        self.assertIn("pollinations", imgs[0]["url"])


class TestVideoAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.video_agent.requests.get")
    @patch("agents.video_agent.call_gemini")
    def test_howto_can_embed_youtube(self, mock_cg, mock_get):
        mock_cg.return_value = json.dumps({
            "needed": True,
            "reason": "How-To benefits from video",
            "search_query": "python tutorial",
        })
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "items": [{
                    "id": {"videoId": "dQw4w9WgXcQ"},
                    "snippet": {"title": "Tutorial", "channelTitle": "Ch"},
                }]
            },
        )
        from agents.video_agent import VideoAgent

        task = _minimal_task()
        task["layer"] = "how-to-guides"
        task["layer_meta"] = _layer_meta("how-to-guides")
        result = VideoAgent().decide_and_fetch(task)
        self.assertTrue(result.get("needed"))
        self.assertIn("youtube.com", result.get("embed_html") or "")

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.video_agent.call_gemini")
    def test_opinion_layer_can_skip_video(self, mock_cg):
        mock_cg.return_value = json.dumps({
            "needed": False,
            "reason": "Opinion piece",
            "search_query": None,
        })
        from agents.video_agent import VideoAgent

        task = _minimal_task()
        task["layer"] = "opinion-analysis"
        task["layer_meta"] = _layer_meta("opinion-analysis")
        result = VideoAgent().decide_and_fetch(task)
        self.assertFalse(result.get("needed"))


class _SeoData(dict):
    """Minimal seo_data for publisher tests."""

    def __init__(self):
        super().__init__(
            labels=["Technology", "AI", "Research Articles"],
            schema_script="<script></script>",
            author="Editor",
            canonical_url="https://example.blogspot.com/p",
            slug="test",
            read_time_minutes=5,
            og_tags="",
            pub_date="2025-01-01T00:00:00Z",
        )


class TestPublisherAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.publisher.PublisherAgent._append_to_log")
    @patch("agents.publisher.build")
    def test_publish_returns_url_metadata(self, mock_build, _log):
        mock_svc = MagicMock()
        mock_build.return_value = mock_svc
        mock_svc.posts.return_value.insert.return_value.execute.return_value = {
            "id": "post_1",
            "url": "https://example.blogspot.com/2025/01/test-post.html",
            "published": "2025-01-15T10:00:00Z",
        }
        from agents.publisher import PublisherAgent

        task = _minimal_task()
        task["seo_data"] = _SeoData()
        task["post_with_citations"] = {"html_body": "<p>x</p>", "references": [{"u": 1}]}
        task["images"] = []
        task["video_data"] = {"needed": False}
        pub = PublisherAgent().publish(task)
        self.assertIn("url", pub)
        self.assertIn("blogspot.com", pub["url"])


class TestSelfImprovementAgent(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    @patch("agents.self_improvement.call_gemini")
    @patch("agents.self_improvement.SelfImprovementAgent._save_changelog")
    @patch("agents.self_improvement.SelfImprovementAgent._save_taxonomy")
    @patch("agents.self_improvement.SelfImprovementAgent._apply_new_genres")
    @patch("agents.self_improvement.SelfImprovementAgent._apply_new_topics")
    @patch("agents.self_improvement.SelfImprovementAgent._fetch_trend_signals", return_value=["Signal A"])
    def test_monthly_expansion_returns_structure(
        self,
        mock_fetch,
        mock_apply_topics,
        mock_apply_genres,
        mock_save_tax,
        mock_save_changelog,
        mock_cg,
    ):
        mock_cg.return_value = json.dumps({
            "new_topics": [],
            "new_genres": [],
            "dismissed_signals": [],
        })
        from agents.self_improvement import SelfImprovementAgent

        proposals = SelfImprovementAgent().monthly_expansion()
        self.assertIsInstance(proposals, dict)
        mock_fetch.assert_called()

    @patch.dict(os.environ, MOCK_ENV)
    def test_weekly_review_has_genre_summary(self):
        from agents.self_improvement import SelfImprovementAgent

        agent = SelfImprovementAgent()
        agent.published_posts = [
            {"genre": "technology", "topic": "ai", "layer": "latest-news", "published_at": "2025-01-10T12:00:00Z"},
        ]
        report = agent.weekly_review()
        self.assertIn("top_genres", report)


class TestPipelineSmoke(unittest.TestCase):

    @patch.dict(os.environ, MOCK_ENV)
    def test_orchestrator_build_task_packet_with_fixture(self):
        research_brief = load_fixture("sample_research_brief.json")
        self.assertIn("source_urls", research_brief)
        from agents.orchestrator import Orchestrator

        orch = Orchestrator()
        packet = orch.build_task_packet("Technology", "AI", "Research Articles")
        self.assertIsNotNone(packet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
