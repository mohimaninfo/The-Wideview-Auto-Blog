"""
agents/publisher.py
Agent 9: Assembles the final HTML post and publishes via Blogger API v3.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

PUBLISHED_POSTS_PATH = Path("logs/published_posts.json")
BLOG_ID = os.environ.get("BLOGGER_BLOG_ID", "")


class PublisherAgent:
    def __init__(self):
        self.service = self._build_blogger_service()

    def _build_blogger_service(self):
        creds_json = os.environ.get("BLOGGER_OAUTH_CREDENTIALS_JSON")
        if not creds_json:
            raise ValueError("BLOGGER_OAUTH_CREDENTIALS_JSON environment variable is empty or missing!")
        
        try:
            creds_data = json.loads(creds_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse BLOGGER_OAUTH_CREDENTIALS_JSON as valid JSON: {e}")

        if "token_uri" not in creds_data:
            creds_data["token_uri"] = "https://oauth2.googleapis.com/token"

        creds = Credentials.from_authorized_user_info(creds_data, scopes=["https://www.googleapis.com/auth/blogger"])
        
        if not creds.refresh_token:
            raise ValueError("The provided JSON is missing the 'refresh_token' field!")

        if creds.expired:
            logger.info("Blogger credentials expired. Triggering automated refresh...")
            creds.refresh(GoogleRequest())
            
        return build("blogger", "v3", credentials=creds)

    def _assemble_html(self, task: dict) -> str:
        """Assemble the complete post HTML from all agent outputs."""
        post_html = task["post_with_citations"]["html_body"]
        seo_data = task["seo_data"]
        images = task["images"]
        video_data = task["video_data"]
        genre_label = task["genre_label"]
        topic_label = task["topic_label"]
        layer_label = task["layer_meta"]["label"]
        layer_color = task["layer_meta"]["color"]
        genre_color = task["genre_color"]
        author = seo_data["author"]
        read_time = seo_data["read_time_minutes"]
        pub_date_display = datetime.utcnow().strftime("%B %d, %Y")

        # Build featured image HTML
        featured_img_html = ""
        inline_img_html = ""
        for img in images:
            img_html = f"""<figure class="post-image">
  <img src="{img['url']}" alt="{img['alt']}" loading="lazy" width="800" height="450" />
  <figcaption>{img['caption']} {img['attribution']}</figcaption>
</figure>"""
            if img["position"] == "featured":
                featured_img_html = img_html
            else:
                inline_img_html += img_html

        # Build video HTML if needed
        video_html = ""
        if video_data.get("needed") and video_data.get("embed_html"):
            video_html = f"""<div class="video-section">
  <h3>Watch: {video_data.get('video_title', 'Related Video')}</h3>
  {video_data['embed_html']}
</div>"""

        # Article meta block
        meta_block = f"""<div class="article-meta">
  <span class="badge genre-badge" style="background:{genre_color}">{genre_label}</span>
  <span class="badge layer-badge" style="background:{layer_color}">{layer_label}</span>
  <span class="meta-author">By {author}</span>
  <span class="meta-date">{pub_date_display}</span>
  <span class="meta-readtime">⏱ {read_time} min read</span>
</div>"""

        # Share buttons
        canonical_url = seo_data["canonical_url"]
        title = task["post_draft"]["title"]
        share_buttons = self._build_share_buttons(canonical_url, title)

        # Disqus embed
        disqus_html = self._build_disqus_embed()

        # Like button (Firebase)
        like_html = self._build_like_button()

        full_html = f"""{meta_block}

{featured_img_html}

{post_html}

{inline_img_html}

{video_html}

{share_buttons}

{like_html}

{disqus_html}

{seo_data['schema_script']}"""

        return full_html

    def _build_share_buttons(self, url: str, title: str) -> str:
        encoded_url = requests.utils.quote(url, safe='')
        encoded_title = requests.utils.quote(title, safe='')
        return f"""<div class="share-section">
  <h3>Share This Article</h3>
  <div class="share-buttons">
    <a href="https://twitter.com/intent/tweet?url={encoded_url}&text={encoded_title}" target="_blank" rel="noopener" class="share-btn share-twitter" aria-label="Share on Twitter">𝕏 Twitter</a>
    <a href="https://www.facebook.com/sharer/sharer.php?u={encoded_url}" target="_blank" rel="noopener" class="share-btn share-facebook" aria-label="Share on Facebook">Facebook</a>
    <a href="https://www.linkedin.com/shareArticle?mini=true&url={encoded_url}&title={encoded_title}" target="_blank" rel="noopener" class="share-btn share-linkedin" aria-label="Share on LinkedIn">LinkedIn</a>
    <a href="https://wa.me/?text={encoded_title}%20{encoded_url}" target="_blank" rel="noopener" class="share-btn share-whatsapp" aria-label="Share on WhatsApp">WhatsApp</a>
    <a href="https://t.me/share/url?url={encoded_url}&text={encoded_title}" target="_blank" rel="noopener" class="share-btn share-telegram" aria-label="Share on Telegram">Telegram</a>
    <a href="https://reddit.com/submit?url={encoded_url}&title={encoded_title}" target="_blank" rel="noopener" class="share-btn share-reddit" aria-label="Share on Reddit">Reddit</a>
    <a href="mailto:?subject={encoded_title}&body=Check%20this%20out%3A%20{encoded_url}" class="share-btn share-email" aria-label="Share via Email">Email</a>
    <button onclick="navigator.clipboard.writeText('{url}');this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Link',2000)" class="share-btn share-copy" aria-label="Copy link">Copy Link</button>
  </div>
</div>"""

    def _build_like_button(self) -> str:
        return """<div class="reaction-section" id="post-reactions">
  <h3>Was this helpful?</h3>
  <div class="reaction-buttons">
    <button class="reaction-btn" data-reaction="like" onclick="handleReaction('like',this)">
      👍 Like <span class="reaction-count" id="count-like">0</span>
    </button>
    <button class="reaction-btn" data-reaction="insightful" onclick="handleReaction('insightful',this)">
      💡 Insightful <span class="reaction-count" id="count-insightful">0</span>
    </button>
    <button class="reaction-btn" data-reaction="helpful" onclick="handleReaction('helpful',this)">
      🙌 Helpful <span class="reaction-count" id="count-helpful">0</span>
    </button>
  </div>
</div>"""

    def _build_disqus_embed(self) -> str:
        disqus_shortname = os.environ.get("DISQUS_SHORTNAME", "yourblog")
        return f"""<div class="comments-section">
  <h2>Comments</h2>
  <div id="disqus_thread"></div>
  <script>
    var disqus_config = function () {{
      this.page.url = window.location.href;
      this.page.identifier = window.location.pathname;
    }};
    (function() {{
      var d = document, s = d.createElement('script');
      s.src = 'https://{disqus_shortname}.disqus.com/embed.js';
      s.setAttribute('data-timestamp', +new Date());
      (d.head || d.body).appendChild(s);
    }})();
  </script>
  <noscript>Please enable JavaScript to view the <a href="https://disqus.com/?ref_noscript">comments powered by Disqus.</a></noscript>
</div>"""

    def publish(self, task: dict) -> dict:
        """Publish the assembled post to Blogger."""
        html_content = self._assemble_html(task)
        seo_data = task["seo_data"]
        labels = seo_data["labels"]
        title = task["post_draft"]["title"]

        # Schedule publish time (stagger posts throughout the day)
        publish_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )

        post_body = {
            "title": title,
            "content": html_content,
            "labels": labels,
            "published": publish_time,
        }

        try:
            result = self.service.posts().insert(
                blogId=BLOG_ID,
                body=post_body,
                isDraft=False,
                fetchImages=False,
            ).execute()

            post_url = result.get("url", "")
            post_id = result.get("id", "")
            logger.info(f"Post published: {post_url}")

            metadata = {
                "post_id": post_id,
                "title": title,
                "url": post_url,
                "genre": task["genre_id"],
                "topic": task["topic_id"],
                "layer": task["layer"],
                "labels": labels,
                "slug": seo_data["slug"],
                "published_at": publish_time,
                "word_count": task["post_draft"].get("estimated_word_count", 0),
                "has_video": task["video_data"].get("needed", False),
                "image_count": len(task.get("images", [])),
                "reference_count": len(task["post_with_citations"].get("references", [])),
            }

            self._append_to_log(metadata)
            return metadata

        except Exception as e:
            logger.error(f"Blogger publish failed: {e}", exc_info=True)
            raise

    def _append_to_log(self, metadata: dict):
        PUBLISHED_POSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        posts = []
        
        if PUBLISHED_POSTS_PATH.exists():
            try:
                with open(PUBLISHED_POSTS_PATH) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        posts = data
                    elif isinstance(data, dict):
                        posts = [data] if data else []
            except json.JSONDecodeError:
                posts = []
                
        posts.append(metadata)
        
        with open(PUBLISHED_POSTS_PATH, "w") as f:
            json.dump(posts, f, indent=2)
