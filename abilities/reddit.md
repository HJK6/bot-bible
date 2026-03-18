# Reddit

Scrape Reddit posts, comments, subreddits, and search results.

**Two methods available:**
1. **Public JSON API** (works now, no setup) — read-only, append `.json` to any Reddit URL
2. **PRAW** (requires API app approval) — full OAuth access, posting, voting, etc.

---

## Method 1: Public JSON API (No Auth Required)

Append `.json` to any Reddit URL. No API key, no OAuth, no setup. Rate limited to ~10 req/min without auth headers.

### Quick Usage

```python
import requests, time

HEADERS = {'User-Agent': 'YOUR_BOT_NAME/1.0'}
BASE = 'https://www.reddit.com'

def reddit_get(path, params=None):
    """Fetch Reddit JSON endpoint with rate limiting."""
    url = f"{BASE}{path}.json"
    r = requests.get(url, headers=HEADERS, params=params or {}, timeout=15)
    r.raise_for_status()
    time.sleep(1)  # respect rate limits
    return r.json()
```

### Search Posts

```python
# Search all of Reddit
data = reddit_get('/search', {'q': 'python asyncio', 'sort': 'relevance', 't': 'month', 'limit': 25})
for post in data['data']['children']:
    p = post['data']
    print(f"r/{p['subreddit']} | {p['score']}pts | {p['title']}")
    print(f"  https://reddit.com{p['permalink']}")

# Search within a subreddit
data = reddit_get('/r/programming/search', {'q': 'rust vs go', 'restrict_sr': 'on', 'limit': 10})
```

### Subreddit Posts

```python
# Hot posts
data = reddit_get('/r/python/hot', {'limit': 10})
for post in data['data']['children']:
    p = post['data']
    print(f"{p['score']}pts | {p['title']}")

# New, top, rising
data = reddit_get('/r/python/new', {'limit': 10})
data = reddit_get('/r/python/top', {'t': 'week', 'limit': 10})  # t: hour/day/week/month/year/all
data = reddit_get('/r/python/rising', {'limit': 10})
```

### Post Details + Comments

```python
# By permalink (from search results)
data = reddit_get('/r/python/comments/abc123/post_title')
post = data[0]['data']['children'][0]['data']
comments = data[1]['data']['children']

print(post['title'], post['score'], post['num_comments'])
print(post['selftext'][:500])

for c in comments:
    cd = c['data']
    if cd.get('body'):
        print(f"u/{cd.get('author','?')} ({cd.get('score',0)}pts): {cd['body'][:100]}")
```

### User Profile & Posts

```python
# User's posts
data = reddit_get('/user/spez/submitted', {'limit': 10})
for post in data['data']['children']:
    print(post['data']['title'])

# User's comments
data = reddit_get('/user/spez/comments', {'limit': 10})
for c in data['data']['children']:
    print(c['data']['body'][:100])

# User about
data = reddit_get('/user/spez/about')
print(data['data']['link_karma'], data['data']['comment_karma'])
```

### Subreddit Info

```python
data = reddit_get('/r/python/about')
sub = data['data']
print(sub['display_name'], sub['subscribers'], sub['public_description'])
```

### Multi-Subreddit Feed

```python
data = reddit_get('/r/python+programming+learnpython/hot', {'limit': 10})
for post in data['data']['children']:
    p = post['data']
    print(f"r/{p['subreddit']} | {p['title']}")
```

### Pagination

```python
# Use 'after' param with the last post's fullname for next page
data = reddit_get('/r/python/hot', {'limit': 25})
after = data['data']['after']  # e.g. "t3_abc123"

# Next page
data = reddit_get('/r/python/hot', {'limit': 25, 'after': after})
```

### JSON API Rate Limits

- No auth: ~10 req/min (Reddit returns 429 if exceeded)
- Always set a descriptive User-Agent
- Add `time.sleep(1)` between requests
- No write operations (can't post, comment, vote)

---

## Method 2: PRAW (Requires API App Approval)

Full OAuth access via PRAW (Python Reddit API Wrapper). **Requires Reddit API app approval** — Reddit removed self-service app creation in 2025. Must submit via [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164).

**Status**: Approval request pending. See todo list.

**Free tier**: 100 req/min, 10K/month (non-commercial).

### Setup (after approval)

1. Go to https://www.reddit.com/prefs/apps/
2. Click "create another app..."
3. Fill in: name=`YOUR_BOT_NAME`, type=`script`, redirect uri=`http://localhost:8080`
4. Store credentials:

```bash
py /Users/YOUR_USERNAME/telegram-claude-bot/modules/passwords.py set reddit_client_id "YOUR_CLIENT_ID"
py /Users/YOUR_USERNAME/telegram-claude-bot/modules/passwords.py set reddit_client_secret "YOUR_CLIENT_SECRET"
```

### Quick Usage

```python
import praw
import subprocess

def get_secret(key):
    r = subprocess.run(
        ['py', '/Users/YOUR_USERNAME/telegram-claude-bot/modules/passwords.py', 'get', key],
        capture_output=True, text=True
    )
    return r.stdout.strip()

reddit = praw.Reddit(
    client_id=get_secret('reddit_client_id'),
    client_secret=get_secret('reddit_client_secret'),
    user_agent='YOUR_BOT_NAME/1.0'
)
```

### Common Operations

```python
# Search
for post in reddit.subreddit('all').search('python asyncio', sort='relevance', time_filter='month', limit=20):
    print(f"r/{post.subreddit} | {post.score}pts | {post.title}")

# Subreddit posts
for post in reddit.subreddit('python').hot(limit=10):
    print(f"{post.score}pts | {post.title}")

# Post + comments
post = reddit.submission(id='abc123')
post.comments.replace_more(limit=0)
for comment in post.comments.list():
    print(f"u/{comment.author} ({comment.score}pts): {comment.body[:100]}")

# User
user = reddit.redditor('spez')
print(user.link_karma, user.comment_karma)
```

---

## Post Data Fields

| Field | Description |
|-------|-------------|
| `title` | Title |
| `selftext` | Body text (empty for link posts) |
| `url` | Link URL |
| `score` | Upvotes minus downvotes |
| `upvote_ratio` | Ratio of upvotes (0.0-1.0) |
| `num_comments` | Comment count |
| `created_utc` | Unix timestamp |
| `author` | Username string |
| `subreddit` | Subreddit name |
| `permalink` | Reddit-relative permalink |
| `is_self` | True if text post |
| `over_18` | True if NSFW |
| `stickied` | True if pinned |

## Comment Data Fields

| Field | Description |
|-------|-------------|
| `body` | Comment text |
| `score` | Score |
| `author` | Username |
| `created_utc` | Unix timestamp |
| `parent_id` | Parent comment/post ID |
| `is_submitter` | True if OP |

## Reddit Account

- Username: `YOUR_REDDIT_USERNAME`
- Email: `YOUR_REDDIT_EMAIL`
- Password: `YOUR_REDDIT_PASSWORD`
