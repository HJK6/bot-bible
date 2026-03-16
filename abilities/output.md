# Web Output

Push rich markdown content to `bartimaeus.quest` for clean browser viewing. Two modes: **private** (auth-protected) and **public** (shareable).

## Private Output (auth-protected)

Push to `bartimaeus.quest/output` — requires Cognito login. Auto-refreshes every 5 seconds. Only one private output at a time (overwrites previous).

```python
import boto3, json, time
s3 = boto3.client('s3', region_name='us-east-1')
s3.put_object(
    Bucket='bartimaeus-chat-media',
    Key='output/current.json',
    Body=json.dumps({
        'title': 'Report Title',
        'content': '# Markdown content here\n\nSupports full markdown.',
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }),
    ContentType='application/json',
)
```

URL: `bartimaeus.quest/output`

## Public Output (shareable, no auth)

Push to `bartimaeus.quest/public/<id>` — no login required. Anyone with the link can view. Multiple public pages can coexist (each has its own ID/slug).

```python
import boto3, json, time
s3 = boto3.client('s3', region_name='us-east-1')
s3.put_object(
    Bucket='bartimaeus-chat-media',
    Key='public/my-page-slug.json',  # slug becomes the URL path
    Body=json.dumps({
        'title': 'Page Title',
        'content': '# Markdown content here\n\nSupports full markdown.',
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }),
    ContentType='application/json',
)
```

URL: `bartimaeus.quest/public/my-page-slug`

## JSON Format

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Page title displayed in header |
| `content` | string | Markdown content (full GFM support) |
| `updated_at` | string | ISO 8601 timestamp |

## Supported Markdown

- Headers (h1-h6)
- Tables (with styled borders and alternating rows)
- Code blocks (with syntax highlighting background)
- Inline code
- Blockquotes
- Lists (ordered and unordered)
- Links
- Images
- Horizontal rules
- Bold, italic, strikethrough

## Notes

- **Private** (`/output`): auto-refreshes every 5 seconds, requires Cognito auth, single page (overwritten)
- **Public** (`/public/<id>`): no auth, shareable links, multiple pages can coexist, manual refresh button
- S3 bucket: `bartimaeus-chat-media` — `output/` prefix for private, `public/` prefix for public
- Public prefix has an S3 bucket policy allowing anonymous `s3:GetObject`
- Content persists until overwritten — no expiry
- Web-only pages — redirect to home on mobile
