"""
settings.py — Central configuration loader for the autonomous blogger pipeline.
Reads from environment variables (GitHub Secrets) and local config files.
All agents import from here — single source of truth.
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── Base Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
TAXONOMY_DIR = BASE_DIR / "taxonomy"
PROMPTS_DIR = BASE_DIR / "prompts"
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"


# ─── API Keys & Secrets (from GitHub Actions secrets / .env) ──────────────────
class Secrets:
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    BLOGGER_CLIENT_ID: str = os.environ.get("BLOGGER_CLIENT_ID", "")
    BLOGGER_CLIENT_SECRET: str = os.environ.get("BLOGGER_CLIENT_SECRET", "")
    BLOGGER_REFRESH_TOKEN: str = os.environ.get("BLOGGER_REFRESH_TOKEN", "")
    BLOGGER_BLOG_ID: str = os.environ.get("BLOGGER_BLOG_ID", "")
    FIREBASE_SERVICE_ACCOUNT_JSON: str = (
        os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        or os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
    )
    FIREBASE_DATABASE_URL: str = os.environ.get("FIREBASE_DATABASE_URL", "")
    YOUTUBE_API_KEY: str = os.environ.get("YOUTUBE_API_KEY", "")
    DISQUS_SHORTNAME: str = os.environ.get("DISQUS_SHORTNAME", "")
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

    @classmethod
    def validate(cls) -> list[str]:
        """Returns list of missing required secrets."""
        required = [
            "GEMINI_API_KEY",
            "BLOGGER_CLIENT_ID",
            "BLOGGER_CLIENT_SECRET",
            "BLOGGER_REFRESH_TOKEN",
            "BLOGGER_BLOG_ID",
            "FIREBASE_SERVICE_ACCOUNT_JSON",
            "FIREBASE_DATABASE_URL",
        ]
        missing = [k for k in required if not getattr(cls, k)]
        return missing


# ─── Gemini Model Config ───────────────────────────────────────────────────────
class GeminiConfig:
    PRIMARY_MODEL: str = "gemini-3.1-flash-lite"
    FALLBACK_MODEL: str = "gemini-3.1-flash-lite"
    MAX_OUTPUT_TOKENS: int = 8192
    TEMPERATURE: float = 0.7
    TOP_P: float = 0.9

    # Free tier daily limits (conservative estimates)
    DAILY_REQUEST_LIMIT: int = 1450        # Leave 50 as buffer from 1500 free
    DAILY_TOKEN_LIMIT: int = 950_000       # Approx free tier daily token budget
    REQUESTS_PER_MINUTE: int = 15          # Flash free tier: 15 RPM
    TOKENS_PER_MINUTE: int = 250_000       # Flash free tier: 250K TPM

    # Retry / backoff config
    MAX_RETRIES: int = 5
    BASE_BACKOFF_SECONDS: float = 2.0
    MAX_BACKOFF_SECONDS: float = 120.0
    JITTER_FACTOR: float = 0.25            # ±25% jitter on backoff


# ─── Blogger Config ────────────────────────────────────────────────────────────
class BloggerConfig:
    BASE_URL: str = "https://www.googleapis.com/blogger/v3"
    AUTH_URL: str = "https://oauth2.googleapis.com/token"
    POSTS_PER_DAY: int = 3                 # Target posts per pipeline run
    DEFAULT_PUBLISH_STATUS: str = "live"   # "live" or "draft"
    POST_LABEL_LIMIT: int = 20             # Blogger max labels per post


class Settings:
    """Backward-compatible settings object (tests / older scripts)."""

    def __init__(self):
        self.POSTS_PER_DAY = BloggerConfig.POSTS_PER_DAY


class PipelineConfig:
    # How many topics to discover before picking one
    TOPIC_CANDIDATES: int = 10

    # Minimum word count per layer type
    MIN_WORD_COUNTS: dict = {
        "latest_news": 600,
        "research_articles": 1500,
        "how_to_guides": 1200,
        "opinion_analysis": 900,
        "case_studies": 1200,
        "interviews": 800,
        "listicles": 800,
        "reviews": 900,
        "explainers": 900,
    }

    # Target word count per layer type
    TARGET_WORD_COUNTS: dict = {
        "latest_news": 800,
        "research_articles": 2000,
        "how_to_guides": 1600,
        "opinion_analysis": 1200,
        "case_studies": 1500,
        "interviews": 1100,
        "listicles": 1100,
        "reviews": 1200,
        "explainers": 1200,
    }

    # Duplicate detection similarity threshold (0.0–1.0)
    DEDUP_SIMILARITY_THRESHOLD: float = 0.75

    # Max age for "trending" posts from RSS (days)
    RSS_MAX_AGE_DAYS: int = 3

    # Number of references required minimum
    MIN_REFERENCES: int = 3

    # Image search preference order
    IMAGE_SOURCES_PRIORITY: list = [
        "wikimedia",
        "unsplash",
        "nasa",
        "who_cdc",
        "pollinations_fallback",
    ]


# ─── YouTube Config ────────────────────────────────────────────────────────────
class YouTubeConfig:
    BASE_URL: str = "https://www.googleapis.com/youtube/v3"
    DAILY_QUOTA: int = 10_000
    SEARCH_COST_UNITS: int = 100           # Each search call costs 100 units
    MAX_SEARCHES_PER_DAY: int = 50         # 50 × 100 = 5000 units, leaves buffer


# ─── Logging Config ────────────────────────────────────────────────────────────
class LoggingConfig:
    LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

    PUBLISHED_POSTS_LOG: Path = LOGS_DIR / "published_posts.json"
    QUOTA_LOG: Path = LOGS_DIR / "quota_log.json"
    PIPELINE_RUNS_LOG: Path = LOGS_DIR / "pipeline_runs.json"
    QUOTA_STATE: Path = CONFIG_DIR / "quota_state.json"


# ─── JSON Config Loaders ───────────────────────────────────────────────────────
def load_taxonomy() -> dict:
    """Load the full genre/topic/layer taxonomy."""
    path = TAXONOMY_DIR / "taxonomy.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tone_profiles() -> dict:
    """Load genre-specific tone profiles."""
    path = CONFIG_DIR / "tone_profiles.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_section_templates() -> dict:
    """Load layer-specific section templates."""
    path = CONFIG_DIR / "section_templates.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(layer_key: str) -> str:
    """
    Load a Gemini prompt template for a given layer type.
    layer_key examples: 'news', 'research', 'howto', 'opinion', etc.
    """
    path = PROMPTS_DIR / f"{layer_key}_prompt.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_published_posts() -> list[dict]:
    """Load the log of previously published posts."""
    path = LoggingConfig.PUBLISHED_POSTS_LOG
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_published_posts(posts: list[dict]) -> None:
    """Persist the published posts log."""
    path = LoggingConfig.PUBLISHED_POSTS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logger for the pipeline."""
    logging.basicConfig(
        level=getattr(logging, LoggingConfig.LEVEL),
        format=LoggingConfig.FORMAT,
        datefmt=LoggingConfig.DATE_FORMAT,
    )
