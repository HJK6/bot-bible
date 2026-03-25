import os
import json
import boto3

from handlers.apigw import apigw_adapter

MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "YOUR_BOT_NAME-chat-media")
REGION = os.environ.get("AWS_REGION", "us-east-1")
s3_client = boto3.client("s3", region_name=REGION)


@apigw_adapter
def getOutputHandler(event, context):
    """Read output/{slug}.json from S3 and return it."""
    body = event.get("body") or "{}"
    if isinstance(body, str):
        body = json.loads(body)
    slug = body.get("slug", "current")
    # Sanitise: only allow alphanumeric, hyphens, underscores
    slug = "".join(c for c in slug if c.isalnum() or c in "-_")
    if not slug:
        slug = "current"
    try:
        resp = s3_client.get_object(Bucket=MEDIA_BUCKET, Key=f"output/{slug}.json")
        data = json.loads(resp["Body"].read().decode("utf-8"))
        return data
    except s3_client.exceptions.NoSuchKey:
        return {"title": "", "content": "", "updated_at": ""}
