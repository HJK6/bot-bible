# Usage

Check Claude Code API usage — rate limit utilization, reset times, plan info.

## How It Works

Uses the OAuth token from macOS Keychain to make a minimal API call (`max_tokens=1`) to the Anthropic messages endpoint. The response headers contain real-time rate limit data.

## Quick Usage

```bash
py /Users/bartimaeus/telegram-claude-bot/abilities/check_usage.py
```

## Key Headers

| Header | Meaning |
|--------|---------|
| `anthropic-ratelimit-unified-5h-utilization` | % of 5-hour rolling window used (Opus) |
| `anthropic-ratelimit-unified-5h-reset` | Epoch timestamp when 5h window resets |
| `anthropic-ratelimit-unified-7d-utilization` | % of 7-day window used (Opus) |
| `anthropic-ratelimit-unified-7d-reset` | Epoch timestamp when 7d window resets |
| `anthropic-ratelimit-unified-7d_sonnet-utilization` | % of 7-day Sonnet window used |
| `anthropic-ratelimit-unified-7d_sonnet-reset` | Epoch timestamp when Sonnet 7d resets |
| `anthropic-ratelimit-unified-status` | `allowed` or `throttled` |
| `anthropic-ratelimit-unified-representative-claim` | Which limit is most constraining |

## Python

```python
import json, subprocess, requests
from datetime import datetime, timezone

def get_usage() -> dict:
    """Get current Claude Code rate limit usage."""
    # Get token from Keychain
    raw = subprocess.check_output([
        'security', 'find-generic-password',
        '-s', 'Claude Code-credentials', '-a', 'bartimaeus', '-w'
    ], text=True).strip()
    token = json.loads(raw)['claudeAiOauth']['accessToken']
    plan = json.loads(raw)['claudeAiOauth'].get('subscriptionType', 'unknown')
    tier = json.loads(raw)['claudeAiOauth'].get('rateLimitTier', 'unknown')

    # Minimal API call to get rate limit headers
    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': token,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 1,
            'messages': [{'role': 'user', 'content': 'hi'}],
        },
    )

    h = resp.headers
    now = datetime.now(timezone.utc)

    def parse_reset(key):
        val = h.get(key)
        if not val:
            return None
        reset_dt = datetime.fromtimestamp(int(val), tz=timezone.utc)
        delta = reset_dt - now
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return {'reset_epoch': int(val), 'reset_utc': reset_dt.isoformat(), 'time_left': f'{hours}h {minutes}m'}

    def pct(key):
        val = h.get(key)
        return f'{float(val) * 100:.1f}%' if val else None

    return {
        'plan': plan,
        'tier': tier,
        'status': h.get('anthropic-ratelimit-unified-status'),
        'most_constrained': h.get('anthropic-ratelimit-unified-representative-claim'),
        'opus_5h': {'used': pct('anthropic-ratelimit-unified-5h-utilization'), **parse_reset('anthropic-ratelimit-unified-5h-reset')},
        'opus_7d': {'used': pct('anthropic-ratelimit-unified-7d-utilization'), **parse_reset('anthropic-ratelimit-unified-7d-reset')},
        'sonnet_7d': {'used': pct('anthropic-ratelimit-unified-7d_sonnet-utilization'), **parse_reset('anthropic-ratelimit-unified-7d_sonnet-reset')},
        'overage_status': h.get('anthropic-ratelimit-unified-overage-status'),
    }

def format_usage(u: dict) -> str:
    lines = [
        f'Plan: {u["plan"]} ({u["tier"]})',
        f'Status: {u["status"]}',
        f'Most constrained: {u["most_constrained"]}',
        '',
        'Opus (5h window):',
        f'  Used: {u["opus_5h"]["used"]}  |  Resets in: {u["opus_5h"]["time_left"]}',
        '',
        'Opus (7d window):',
        f'  Used: {u["opus_7d"]["used"]}  |  Resets in: {u["opus_7d"]["time_left"]}',
        '',
        'Sonnet (7d window):',
        f'  Used: {u["sonnet_7d"]["used"]}  |  Resets in: {u["sonnet_7d"]["time_left"]}',
        '',
        f'Extra usage: {u["overage_status"]}',
    ]
    return '\n'.join(lines)
```

## Notes

- The API call uses Sonnet with `max_tokens=1` — costs essentially nothing
- Rate limit headers are returned on every API call, so this just piggybacks on a tiny request
- The 5h window is the primary constraint for Opus usage
- Sonnet has its own separate 7d limit that's much more generous
- `representative-claim` tells you which window is closest to being exhausted
