# X (Twitter)

Scrape tweets, user profiles, search results, and trends from X using **twikit**.

**Free**: No API key or subscription needed. Uses account session cookies (like browsing X in a browser).

**Account**: `@YOUR_X_HANDLE` (Google login)

## Setup (one-time)

X killed anonymous/guest access. Must log in once to capture session cookies.

Run this setup script — it opens Chrome, you log in via Google, and cookies are saved:

```bash
py /Users/YOUR_USERNAME/telegram-claude-bot/scripts/x_setup.py
```

This saves cookies to `~/.config/x/cookies.json`. Cookies last weeks/months — re-run if they expire.

## Quick Usage

```python
import asyncio
from twikit import Client

COOKIES_PATH = '/Users/YOUR_USERNAME/.config/x/cookies.json'

async def x_client() -> Client:
    """Get an authenticated X client."""
    client = Client('en-US')
    client.load_cookies(COOKIES_PATH)
    return client
```

## Common Operations

### Search Tweets

```python
async def search_tweets(query: str, count: int = 20):
    client = await x_client()
    # product: 'Latest' (chronological) or 'Top' (relevance)
    result = await client.search_tweet(query, product='Latest', count=count)
    tweets = list(result)
    for t in tweets:
        print(f"@{t.user.screen_name} ({t.favorite_count} likes): {t.text[:120]}")
    return tweets

asyncio.run(search_tweets('python programming'))
```

### Advanced Search Queries

```python
# X search operators (same as the web search bar)
queries = [
    'python from:elonmusk',          # tweets from a user
    'AI lang:en since:2025-01-01',    # language + date filter
    'bitcoin min_faves:1000',         # minimum likes
    '#machinelearning -filter:links', # hashtag without links
    'to:openai',                      # replies to a user
    '"exact phrase"',                 # exact match
    'python OR rust',                 # boolean OR
    'AI filter:media',               # only tweets with media
]
```

### Get User Profile

```python
async def get_user(username: str):
    client = await x_client()
    user = await client.get_user_by_screen_name(username)
    print(f"@{user.screen_name} | {user.name}")
    print(f"Followers: {user.followers_count} | Following: {user.following_count}")
    print(f"Tweets: {user.statuses_count}")
    print(f"Bio: {user.description}")
    return user

asyncio.run(get_user('elonmusk'))
```

### Get User Timeline

```python
async def get_timeline(username: str, count: int = 20):
    client = await x_client()
    user = await client.get_user_by_screen_name(username)
    result = await client.get_user_tweets(user.id, tweet_type='Tweets', count=count)
    tweets = list(result)
    for t in tweets:
        print(f"{t.created_at} | {t.favorite_count} likes | {t.text[:120]}")
    return tweets

asyncio.run(get_timeline('openai'))
```

### Get Trending Topics

```python
async def get_trends():
    client = await x_client()
    trends = await client.get_trends('trending')
    for t in trends:
        print(t.name, t.tweet_count if hasattr(t, 'tweet_count') else '')
    return trends

asyncio.run(get_trends())
```

### Get Tweet by ID

```python
async def get_tweet(tweet_id: str):
    client = await x_client()
    tweet = await client.get_tweet_by_id(tweet_id)
    print(f"@{tweet.user.screen_name}: {tweet.text}")
    print(f"Likes: {tweet.favorite_count} | RTs: {tweet.retweet_count}")
    return tweet

# Extract ID from URL: https://x.com/user/status/1234567890
asyncio.run(get_tweet('1234567890'))
```

### Get Replies to a Tweet

```python
async def get_replies(tweet_id: str, count: int = 20):
    client = await x_client()
    tweet = await client.get_tweet_by_id(tweet_id)
    result = await client.get_tweet_replies(tweet, count=count)
    for reply in result:
        print(f"@{reply.user.screen_name}: {reply.text[:100]}")
    return list(result)
```

### Pagination

```python
async def search_all(query: str, max_tweets: int = 100):
    """Paginate through search results."""
    client = await x_client()
    all_tweets = []
    result = await client.search_tweet(query, product='Latest', count=20)
    all_tweets.extend(result)

    while len(all_tweets) < max_tweets:
        # Get next page using cursor
        result = await result.next()
        if not result:
            break
        all_tweets.extend(result)

    return all_tweets[:max_tweets]
```

## Tweet Attributes

| Attribute | Description |
|-----------|-------------|
| `tweet.id` | Tweet ID |
| `tweet.text` | Full tweet text |
| `tweet.created_at` | Timestamp string |
| `tweet.user` | User object |
| `tweet.favorite_count` | Like count |
| `tweet.retweet_count` | Retweet count |
| `tweet.reply_count` | Reply count |
| `tweet.quote_count` | Quote tweet count |
| `tweet.view_count` | View count |
| `tweet.lang` | Language code |
| `tweet.media` | Attached media list |
| `tweet.urls` | URLs in tweet |
| `tweet.hashtags` | Hashtags list |
| `tweet.in_reply_to` | Parent tweet ID if reply |

## User Attributes

| Attribute | Description |
|-----------|-------------|
| `user.id` | User ID |
| `user.screen_name` | @handle |
| `user.name` | Display name |
| `user.description` | Bio |
| `user.followers_count` | Follower count |
| `user.following_count` | Following count |
| `user.statuses_count` | Tweet count |
| `user.verified` | Blue checkmark |
| `user.created_at` | Account creation date |
| `user.profile_image_url` | Avatar URL |
| `user.profile_banner_url` | Banner URL |

## Cookie Refresh

If you get auth errors (401/403), cookies have expired. Re-run setup:

```bash
py /Users/YOUR_USERNAME/telegram-claude-bot/scripts/x_setup.py
```

## Notes

- twikit is async — wrap calls in `asyncio.run()` for scripts
- Cookies typically last weeks to months before expiring
- Respect rate limits — don't hammer X or the account may get temporarily locked
- Search operators work the same as X's web search bar
- For posting tweets (not just reading), use `await client.create_tweet('text')`
