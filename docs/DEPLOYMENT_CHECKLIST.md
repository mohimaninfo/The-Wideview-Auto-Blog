# 🚀 Deployment Checklist — Autonomous Blogger
### Deliverable [M] — Zero-to-Live Setup (Ordered, Exact Commands)

Every step is mandatory. Complete them **in order**. Estimated total time: ~3 hours.

---

## PHASE 0 — Prerequisites

| Requirement | Notes |
|---|---|
| Google account | For Blogger + GCP + YouTube API |
| GitHub account | For repo + Actions |
| Python 3.11+ | Local dev & testing |
| `git` installed locally | For pushing code |

```bash
# Verify Python
python3 --version   # Must be 3.11+

# Verify git
git --version
```

---

## PHASE 1 — GitHub Repository

### 1.1 Create the repo
```bash
# On GitHub: New repo → Name: autonomous-blogger → Private → Create

# Clone locally
git clone https://github.com/YOUR_USERNAME/autonomous-blogger.git
cd autonomous-blogger

# Copy all project files into this directory, then:
pip install -r requirements.txt
```

### 1.2 Create a GitHub Personal Access Token
- GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained
- Scopes: **Contents (read/write)**, **Actions (read)**
- Copy the token — you'll add it as `GITHUB_TOKEN` secret later

---

## PHASE 2 — Google Cloud Project (GCP)

### 2.1 Create a GCP Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **New Project** → Name: `autonomous-blogger` → Create
3. Note your **Project ID**

### 2.2 Enable APIs
```
In GCP Console → APIs & Services → Enable APIs:
  ✅ Blogger API v3
  ✅ YouTube Data API v3
  ✅ Google Generative Language API (Gemini)
```

Or via CLI:
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable blogger.googleapis.com
gcloud services enable youtube.googleapis.com
gcloud services enable generativelanguage.googleapis.com
```

### 2.3 Get Gemini API Key
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API Key** → Select your project
3. Copy key → save as `GEMINI_API_KEY`

### 2.4 Get YouTube Data API Key
1. GCP Console → APIs & Services → Credentials
2. Create Credentials → **API Key**
3. Restrict to: YouTube Data API v3
4. Copy → save as `YOUTUBE_API_KEY`

---

## PHASE 3 — Blogger Setup

### 3.1 Create Your Blog
1. Go to [blogger.com](https://www.blogger.com)
2. Create New Blog → Choose any name/URL
3. Note your **Blog ID** (visible in Blogger dashboard URL: `blogger.com/blog/posts/BLOG_ID`)
4. Save as `BLOGGER_BLOG_ID`

### 3.2 OAuth2 Credentials for Blogger API
1. GCP Console → APIs & Services → Credentials
2. Create Credentials → **OAuth 2.0 Client ID**
3. Application type: **Desktop App** → Name: `blogger-bot`
4. Download JSON → save as `config/client_secrets.json` locally
5. **Do NOT commit this file** (it's in .gitignore)

### 3.3 Generate Refresh Token (one-time, local)
```bash
# Run the OAuth setup helper (included in utils/blogger_client.py)
python3 -c "
from utils.blogger_client import run_oauth_flow
run_oauth_flow('config/client_secrets.json')
"
# A browser window opens → sign in → allow access
# The script prints your REFRESH_TOKEN — copy it
```

### 3.4 Upload Blogger Template
1. Blogger Dashboard → Theme → Customize → Edit HTML
2. Paste the entire content of `templates/blogger_template.xml`
3. Click Save — your blog now has the custom mega-menu template

---

## PHASE 4 — Firebase Setup

### 4.1 Create Firebase Project
1. Go to [console.firebase.google.com](https://console.firebase.google.com)
2. Add Project → Use existing GCP project `autonomous-blogger`
3. Realtime Database → Create Database → **Start in test mode** (you'll add rules later)
4. Note Database URL: `https://autonomous-blogger-default-rtdb.firebaseio.com`
5. Save as `FIREBASE_DATABASE_URL`

### 4.2 Security Rules (copy-paste into Firebase Console → Realtime Database → Rules)
```json
{
  "rules": {
    "likes": {
      "$postId": {
        "count": {
          ".read": true,
          ".write": true
        },
        "users": {
          "$uid": {
            ".read": "auth != null && auth.uid === $uid",
            ".write": "auth != null && auth.uid === $uid"
          }
        }
      }
    }
  }
}
```

### 4.3 Service Account for GitHub Actions
1. Firebase Console → Project Settings → Service Accounts
2. Generate New Private Key → Download JSON
3. Copy entire JSON content → save as `FIREBASE_SERVICE_ACCOUNT_JSON` secret (see Phase 6)

---

## PHASE 5 — Disqus Setup

1. Go to [disqus.com](https://disqus.com) → Sign up free
2. Settings → Add Disqus to Site → Create new site
3. Category: News/Blog → Platform: **Universal Code**
4. Copy your **Shortname** (e.g., `my-blog-abc`) → save as `DISQUS_SHORTNAME`
5. The `blogger_template.xml` already includes the Disqus embed code —
   just replace `YOUR_DISQUS_SHORTNAME` in the template with your actual shortname

---

## PHASE 6 — GitHub Actions Secrets

Go to: GitHub Repo → Settings → Secrets and Variables → Actions → New Repository Secret

Add **all** of the following:

| Secret Name | Value |
|---|---|
| `GEMINI_API_KEY` | From Phase 2.3 |
| `BLOGGER_BLOG_ID` | From Phase 3.1 |
| `BLOGGER_REFRESH_TOKEN` | From Phase 3.3 |
| `BLOGGER_OAUTH_CREDENTIALS_JSON` | Full JSON content of `client_secrets.json` |
| `YOUTUBE_API_KEY` | From Phase 2.4 |
| `FIREBASE_DATABASE_URL` | From Phase 4.1 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full JSON content from Phase 4.3 |
| `GITHUB_TOKEN` | From Phase 1.2 (auto-provided by Actions, but set explicitly) |
| `DISQUS_SHORTNAME` | From Phase 5 |

---

## PHASE 7 — Configure Taxonomy & Settings

### 7.1 Review taxonomy.json
```bash
# Open taxonomy/taxonomy.json
# Verify genres, topics, and layer types match your desired content strategy
# The system will use this as its content roadmap — customize before first run
```

### 7.2 Set pipeline settings in .env (local) or as GitHub secrets
```bash
cp .env.example .env
# Edit .env with all values from Phases 2–5
```

---

## PHASE 8 — Test Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Dry-run the full pipeline (no publishing, no API writes)
DRY_RUN=true python3 -m agents.orchestrator --run-once

# Test individual agents
python3 -m agents.topic_discovery     # Should print a list of topic ideas
python3 -m agents.research --topic "artificial intelligence trends 2025"
python3 -m utils.link_validator https://en.wikipedia.org/wiki/Artificial_intelligence
python3 -m utils.quota_manager --status

# Run test suite
pytest tests/ -v
```

Expected output: `N passed, 0 failed` — fix any failures before deploying.

---

## PHASE 9 — Activate GitHub Actions

### 9.1 Push code to GitHub
```bash
git add .
git commit -m "Initial deployment: autonomous blogger pipeline"
git push origin main
```

### 9.2 Verify workflows
1. GitHub → Actions tab → you should see two workflows:
   - `Daily Content Pipeline` (runs at 06:00 UTC)
   - `Weekly & Monthly Self-Improvement` (runs Sundays 02:00 UTC)

### 9.3 Trigger a manual test run
1. Actions → `Daily Content Pipeline` → Run workflow → Run workflow
2. Watch the logs — each agent step should show green ✅
3. Check your Blogger dashboard — a new post should appear

---

## PHASE 10 — Post-Launch Verification

```bash
# Check published posts log
cat logs/published_posts.json | python3 -m json.tool

# Check quota usage
cat config/quota_state.json | python3 -m json.tool

# Verify Blogger post is live
# → Go to your .blogspot.com URL and confirm the post appears
# → Confirm Disqus comments section loads
# → Click Like button → confirm Firebase counter increments
# → Click Share → confirm share sheet appears
```

---

## PHASE 11 — SEO & Analytics (optional but recommended)

1. **Google Search Console** → Add property → Your blogspot URL → Verify via HTML tag method
2. **Google Analytics (GA4)** → Create property → Add tracking ID to `blogger_template.xml`
3. Submit sitemap: `https://your-blog.blogspot.com/feeds/posts/default?alt=rss`

---

## 🔴 Common Issues & Fixes

| Problem | Fix |
|---|---|
| `403 Forbidden` on Blogger API | Re-run OAuth flow, check scopes include `https://www.googleapis.com/auth/blogger` |
| `429 RESOURCE_EXHAUSTED` from Gemini | Quota manager auto-switches to fallback — check `quota_state.json` |
| Firebase write denied | Check security rules in Firebase Console → Realtime Database → Rules |
| GitHub Actions workflow not triggering | Check cron syntax; manual trigger via Actions tab to test |
| Posts publish but images 404 | Wikimedia/Unsplash URLs are dynamic — Image Agent validates before embedding |
| Duplicate post detected | `dedup_checker.py` compares against `logs/published_posts.json` — this is working correctly |

---

## ✅ Final Cost Confirmation

| Service | Plan | Cost |
|---|---|---|
| GitHub Actions | Free (2,000 min/month) | **$0** |
| Gemini 2.5 Flash | Free tier (1,500 RPD) | **$0** |
| Blogger | Free (Google hosting) | **$0** |
| Firebase Realtime DB | Spark plan (1GB) | **$0** |
| Disqus | Basic free tier | **$0** |
| YouTube Data API | Free (10,000 units/day) | **$0** |
| Wikimedia/Unsplash images | Free embed | **$0** |
| Pollinations.ai | Free | **$0** |
| **TOTAL** | | **$0.00/month** |

> ⚠️ **Hidden cost flags:** None identified. All services use documented free tiers.
> Monitor Firebase bandwidth (10GB/month free limit). At 3 posts/day the like counter
> should use well under 1GB of data per month.
