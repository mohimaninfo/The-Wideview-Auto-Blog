"""
blogger_client.py — Blogger API v3 wrapper with OAuth2 token refresh.

Handles:
- Token refresh using stored refresh token (no browser interaction needed)
- Post creation, update, and listing
- Label management
- Draft and live publishing
- Graceful error handling for all API responses
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from config.settings import Secrets, BloggerConfig

logger = logging.getLogger(__name__)


class BloggerAPIError(Exception):
    """Raised when the Blogger API returns an error response."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Blogger API error {status_code}: {message}")


class BloggerClient:
    """
    Wrapper around the Blogger API v3.
    Uses OAuth2 with offline access (refresh token) — no browser required.
    """

    def __init__(self):
        self.blog_id = Secrets.BLOGGER_BLOG_ID
        self.base_url = BloggerConfig.BASE_URL
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ── Authentication ────────────────────────────────────────────────────────

    def _refresh_access_token(self) -> str:
        """
        Exchange the stored refresh token for a fresh access token.
        Tokens typically expire after 3600 seconds (1 hour).
        """
        logger.debug("Refreshing Blogger OAuth2 access token...")
        response = requests.post(
            BloggerConfig.AUTH_URL,
            data={
                "client_id": Secrets.BLOGGER_CLIENT_ID,
                "client_secret": Secrets.BLOGGER_CLIENT_SECRET,
                "refresh_token": Secrets.BLOGGER_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise BloggerAPIError(
                response.status_code,
                f"Token refresh failed: {response.text}"
            )

        data = response.json()
        self._access_token = data["access_token"]
        # Set expiry 5 minutes early to avoid edge-case expirations
        self._token_expiry = time.time() + data.get("expires_in", 3600) - 300
        logger.debug("Access token refreshed successfully.")
        return self._access_token

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if not self._access_token or time.time() >= self._token_expiry:
            return self._refresh_access_token()
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ── Core HTTP helpers ─────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self._headers(), params=params, timeout=30)
        return self._handle_response(response)

    def _post(self, endpoint: str, body: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        response = requests.post(
            url, headers=self._headers(), json=body, timeout=30
        )
        return self._handle_response(response)

    def _patch(self, endpoint: str, body: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        response = requests.patch(
            url, headers=self._headers(), json=body, timeout=30
        )
        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> dict:
        """Parse response or raise a detailed BloggerAPIError."""
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        if response.status_code in (200, 201):
            return data

        error_msg = data.get("error", {}).get("message", response.text)
        raise BloggerAPIError(response.status_code, error_msg)

    # ── Blog Info ─────────────────────────────────────────────────────────────

    def get_blog_info(self) -> dict:
        """Fetch basic metadata about the blog."""
        return self._get(f"/blogs/{self.blog_id}")

    # ── Posts ─────────────────────────────────────────────────────────────────

    def list_posts(
        self,
        max_results: int = 50,
        page_token: str = None,
        status: str = "live",
    ) -> dict:
        """
        List posts on the blog.
        status: 'live', 'draft', or 'scheduled'
        """
        params = {
            "maxResults": max_results,
            "status": status,
            "fetchBodies": "false",  # Don't fetch content — just metadata
            "fetchImages": "false",
        }
        if page_token:
            params["pageToken"] = page_token

        return self._get(f"/blogs/{self.blog_id}/posts", params=params)

    def get_all_post_titles(self) -> list[dict]:
        """
        Retrieve all published post titles and URLs for dedup checking.
        Paginates through all results automatically.
        """
        posts = []
        page_token = None

        while True:
            result = self.list_posts(max_results=500, page_token=page_token)
            items = result.get("items", [])
            for item in items:
                posts.append({
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "published": item.get("published", ""),
                    "labels": item.get("labels", []),
                })

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Fetched {len(posts)} existing post titles for dedup check.")
        return posts

    def get_post(self, post_id: str) -> dict:
        """Fetch a single post by ID."""
        return self._get(f"/blogs/{self.blog_id}/posts/{post_id}")

    def create_post(
        self,
        title: str,
        content_html: str,
        labels: list[str] = None,
        publish: bool = True,
        custom_meta_tags: str = "",
    ) -> dict:
        """
        Create and publish (or draft) a new blog post.

        Args:
            title: Post title (plain text)
            content_html: Full HTML body of the post
            labels: List of label strings (genre, topic, layer, keywords)
            publish: True to publish immediately, False to save as draft
            custom_meta_tags: Additional HTML meta tags to prepend

        Returns:
            Blogger API response dict containing post ID and URL
        """
        if labels is None:
            labels = []

        # Enforce Blogger's label limit
        if len(labels) > BloggerConfig.POST_LABEL_LIMIT:
            logger.warning(
                f"Label count {len(labels)} exceeds limit {BloggerConfig.POST_LABEL_LIMIT}. "
                "Truncating."
            )
            labels = labels[:BloggerConfig.POST_LABEL_LIMIT]

        # Prepend any meta tags inside a hidden div (Blogger ignores head tags)
        full_content = content_html
        if custom_meta_tags:
            full_content = (
                f'<div style="display:none;" class="post-meta-tags">'
                f'{custom_meta_tags}</div>\n{content_html}'
            )

        body = {
            "kind": "blogger#post",
            "title": title,
            "content": full_content,
            "labels": labels,
        }

        status_param = "live" if publish else "draft"
        endpoint = f"/blogs/{self.blog_id}/posts?isDraft={'false' if publish else 'true'}"

        result = self._post(endpoint, body)

        post_id = result.get("id", "unknown")
        post_url = result.get("url", "")
        logger.info(f"Post created: id={post_id} | url={post_url} | status={status_param}")

        return result

    def update_post(self, post_id: str, title: str = None, content_html: str = None, labels: list[str] = None) -> dict:
        """Partially update an existing post."""
        body = {}
        if title:
            body["title"] = title
        if content_html:
            body["content"] = content_html
        if labels is not None:
            body["labels"] = labels[:BloggerConfig.POST_LABEL_LIMIT]

        return self._patch(f"/blogs/{self.blog_id}/posts/{post_id}", body)

    # ── Pages ─────────────────────────────────────────────────────────────────

    def list_pages(self) -> dict:
        """List all static pages on the blog."""
        return self._get(f"/blogs/{self.blog_id}/pages")

    def create_page(self, title: str, content_html: str) -> dict:
        """Create a static page (for genre landing pages)."""
        body = {
            "kind": "blogger#page",
            "title": title,
            "content": content_html,
        }
        return self._post(f"/blogs/{self.blog_id}/pages", body)

    # ── Post Stats ────────────────────────────────────────────────────────────

    def get_post_stats(self, post_id: str) -> dict:
        """
        Retrieve page view stats for a specific post.
        Note: Blogger API provides basic view counts at the blog level.
        For per-post stats, we fall back to blog-level aggregates.
        """
        try:
            result = self._get(f"/blogs/{self.blog_id}/pageviews")
            return result
        except BloggerAPIError as e:
            logger.warning(f"Could not fetch stats for post {post_id}: {e}")
            return {}

    def get_blog_pageviews(self) -> dict:
        """
        Get total blog pageviews broken down by range.
        Returns counts for: ALL, 30DAYS, 7DAYS, today
        """
        try:
            return self._get(
                f"/blogs/{self.blog_id}/pageviews",
                params={"range": "all"}
            )
        except BloggerAPIError as e:
            logger.warning(f"Could not fetch blog pageviews: {e}")
            return {}

    # ── Utility ───────────────────────────────────────────────────────────────

    def build_labels(
        self,
        genre: str,
        topic: str,
        layer: str,
        keywords: list[str],
    ) -> list[str]:
        """
        Build a standardized Blogger label list from taxonomy fields.
        Format ensures consistent filtering across the blog.

        Example result: ["Technology", "AI", "Research Articles", "machine learning", "LLMs"]
        """
        # Normalize display names
        genre_label = genre.title()
        topic_label = topic.replace("_", " ").title()

        # Layer display name mapping
        layer_display_map = {
            "latest_news": "Latest News",
            "research_articles": "Research Articles",
            "how_to_guides": "How-To Guides",
            "opinion_analysis": "Opinion & Analysis",
            "case_studies": "Case Studies",
            "interviews": "Interviews",
            "listicles": "Listicles",
            "reviews": "Reviews",
            "explainers": "Explainers",
        }
        layer_label = layer_display_map.get(layer, layer.replace("_", " ").title())

        labels = [genre_label, topic_label, layer_label]

        # Add keyword tags (lowercase, deduped)
        for kw in keywords[:5]:  # Max 5 keyword tags
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean not in [l.lower() for l in labels]:
                labels.append(kw_clean)

        return labels

    def publish_post(
        self,
        title: str,
        content: str,
        labels: list[str] | None = None,
        publish: bool = True,
        custom_meta_tags: str = "",
    ) -> dict:
        """Publish a post (alias for create_post using HTML `content`)."""
        return self.create_post(
            title=title,
            content_html=content,
            labels=labels,
            publish=publish,
            custom_meta_tags=custom_meta_tags,
        )

# ── One-time OAuth Flow Helper ───────────────────────────────────────────────

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/blogger"]

def run_oauth_flow(client_secrets_file: str):

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets_file,
        scopes=SCOPES,
    )

    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )

    print("\nOpen this URL in your browser:\n")
    print(auth_url)

    code = input("\nPaste the authorization code here: ")

    flow.fetch_token(code=code)

    creds = flow.credentials

    print("\n=== BLOGGER OAUTH TOKENS ===\n")
    print(f"CLIENT_ID={creds.client_id}")
    print(f"CLIENT_SECRET={creds.client_secret}")
    print(f"REFRESH_TOKEN={creds.refresh_token}")
    print(f"TOKEN={creds.token}")
