"""
Gmail Webhook Lambda Handler.

Receives Google Cloud Pub/Sub push notifications when Gmail has new messages.
Validates the OIDC JWT token from Google, then forwards the notification
to the OrchestratorInbox SQS queue.

Flow: Gmail Watch → Pub/Sub → this Lambda → SQS → Orchestrator
"""
import base64
import json
import os
import time

import boto3
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

QUEUE_URL = os.environ.get("ORCHESTRATOR_QUEUE_URL", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")
# The Lambda Function URL — used as the expected audience in the OIDC token
EXPECTED_AUDIENCE = os.environ.get("GMAIL_WEBHOOK_AUDIENCE", "")

sqs = boto3.client("sqs", region_name=REGION)

# Cache the HTTP transport for token verification
_google_request = None


def _get_google_request():
    global _google_request
    if _google_request is None:
        _google_request = google_requests.Request()
    return _google_request


def gmailWebhookHandler(event, context):
    """Handle incoming Pub/Sub push notification for Gmail changes."""
    # --- 1. Verify OIDC JWT ---
    headers = event.get("headers") or {}
    headers_lower = {k.lower(): v for k, v in headers.items()}
    auth_header = headers_lower.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        print("Missing or malformed Authorization header")
        return _response(401, "Unauthorized")

    token = auth_header[7:]  # strip "Bearer "

    try:
        claim = id_token.verify_oauth2_token(
            token,
            _get_google_request(),
            audience=EXPECTED_AUDIENCE if EXPECTED_AUDIENCE else None,
        )
        # Verify the issuer is Google
        issuer = claim.get("iss", "")
        if issuer not in ("accounts.google.com", "https://accounts.google.com"):
            print(f"Invalid issuer: {issuer}")
            return _response(403, "Forbidden")

        print(f"OIDC verified: sub={claim.get('sub')} email={claim.get('email')}")
    except Exception as e:
        print(f"OIDC verification failed: {e}")
        return _response(403, "Forbidden")

    # --- 2. Parse Pub/Sub message ---
    body = event.get("body", "{}")
    if isinstance(body, str):
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8", errors="ignore")
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return _response(400, "Invalid JSON")

    pubsub_message = body.get("message", {})
    if not pubsub_message:
        return _response(400, "No Pub/Sub message")

    # Pub/Sub data is base64-encoded JSON: {"emailAddress": "...", "historyId": ...}
    data_b64 = pubsub_message.get("data", "")
    try:
        notification = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except Exception:
        notification = {}

    email_address = notification.get("emailAddress", "unknown")
    history_id = notification.get("historyId", 0)

    print(f"Gmail notification: email={email_address} historyId={history_id}")

    # --- 3. Forward to SQS ---
    sqs_message = {
        "source": "gmail",
        "email": email_address,
        "history_id": history_id,
        "timestamp": int(time.time()),
    }

    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(sqs_message),
            MessageAttributes={
                "source": {
                    "StringValue": "gmail",
                    "DataType": "String",
                },
            },
        )
        print(f"Gmail notification forwarded to SQS: historyId={history_id}")
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
