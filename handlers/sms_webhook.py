"""
SMS Webhook Lambda Handler.

Receives inbound Twilio SMS via Function URL, validates the HMAC-SHA1
signature, and pushes the message to the OrchestratorInbox SQS queue.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qs, urlparse

import boto3

QUEUE_URL = os.environ.get("ORCHESTRATOR_QUEUE_URL", "")
TWILIO_AUTH_TOKEN_SSM = os.environ.get("TWILIO_AUTH_TOKEN_SSM", "/YOUR_BOT_NAME/creds/twilio-auth-token")
REGION = os.environ.get("AWS_REGION", "us-east-1")

sqs = boto3.client("sqs", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)

# Resolve auth token from SSM at cold start
_auth_token_cache = None


def _get_auth_token() -> str:
    global _auth_token_cache
    if _auth_token_cache is None:
        resp = ssm.get_parameter(Name=TWILIO_AUTH_TOKEN_SSM, WithDecryption=True)
        _auth_token_cache = resp["Parameter"]["Value"]
    return _auth_token_cache

TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


# -- Twilio signature validation -------------------------------------------


def _remove_port(uri):
    if not uri.port:
        return uri.geturl()
    new_netloc = uri.netloc.split(":")[0]
    return uri._replace(netloc=new_netloc).geturl()


def _add_port(uri):
    if uri.port:
        return uri.geturl()
    port = 443 if uri.scheme == "https" else 80
    return uri._replace(netloc=f"{uri.netloc}:{port}").geturl()


def _compute_signature(uri: str, params: dict, auth_token: bytes) -> str:
    s = uri
    if params:
        for name in sorted(params.keys()):
            for value in sorted(params[name]):
                s += name + str(value)
    digest = hmac.new(auth_token, s.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8").strip()


def _validate_twilio_request(event, auth_token: str) -> bool:
    headers_in = event.get("headers") or {}
    headers = {k.lower(): v for k, v in headers_in.items()}
    x_sig = headers.get("x-twilio-signature")
    if not x_sig:
        return False

    rc = event.get("requestContext") or {}
    proto = headers.get("x-forwarded-proto") or "https"
    host = headers.get("host") or rc.get("domainName") or ""
    path = event.get("rawPath") or (rc.get("http") or {}).get("path") or "/"
    if not path or path == "$default":
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    query = event.get("rawQueryString") or ""
    full_url = f"{proto}://{host}{path}" + (f"?{query}" if query else "")

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="ignore")

    params = parse_qs(body, keep_blank_values=True) if body else {}

    url_variants = {full_url}
    url_variants.add(full_url.rstrip("/") or full_url)
    if not full_url.endswith("/"):
        url_variants.add(full_url + "/")

    auth = auth_token.encode("utf-8")
    for base_url in url_variants:
        parsed = urlparse(base_url)
        for url_str in (_remove_port(parsed), _add_port(parsed)):
            sig = _compute_signature(url_str, params, auth)
            if hmac.compare_digest(sig, x_sig):
                print(f"Twilio signature valid (url={full_url})")
                return True

    print(f"Twilio signature INVALID url={full_url!r}")
    return False


# -- Handler ---------------------------------------------------------------


def smsWebhookHandler(event, context):
    """Handle incoming Twilio SMS webhook."""
    # Validate signature
    if not _validate_twilio_request(event, _get_auth_token()):
        return _twiml_response(403)

    # Parse form body
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="ignore")

    params = parse_qs(body, keep_blank_values=True) if body else {}

    from_number = (params.get("From") or [""])[0]
    to_number = (params.get("To") or [""])[0]
    text = (params.get("Body") or [""])[0]
    message_sid = (params.get("MessageSid") or [""])[0]

    if not text:
        return _twiml_response(200)

    # Push to SQS
    sqs_message = {
        "source": "sms",
        "from": from_number,
        "to": to_number,
        "text": text,
        "message_sid": message_sid,
        "timestamp": int(time.time()),
    }

    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(sqs_message),
            MessageAttributes={
                "source": {
                    "StringValue": "sms",
                    "DataType": "String",
                },
            },
        )
        print(f"SMS from {from_number}: {text[:80]} -> SQS")
    except Exception as e:
        print(f"Failed to send to SQS: {e}")
        return _twiml_response(500)

    return _twiml_response(200)


def _twiml_response(status_code):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/xml"},
        "body": TWIML_EMPTY,
    }
