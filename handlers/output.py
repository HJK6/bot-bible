import os
import json
import boto3

from handlers.apigw import apigw_adapter

MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "YOUR_BOT_NAME-chat-media")
REGION = os.environ.get("AWS_REGION", "us-east-1")
s3_client = boto3.client("s3", region_name=REGION)


@apigw_adapter
def getOutputHandler(event, context):
    """Read output/current.json from S3 and return it."""
    try:
        resp = s3_client.get_object(Bucket=MEDIA_BUCKET, Key="output/current.json")
        data = json.loads(resp["Body"].read().decode("utf-8"))
        return data
    except s3_client.exceptions.NoSuchKey:
        return {"title": "", "content": "", "updated_at": ""}
