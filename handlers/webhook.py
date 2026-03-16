"""
Telegram Webhook Lambda Handler.

Receives Telegram updates via Function URL, validates them,
and pushes messages to the OrchestratorInbox SQS queue.
"""
import json
import os
import boto3

QUEUE_URL = os.environ.get("ORCHESTRATOR_QUEUE_URL", "")
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "0"))
REGION = os.environ.get("AWS_REGION", "us-east-1")

sqs = boto3.client("sqs", region_name=REGION)


def telegramWebhookHandler(event, context):
    """Handle incoming Telegram webhook update.

    This is called directly via Lambda Function URL (not API Gateway),
    so we handle the raw event format ourselves.
    """
    # Parse the body
    body = event.get("body", "{}")
    if isinstance(body, str):
        try:
            update = json.loads(body)
        except json.JSONDecodeError:
            return _response(400, "Invalid JSON")
    else:
        update = body or {}

    # Extract message from the Telegram update
    message = update.get("message")
    if not message:
        # Could be an edited_message, callback_query, etc. — ignore for now
        return _response(200, "OK")

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    message_id = message.get("message_id")

    # Only accept messages from the owner
    if chat_id != OWNER_CHAT_ID:
        return _response(200, "OK")

    if not text:
        return _response(200, "OK")

    # Push to SQS
    sqs_message = {
        "source": "telegram",
        "chat_id": chat_id,
        "text": text,
        "message_id": message_id,
        "timestamp": message.get("date", 0),
    }

    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(sqs_message),
            MessageAttributes={
                "source": {
                    "StringValue": "telegram",
                    "DataType": "String",
                },
            },
        )
    except Exception as e:
        print(f"Failed to send to SQS: {e}")
        return _response(500, f"SQS error: {e}")

    return _response(200, "OK")


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": body}),
    }
