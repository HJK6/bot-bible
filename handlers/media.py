import os
import uuid
import time
import boto3
from handlers.apigw import apigw_adapter

MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "bartimaeus-chat-media")
REGION = os.environ.get("AWS_REGION", "us-east-1")
s3_client = boto3.client("s3", region_name=REGION)


@apigw_adapter
def getUploadUrlHandler(event, context):
    """Generate a presigned PUT URL for uploading an image to S3."""
    agent_id = event.get("agent_id", "general")
    content_type = event.get("content_type", "image/jpeg")
    file_ext = event.get("file_ext", "jpg")

    timestamp = int(time.time() * 1000)
    unique_id = uuid.uuid4().hex[:8]
    key = f"chat-media/{agent_id}/{timestamp}_{unique_id}.{file_ext}"

    upload_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": MEDIA_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=300,  # 5 minutes
    )

    object_url = f"https://{MEDIA_BUCKET}.s3.{REGION}.amazonaws.com/{key}"

    return {
        "upload_url": upload_url,
        "object_url": object_url,
        "key": key,
    }
