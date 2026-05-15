# [H] Firebase Setup Guide
## Like Counter — Free Spark Plan, JS SDK & Blogger Template Integration

---

## Overview

Post reactions (Like ❤️, Insightful 💡, Helpful 👍) are stored in
**Firebase Realtime Database** (free Spark plan). The Blogger template
loads the Firebase JS SDK and reads/writes reaction counts client-side.
The Python pipeline uses the Firebase Admin SDK to initialize the database
structure when a new post is published.

**Free Spark plan limits (as of 2025):**
- 1 GB stored data
- 10 GB/month download bandwidth
- 100 simultaneous connections

At ~100 bytes per post reaction record, 1 GB supports **~10 million posts** —
more than enough.

---

## Step 1 — Create a Firebase Project

1. Go to [https://console.firebase.google.com/](https://console.firebase.google.com/)
2. Click **"Add project"**
3. Name it: `autonomous-blogger` → Continue
4. Disable Google Analytics (not needed) → **Create project**
5. Click **Continue** when ready

---

## Step 2 — Enable Realtime Database

1. In your Firebase project, go to **Build → Realtime Database**
2. Click **"Create Database"**
3. Choose your database location (pick closest region)
4. Start in **"Test mode"** for initial setup (we'll secure it in Step 5)
5. Click **Enable**
6. Note your **Database URL**:
   ```
   https://autonomous-blogger-default-rtdb.REGION.firebasedatabase.app
   ```

---

## Step 3 — Get Firebase Web Config (for Blogger JS SDK)

1. Go to **Project Settings** (gear icon) → **General** tab
2. Scroll to **"Your apps"** → Click **"</>"** (Web) icon
3. Register app with nickname `blogger-frontend`
4. Copy the `firebaseConfig` object:

```javascript
const firebaseConfig = {
  apiKey:            "AIzaSy...",
  authDomain:        "autonomous-blogger.firebaseapp.com",
  databaseURL:       "https://autonomous-blogger-default-rtdb.firebasedatabase.app",
  projectId:         "autonomous-blogger",
  storageBucket:     "autonomous-blogger.appspot.com",
  messagingSenderId: "123456789",
  appId:             "1:123456789:web:abcdef"
};
```

---

## Step 4 — Get Firebase Admin SDK Credentials (for Python agent)

1. Go to **Project Settings → Service Accounts**
2. Click **"Generate new private key"** → **Generate Key**
3. A JSON file downloads. **Keep this secret.**
4. Store the full JSON contents as the GitHub secret `FIREBASE_CREDENTIALS_JSON`
5. Store the database URL as `FIREBASE_DATABASE_URL`

---

## Step 5 — Secure the Database Rules

Replace the default open rules with these production rules.

Go to **Realtime Database → Rules** and paste:

```json
{
  "rules": {
    "reactions": {
      "$postId": {
        ".read": true,
        "counts": {
          ".read": true,
          "like": {
            ".write": true,
            ".validate": "newData.isNumber() && newData.val() >= 0"
          },
          "insightful": {
            ".write": true,
            ".validate": "newData.isNumber() && newData.val() >= 0"
          },
          "helpful": {
            ".write": true,
            ".validate": "newData.isNumber() && newData.val() >= 0"
          }
        },
        "voters": {
          "$userId": {
            ".read": "auth != null && auth.uid === $userId",
            ".write": "auth != null && auth.uid === $userId",
            ".validate": "newData.hasChildren(['like','insightful','helpful'])"
          }
        }
      }
    }
  }
}
```

**Rule explanation:**
- `counts` are publicly readable (for displaying counts to all users)
- `counts` are publicly writable (anonymous voting — simpler UX)
- `voters` track who voted to prevent duplicate votes (requires auth)
- Numeric validation prevents count manipulation via direct writes

> **Anonymous voting note:** For simplicity, vote counts are publicly
> writable. Duplicate vote prevention is handled client-side via
> `localStorage`. For stricter enforcement, enable Firebase Anonymous
> Auth and use the `$userId` voter path.

---

## Step 6 — Database Structure

The pipeline auto-creates this structure when publishing a post:

```json
{
  "reactions": {
    "POST_BLOGGER_ID": {
      "counts": {
        "like": 0,
        "insightful": 0,
        "helpful": 0
      }
    }
  }
}
```

Python initialization code (runs in Publisher Agent):

```python
# utils/firebase_client.py
import firebase_admin
from firebase_admin import credentials, db

def initialize_post_reactions(post_id: str):
    ref = db.reference(f"reactions/{post_id}/counts")
    if ref.get() is None:
        ref.set({"like": 0, "insightful": 0, "helpful": 0})
```

---

## Step 7 — Blogger Template Integration

Add this JavaScript to your `blogger_template.xml` inside the `<head>` section
(or just before `</body>`). Replace `YOUR_FIREBASE_CONFIG` with the config from Step 3.

```html
<!-- Firebase SDK (modular, from CDN — free) -->
<script type="module">
  import { initializeApp }        from 'https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js';
  import { getDatabase, ref, get, set, increment, runTransaction }
    from 'https://www.gstatic.com/firebasejs/10.12.0/firebase-database.js';

  const firebaseConfig = {
    apiKey:      "YOUR_API_KEY",
    databaseURL: "https://YOUR-PROJECT-rtdb.firebasedatabase.app",
    projectId:   "YOUR_PROJECT_ID",
    appId:       "YOUR_APP_ID"
  };

  const app = initializeApp(firebaseConfig);
  const database = getDatabase(app);

  // ── initPostReactions ──────────────────────────────────────────
  // Called from each post's inline script (see post_html_template.html)
  window.initPostReactions = function(postId) {
    if (!postId) return;

    const countsRef = ref(database, `reactions/${postId}/counts`);
    const voted     = JSON.parse(localStorage.getItem(`voted_${postId}`) || '{}');

    // Load current counts
    get(countsRef).then(snapshot => {
      const counts = snapshot.val() || { like: 0, insightful: 0, helpful: 0 };
      document.getElementById('count-like').textContent        = counts.like        || 0;
      document.getElementById('count-insightful').textContent  = counts.insightful  || 0;
      document.getElementById('count-helpful').textContent     = counts.helpful     || 0;

      // Mark already-voted buttons
      ['like','insightful','helpful'].forEach(type => {
        if (voted[type]) {
          const btn = document.getElementById(`ab-${type}-btn`);
          if (btn) btn.classList.add('ab-reaction-btn--voted');
        }
      });
    });

    // Wire up click handlers
    ['like', 'insightful', 'helpful'].forEach(type => {
      const btn = document.getElementById(`ab-${type}-btn`);
      if (!btn) return;

      btn.addEventListener('click', () => {
        if (voted[type]) return; // Prevent duplicate vote

        // Optimistic UI update
        const countEl = document.getElementById(`count-${type}`);
        countEl.textContent = parseInt(countEl.textContent || '0') + 1;
        btn.classList.add('ab-reaction-btn--voted');
        btn.classList.add('ab-reaction-btn--pulse');
        setTimeout(() => btn.classList.remove('ab-reaction-btn--pulse'), 600);

        // Persist vote to localStorage
        voted[type] = true;
        localStorage.setItem(`voted_${postId}`, JSON.stringify(voted));

        // Write to Firebase with atomic increment
        const typeRef = ref(database, `reactions/${postId}/counts/${type}`);
        runTransaction(typeRef, current => (current || 0) + 1)
          .catch(err => {
            console.error('Firebase reaction write failed:', err);
            // Rollback UI on failure
            countEl.textContent = parseInt(countEl.textContent) - 1;
            btn.classList.remove('ab-reaction-btn--voted');
            delete voted[type];
            localStorage.setItem(`voted_${postId}`, JSON.stringify(voted));
          });
      });
    });
  };
</script>

<style>
  .ab-reaction-btn { /* Base styles already in blogger_template.xml */ }
  .ab-reaction-btn--voted  { opacity: 0.6; cursor: default; }
  .ab-reaction-btn--pulse  { animation: ab-pulse 0.4s ease; }
  @keyframes ab-pulse {
    0%   { transform: scale(1); }
    50%  { transform: scale(1.25); }
    100% { transform: scale(1); }
  }
</style>
```

---

## Step 8 — Display Reaction Counts on Post Cards (Listing Pages)

On listing pages (genre/topic landing pages), show the total reaction count.

Add to listing page JavaScript:

```javascript
// Load reaction counts for all visible post cards
async function loadPostCardReactions() {
  const cards = document.querySelectorAll('[data-post-id]');
  for (const card of cards) {
    const postId = card.getAttribute('data-post-id');
    if (!postId) continue;
    const countsRef = ref(database, `reactions/${postId}/counts`);
    const snapshot  = await get(countsRef);
    const counts    = snapshot.val() || { like: 0, insightful: 0, helpful: 0 };
    const total     = (counts.like || 0) + (counts.insightful || 0) + (counts.helpful || 0);
    const countEl   = card.querySelector('.ab-post-card__like-count');
    if (countEl) countEl.textContent = total;
  }
}
document.addEventListener('DOMContentLoaded', loadPostCardReactions);
```

---

## Step 9 — Python Admin SDK Setup

```bash
pip install firebase-admin
```

```python
# utils/firebase_client.py  (excerpt)
import json, os
import firebase_admin
from firebase_admin import credentials, db

_initialized = False

def get_firebase_db():
    global _initialized
    if not _initialized:
        cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"])
        db_url    = os.environ["FIREBASE_DATABASE_URL"]
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred, {"databaseURL": db_url})
        _initialized = True
    return db
```

---

## Step 10 — Verify Firebase is Working

Run this from your local machine after setting environment variables:

```bash
export FIREBASE_CREDENTIALS_JSON="$(cat path/to/serviceAccount.json)"
export FIREBASE_DATABASE_URL="https://your-project-rtdb.firebasedatabase.app"

python -c "
from utils.firebase_client import FirebaseClient
fc = FirebaseClient()
fc.initialize_post_reactions('test_post_001')
counts = fc.get_reactions('test_post_001')
print('Counts:', counts)  # Should print: Counts: {'like': 0, 'insightful': 0, 'helpful': 0}
"
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `PERMISSION_DENIED` | Database rules too restrictive | Check Step 5 rules |
| `Firebase: No Firebase App` | SDK not initialized before use | Ensure `initializeApp()` called once |
| Counts not loading on blog | Wrong `databaseURL` in JS config | Verify URL matches Step 2 |
| Duplicate votes possible | localStorage cleared | Expected for private/incognito windows |
| `quota-exceeded` | Free plan bandwidth limit | Monitor in Firebase console; 10 GB/month is generous |
