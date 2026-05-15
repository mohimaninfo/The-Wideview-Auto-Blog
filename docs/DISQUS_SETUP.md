# [I] Disqus Setup Guide
## Comment System + Login Integration for Blogger

---

## Overview

**Disqus** (free tier) provides:
- Threaded comment system with nested replies
- Upvote/downvote on comments
- Spam filtering (Akismet-powered)
- Social login (Google, Facebook, Twitter, Disqus accounts)
- Comment count display on post cards
- Email notifications to commenters
- Moderation dashboard

---

## Step 1 — Create a Disqus Account & Site

1. Go to [https://disqus.com/](https://disqus.com/) → **Get Started**
2. Select **"I want to install Disqus on my site"**
3. Fill in:
   - **Website Name:** `My AI Blog` (or your blog name)
   - **Shortname:** `my-ai-blog` (lowercase, hyphens only — **remember this**)
   - **Category:** News & Politics, Technology, etc.
4. Select the **Basic (Free)** plan → **Subscribe Now**
5. On the platform selection screen, choose **"Universal Code"**
   (we embed it manually in the Blogger template)

> Your **shortname** is used everywhere. Example: if your shortname is
> `my-ai-blog`, your Disqus URL is `https://my-ai-blog.disqus.com`.

---

## Step 2 — Configure Disqus Settings

Go to your [Disqus Admin Dashboard](https://disqus.com/admin/) → **Settings**:

### General
- **Website URL:** `https://yourblog.blogspot.com`
- **Description:** Short blog description
- **Language:** English (or your language)
- **Color scheme:** Match your blog theme (Light/Dark/Auto)

### Community
- **Guest commenting:** Enable (allows unregistered readers to comment)
- **Comment voting:** Enable (upvote/downvote)
- **Reactions:** Enable (emoji reactions per comment)

### Moderation
- **Spam filtering:** Enable (default on)
- **Pre-moderation:** Disable (auto-approve most comments for engagement)
- **Profanity filter:** Enable

---

## Step 3 — Embed Disqus in the Blogger Template

The `blogger_template.xml` already contains the Disqus embed. For reference,
here is the full embed code that lives inside each post page's HTML:

```html
<!-- Place this where you want the comment section to appear -->
<div id="disqus_thread"></div>

<script>
  /**
   * REQUIRED Disqus configuration variables.
   * These are injected by the Publisher Agent (Agent 9) at post creation time
   * via the post_html_template.html {{variable}} substitution.
   */
  var disqus_config = function () {
    // The canonical URL of the page (must be stable — never change after publishing)
    this.page.url = "{{POST_URL}}";

    // A unique identifier for this page (Blogger post ID works perfectly)
    this.page.identifier = "{{POST_ID}}";

    // Post title (used in notification emails to commenters)
    this.page.title = "{{POST_TITLE}}";
  };

  (function() {
    var d = document, s = d.createElement('script');
    s.src = 'https://{{DISQUS_SHORTNAME}}.disqus.com/embed.js';
    s.setAttribute('data-timestamp', +new Date());
    (d.head || d.body).appendChild(s);
  })();
</script>

<noscript>
  Please enable JavaScript to view the
  <a href="https://disqus.com/?ref_noscript" rel="nofollow">
    comments powered by Disqus.
  </a>
</noscript>
```

Replace `{{DISQUS_SHORTNAME}}` with your actual shortname, or let the
Publisher Agent inject it dynamically from the `DISQUS_SHORTNAME` environment
variable.

---

## Step 4 — Display Comment Count on Post Cards

Disqus provides a **comment count script** that automatically replaces
link text with the actual comment count. Add this to your listing pages
(genre landing page, homepage, label pages).

```html
<!-- Add once per page, before </body> -->
<script id="dsq-count-scr"
        src="//YOUR-SHORTNAME.disqus.com/count.js"
        async></script>
```

Then for each post card, use this link format:

```html
<a href="{{POST_URL}}#disqus_thread"
   data-disqus-identifier="{{POST_ID}}"
   class="ab-post-card__comment-count">
  <!-- Disqus replaces this text automatically -->
  0 Comments
</a>
```

Disqus's `count.js` scans all links with `#disqus_thread` and replaces
their text content with the actual comment count.

---

## Step 5 — Enable Disqus SSO (Optional — for unified login)

Disqus SSO allows your readers to log in once and have their identity
carried across all Disqus-powered sites. This is optional but enhances UX.

> Disqus SSO requires the **Plus plan** ($9/month) for custom SSO.
> For $0 cost, use Disqus's built-in social login (Google, Facebook, Twitter)
> which is available on the free plan. Skip this step to stay at $0.

For the free plan, Disqus automatically shows Google/Facebook/Twitter login
buttons in the comment embed — no configuration needed.

---

## Step 6 — Configure Allowed Domains

To prevent your Disqus comment thread from being embedded on other sites:

1. Go to **Disqus Admin → Settings → Advanced**
2. Under **Trusted Domains**, add: `yourblog.blogspot.com`
3. If you have a custom domain, add that too
4. Save settings

---

## Step 7 — Blogger Template Integration Points

In `blogger_template.xml`, the Disqus integration uses these Blogger data tags:

```xml
<!-- Used in the post page layout -->
<b:if cond='data:blog.pageType == &quot;item&quot;'>
  <!-- Only load Disqus on individual post pages, not listing pages -->
  <div id='disqus_thread'/>
  <script>
    var disqus_config = function() {
      this.page.url        = '<data:post.canonicalUrl/>';
      this.page.identifier = '<data:post.id/>';
      this.page.title      = '<data:post.title/>';
    };
    (function() {
      var d = document, s = d.createElement('script');
      s.src = 'https://YOUR-SHORTNAME.disqus.com/embed.js';
      s.setAttribute('data-timestamp', +new Date());
      (d.head || d.body).appendChild(s);
    })();
  </script>
</b:if>

<!-- Comment count on listing pages -->
<b:if cond='data:blog.pageType != &quot;item&quot;'>
  <script id='dsq-count-scr'
    src='//YOUR-SHORTNAME.disqus.com/count.js' async='async'/>
</b:if>
```

---

## Step 8 — Store Shortname in GitHub Secrets

```
Secret name:  DISQUS_SHORTNAME
Secret value: your-blog-shortname
```

The Publisher Agent injects this into each post automatically.

In Python (`config/settings.py`):
```python
import os
DISQUS_SHORTNAME = os.environ.get("DISQUS_SHORTNAME", "")
```

---

## Step 9 — Moderation & Spam Management

### Accessing your moderation queue:
1. Go to [https://disqus.com/admin/](https://disqus.com/admin/)
2. Navigate to **Moderate** → Pending queue
3. Approve, delete, or mark as spam

### Email alerts for new comments:
1. **Admin → Settings → Email** 
2. Enable **"Email me when someone comments"**
3. Enter your email address

### Auto-close old comments:
1. **Admin → Settings → Community**
2. Set **"Close posts after"** to `365 days` (prevents spam on old posts)

---

## Step 10 — Verify Disqus is Working

1. Open any published post on your blog
2. Scroll to the bottom — you should see the Disqus comment box
3. Try posting a test comment (you'll need to log in or comment as guest)
4. Verify the comment appears after refresh
5. Go to your Disqus admin dashboard → **Moderate** → confirm the comment
   shows up there too

### Comment count verification:
1. On a listing page (e.g. homepage or genre page)
2. View page source → confirm `count.js` is loaded
3. Hover over a "0 Comments" link → it should update after Disqus loads

---

## Free Plan Limitations

| Feature | Free Plan |
|---------|-----------|
| Comments | Unlimited |
| Comment voting | ✅ Included |
| Social login | ✅ Google, Facebook, Twitter |
| Spam filtering | ✅ Included |
| Comment count widget | ✅ Included |
| Ads in comment section | ⚠️ Disqus shows ads in free plan |
| Custom SSO | ❌ Requires Plus ($9/mo) |
| Remove Disqus branding | ❌ Requires Plus |
| Analytics | Basic only |

> **Note on ads:** Disqus shows small ads in the comment section on the
> free plan. This is the tradeoff for the $0 cost. Readers are generally
> accustomed to this. If ads are a concern, consider Blogger's native
> comment system as an alternative (see below).

---

## Alternative: Blogger Native Comments

If Disqus ads are unacceptable, use Blogger's built-in comment system:
- No third-party ads
- Fewer features (no voting, limited threading)
- Google account login required

To switch, in `blogger_template.xml`, replace the Disqus embed with:

```xml
<b:if cond='data:blog.pageType == &quot;item&quot;'>
  <b:include data='post' name='comment-form'/>
  <b:include data='post' name='threaded-comment-form'/>
</b:if>
```

Then in Blogger Dashboard → **Settings → Comments**:
- Comment location: **Embedded**
- Who can comment: **Anyone (including Anonymous)**
