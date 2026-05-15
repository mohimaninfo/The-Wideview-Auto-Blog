# [F] Blogger API Setup Guide
## OAuth2, API Key, Blog ID & Custom Template Configuration

---

## Overview

The Publisher Agent (Agent 9) uses the **Blogger API v3** to programmatically
create posts. Authentication is via **OAuth 2.0 with a Service Account** — no
browser interaction needed after initial setup, making it suitable for
fully automated GitHub Actions runs.

---

## Step 1 — Create a Google Cloud Project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click **"New Project"** → name it `autonomous-blogger` → **Create**
3. Note your **Project ID** (e.g. `autonomous-blogger-123456`)

---

## Step 2 — Enable the Blogger API

1. In your project, go to **APIs & Services → Library**
2. Search for **"Blogger API v3"**
3. Click it → **Enable**

---

## Step 3 — Create a Service Account

Service accounts allow server-to-server authentication without user login.

1. Go to **APIs & Services → Credentials**
2. Click **"+ Create Credentials" → Service Account**
3. Fill in:
   - **Name:** `blogger-automation`
   - **Role:** Leave blank (role is granted at the blog level, not GCP level)
4. Click **Done**

### Download the JSON key

1. Click your new service account → **Keys** tab → **Add Key → JSON**
2. A `.json` file downloads. **Keep this file secret.**
3. The file looks like:
   ```json
   {
     "type": "service_account",
     "project_id": "autonomous-blogger-123456",
     "private_key_id": "...",
     "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
     "client_email": "blogger-automation@autonomous-blogger-123456.iam.gserviceaccount.com",
     "client_id": "...",
     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
     "token_uri": "https://oauth2.googleapis.com/token"
   }
   ```
4. Note the `client_email` — you'll need it in Step 5.

---

## Step 4 — Get Your Blogger Blog ID

1. Open your Blogger dashboard: [https://www.blogger.com/](https://www.blogger.com/)
2. Select your blog → Click **Settings**
3. Scroll to **Blog ID** — copy the numeric ID (e.g. `1234567890123456789`)
4. Alternatively, from your blog's URL:
   ```
   https://www.blogger.com/blog/posts/1234567890123456789
   ```
   The number after `/posts/` is your Blog ID.

---

## Step 5 — Grant Service Account Access to Your Blog

Blogger's API v3 requires the service account's email to have **Author** or
**Admin** access on the blog.

1. Go to your Blogger dashboard → **Settings → Permissions**
2. Click **"Invite more authors"**
3. Enter the `client_email` from your service account JSON
   (e.g. `blogger-automation@autonomous-blogger-123456.iam.gserviceaccount.com`)
4. Set role to **Author** (sufficient for post creation)
5. Accept the invitation by logging in with the service account email
   — OR — use the Admin role and skip the invitation step.

> **Tip:** If you don't see the invitation acceptance option, use the
> [Blogger API Explorer](https://developers.google.com/blogger/docs/3.0/using)
> to test the service account directly.

---

## Step 6 — Store Credentials as GitHub Secrets

Never commit credentials to your repo. Store them as GitHub Actions secrets:

1. Go to your GitHub repo → **Settings → Secrets and variables → Actions**
2. Click **"New repository secret"** for each:

| Secret Name                     | Value                                              |
|---------------------------------|----------------------------------------------------|
| `BLOGGER_BLOG_ID`               | Numeric blog ID from Step 4                        |
| `GOOGLE_SERVICE_ACCOUNT_JSON`   | Full contents of the downloaded `.json` key file   |
| `GEMINI_API_KEY`                | Your Gemini API key (from Google AI Studio)        |
| `YOUTUBE_API_KEY`               | YouTube Data API v3 key (from Google Cloud)        |
| `FIREBASE_CREDENTIALS_JSON`     | Firebase service account JSON (see Firebase guide) |
| `FIREBASE_DATABASE_URL`         | `https://YOUR-PROJECT-rtdb.firebaseio.com`         |
| `DISQUS_SHORTNAME`              | Your Disqus site shortname                         |
| `GITHUB_TOKEN`                  | Auto-provided by Actions — no setup needed         |

### In your GitHub Actions workflow, load them like this:

```yaml
env:
  BLOGGER_BLOG_ID:             ${{ secrets.BLOGGER_BLOG_ID }}
  GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
  GEMINI_API_KEY:              ${{ secrets.GEMINI_API_KEY }}
  YOUTUBE_API_KEY:             ${{ secrets.YOUTUBE_API_KEY }}
  FIREBASE_CREDENTIALS_JSON:   ${{ secrets.FIREBASE_CREDENTIALS_JSON }}
  FIREBASE_DATABASE_URL:       ${{ secrets.FIREBASE_DATABASE_URL }}
  DISQUS_SHORTNAME:            ${{ secrets.DISQUS_SHORTNAME }}
```

### In Python (`config/settings.py`), load them:

```python
import os, json

BLOGGER_BLOG_ID           = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_SERVICE_ACCOUNT    = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
```

---

## Step 7 — Test the Blogger API Connection

Run this quick test script locally before deploying:

```python
# test_blogger_connection.py
import os, json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SERVICE_ACCOUNT = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
BLOG_ID         = os.environ["BLOGGER_BLOG_ID"]

creds = Credentials.from_service_account_info(
    SERVICE_ACCOUNT,
    scopes=["https://www.googleapis.com/auth/blogger"]
)
service = build("blogger", "v3", credentials=creds)

# List recent posts
posts = service.posts().list(blogId=BLOG_ID, maxResults=5).execute()
for p in posts.get("items", []):
    print(p["title"], p["url"])
```

Expected output — your last 5 blog post titles and URLs.

---

## Step 8 — Apply the Custom Blogger XML Template

The file `templates/blogger_template.xml` contains the full custom Blogger
theme. To apply it:

1. Go to **Blogger Dashboard → Theme**
2. Click the **dropdown arrow** next to "Customize" → **"Edit HTML"**
3. Delete ALL existing XML in the editor
4. Paste the entire contents of `blogger_template.xml`
5. Click **Save**

### What the template includes:
- **Mega menu** — Genre → Topic dropdown navigation
- **Breadcrumb system** — structured breadcrumbs per post
- **Post card design** — badges (Genre, Layer), read time, like/comment counts
- **Firebase like buttons** — per-post reaction bar wired to Firebase
- **Disqus comments** — auto-loaded on every post page
- **Share buttons** — 8 platform share links
- **Reference section** — styled citation list at post bottom
- **JSON-LD schema** — Article schema auto-populated from post metadata
- **Open Graph + Twitter Card** — rich link preview meta tags

### Configuring template variables

After pasting the template, find and replace these placeholders:

```xml
<!-- In blogger_template.xml, search for these and replace: -->
<b:skin>
  <!-- REPLACE: YOUR_FIREBASE_CONFIG_JSON -->
  <!-- REPLACE: YOUR_DISQUS_SHORTNAME -->
  <!-- REPLACE: YOUR_BLOG_TITLE -->
  <!-- REPLACE: YOUR_BLOG_URL -->
</b:skin>
```

Or use the automated setup:
```bash
python utils/template_configurator.py \
  --firebase-config '{"apiKey":"...","databaseURL":"..."}' \
  --disqus-shortname your-shortname \
  --blog-title "My AI Blog" \
  --blog-url "https://myblog.blogspot.com"
```

---

## Step 9 — Blogger API Rate Limits

| Limit             | Value               | Notes                           |
|-------------------|---------------------|---------------------------------|
| Posts per day     | 50                  | Per blog                        |
| API requests/day  | 10,000              | Per project (shared with other Google APIs) |
| Post size         | 500KB max           | Including HTML                  |

The pipeline publishes **3–5 posts/day** by default — well within limits.

---

## Step 10 — Verify Post Published Correctly

After first pipeline run:

1. Check `logs/published_posts.json` — should have an entry with `url`, `id`, `date`
2. Visit the post URL and confirm:
   - Breadcrumbs render correctly
   - Genre/Layer badges are visible
   - Firebase like buttons load and increment
   - Disqus comments section loads
   - Share buttons open correct URLs
   - Reference section appears at bottom

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `403 insufficientPermissions` | Service account not added as Author | Repeat Step 5 |
| `401 Unauthorized` | Expired/wrong credentials | Re-download service account JSON |
| `400 invalidValue` | Malformed post HTML | Check `post_html_template.html` for unclosed tags |
| Template not showing | Browser cache | Hard refresh (Ctrl+Shift+R) |
| Labels not applying | Label string too long | Max 200 chars per label, max 20 labels per post |
