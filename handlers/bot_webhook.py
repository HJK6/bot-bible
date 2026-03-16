"""
Bot-to-Bot Communication Webhook Lambda Handler.

Receives inbound messages from friend bots via Function URL,
validates the API key, and pushes the message to the OrchestratorInbox SQS queue.
Also handles upload_request (presigned S3 PUT URLs) and ping.
"""
import hashlib
import json
import os
import time
import uuid

import boto3

QUEUE_URL = os.environ.get("ORCHESTRATOR_QUEUE_URL", "")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "bartimaeus-chat-media")
REGION = os.environ.get("AWS_REGION", "us-east-1")

sqs = boto3.client("sqs", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

# Cache API key hashes from SSM (bot_id -> sha256 hash)
_key_cache = {}

VALID_MESSAGE_TYPES = {"chat", "data_request", "data_response", "capability_query", "capability_response", "ping", "upload_request", "register"}

dynamo = boto3.resource("dynamodb", region_name=REGION)
BOTS_TABLE = "BotCommBots"

# Cache bot records from DynamoDB (bot_id -> dict)
_bot_cache = {}


def _get_api_key_hash(bot_id: str) -> str:
    """Fetch the stored API key hash from SSM for a bot_id."""
    if bot_id in _key_cache:
        return _key_cache[bot_id]
    try:
        resp = ssm.get_parameter(
            Name=f"/bartimaeus/botcomm/keys/{bot_id}",
            WithDecryption=True,
        )
        _key_cache[bot_id] = resp["Parameter"]["Value"]
        return _key_cache[bot_id]
    except ssm.exceptions.ParameterNotFound:
        return ""
    except Exception as e:
        print(f"SSM error for bot {bot_id}: {e}")
        return ""


def _get_bot_record(bot_id: str) -> dict:
    """Fetch bot record from DynamoDB (cached)."""
    if bot_id in _bot_cache:
        return _bot_cache[bot_id]
    try:
        resp = dynamo.Table(BOTS_TABLE).get_item(Key={"bot_id": bot_id})
        item = resp.get("Item")
        if item:
            _bot_cache[bot_id] = item
            return item
    except Exception as e:
        print(f"DynamoDB error for bot {bot_id}: {e}")
    return {}


def _validate_api_key(bot_id: str, api_key: str) -> bool:
    """Validate API key by comparing SHA-256 hash against stored hash.
    Falls back to previous_api_key_hash if within grace period."""
    if not bot_id or not api_key:
        return False
    stored_hash = _get_api_key_hash(bot_id)
    if not stored_hash:
        return False
    provided_hash = hashlib.sha256(api_key.encode()).hexdigest()
    if provided_hash == stored_hash:
        return True
    # Check previous key during grace period
    bot_record = _get_bot_record(bot_id)
    previous_hash = bot_record.get("previous_api_key_hash", "")
    grace_until = int(bot_record.get("key_grace_until", 0))
    if previous_hash and grace_until > 0:
        now_ms = int(time.time() * 1000)
        if now_ms <= grace_until and provided_hash == previous_hash:
            print(f"Bot {bot_id} authenticated with previous key (grace period until {grace_until})")
            return True
    return False


def _ulid() -> str:
    return f"{int(time.time() * 1000):013d}_{uuid.uuid4().hex[:8]}"


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _handle_registration(payload: dict) -> dict:
    """Handle bot registration: validate token, challenge webhook, deliver key."""
    import secrets
    import urllib.request

    reg_token = payload.get("registration_token", "").strip()
    bot_id = payload.get("bot_id", "").strip()
    name = payload.get("name", "").strip()
    webhook_url = payload.get("webhook_url", "").strip()
    capabilities = payload.get("capabilities", [])

    if not all([reg_token, bot_id, name, webhook_url]):
        return _json_response(400, {"error": "Missing required fields: registration_token, bot_id, name, webhook_url"})

    # Validate bot_id format (lowercase alphanumeric + hyphens)
    if not all(c.isalnum() or c == "-" for c in bot_id) or not bot_id[0].isalnum():
        return _json_response(400, {"error": "bot_id must be lowercase alphanumeric with hyphens"})

    # Check bot_id not already registered
    existing = _get_api_key_hash(bot_id)
    if existing:
        return _json_response(409, {"error": f"bot_id '{bot_id}' is already registered"})

    # Validate registration token from SSM
    ssm_path = f"/bartimaeus/botcomm/reg/{reg_token}"
    try:
        resp = ssm.get_parameter(Name=ssm_path, WithDecryption=True)
        token_data = json.loads(resp["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        return _json_response(403, {"error": "Invalid or expired registration token"})
    except Exception as e:
        print(f"SSM error validating registration token: {e}")
        return _json_response(500, {"error": "Internal error validating token"})

    # Check expiry
    if token_data.get("expires_at", 0) < int(time.time()):
        # Clean up expired token
        try:
            ssm.delete_parameter(Name=ssm_path)
        except Exception:
            pass
        return _json_response(403, {"error": "Registration token has expired"})

    # Webhook challenge — POST nonce, expect it back
    nonce = secrets.token_hex(32)
    challenge_payload = json.dumps({
        "type": "registration_challenge",
        "challenge": nonce,
    }).encode()
    try:
        req = urllib.request.Request(
            webhook_url,
            data=challenge_payload,
            headers={"Content-Type": "application/json"},
        )
        challenge_resp = urllib.request.urlopen(req, timeout=10)
        challenge_body = json.loads(challenge_resp.read().decode())
        if challenge_body.get("challenge_response") != nonce:
            return _json_response(403, {"error": "Webhook challenge failed — incorrect nonce response"})
    except urllib.error.URLError as e:
        return _json_response(400, {"error": f"Cannot reach webhook URL: {e}"})
    except (json.JSONDecodeError, KeyError):
        return _json_response(403, {"error": "Webhook challenge failed — invalid response format"})
    except Exception as e:
        print(f"Challenge error: {e}")
        return _json_response(400, {"error": f"Webhook challenge failed: {e}"})

    # Generate API key and HMAC secret
    api_key = f"bk_live_{secrets.token_hex(32)}"
    hmac_secret = secrets.token_hex(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    now_ms = int(time.time() * 1000)
    scopes = token_data.get("scopes", ["chat"])

    # Store API key hash in SSM
    try:
        ssm.put_parameter(
            Name=f"/bartimaeus/botcomm/keys/{bot_id}",
            Value=api_key_hash,
            Type="SecureString",
            Overwrite=True,
        )
    except Exception as e:
        print(f"Failed to store API key in SSM: {e}")
        return _json_response(500, {"error": "Internal error storing credentials"})

    # Store HMAC secret in SSM
    try:
        ssm.put_parameter(
            Name=f"/bartimaeus/botcomm/hmac/{bot_id}",
            Value=hmac_secret,
            Type="SecureString",
            Overwrite=True,
        )
    except Exception as e:
        print(f"Failed to store HMAC secret in SSM: {e}")
        return _json_response(500, {"error": "Internal error storing credentials"})

    # Create bot record in DynamoDB
    from decimal import Decimal
    bot_item = {
        "bot_id": bot_id,
        "name": name,
        "webhook_url": webhook_url,
        "api_key_hash": api_key_hash,
        "capabilities": capabilities,
        "scopes": scopes,
        "status": "active",
        "previous_api_key_hash": "",
        "key_rotated_at": Decimal(str(now_ms)),
        "key_grace_until": Decimal("0"),
        "created_at": Decimal(str(now_ms)),
        "updated_at": Decimal(str(now_ms)),
    }
    try:
        dynamo.Table(BOTS_TABLE).put_item(Item=bot_item)
    except Exception as e:
        print(f"Failed to create bot in DynamoDB: {e}")
        return _json_response(500, {"error": "Internal error creating bot record"})

    # Deliver API key + HMAC secret to friend's webhook
    delivery_payload = json.dumps({
        "type": "registration_complete",
        "bot_id": bot_id,
        "api_key": api_key,
        "hmac_secret": hmac_secret,
        "bartimaeus_webhook_url": "",  # Filled by the friend from the invite instructions
    }).encode()
    try:
        req = urllib.request.Request(
            webhook_url,
            data=delivery_payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Warning: could not deliver credentials to webhook (bot registered anyway): {e}")

    # Delete registration token from SSM
    try:
        ssm.delete_parameter(Name=ssm_path)
    except Exception as e:
        print(f"Warning: could not delete registration token: {e}")

    print(f"Bot registered: {bot_id} ({name}), scopes={scopes}")
    return _json_response(200, {
        "status": "ok",
        "bot_id": bot_id,
        "message": f"Registration complete. API key and HMAC secret delivered to your webhook.",
    })


def botWebhookHandler(event, context):
    """Handle incoming bot-to-bot messages via Function URL."""
    # Parse body
    body_raw = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64
        body_raw = base64.b64decode(body_raw).decode("utf-8", errors="ignore")

    try:
        payload = json.loads(body_raw) if body_raw else {}
    except json.JSONDecodeError:
        return _json_response(400, {"error": "Invalid JSON"})

    bot_id = payload.get("bot_id", "").strip()
    api_key = payload.get("api_key", "").strip()
    message_type = payload.get("message_type", "chat").strip()
    message = payload.get("message", "").strip()
    reply_to = payload.get("reply_to", "")
    attachments = payload.get("attachments", [])

    # Handle registration before auth — register requests don't have an API key
    if message_type == "register":
        return _handle_registration(payload)

    # Validate required fields
    if not bot_id:
        return _json_response(400, {"error": "Missing bot_id"})
    if not api_key:
        return _json_response(401, {"error": "Missing api_key"})

    # Validate API key
    if not _validate_api_key(bot_id, api_key):
        print(f"Auth failed for bot_id={bot_id}")
        return _json_response(403, {"error": "Invalid API key"})

    # Validate message_type
    if message_type not in VALID_MESSAGE_TYPES:
        return _json_response(400, {"error": f"Invalid message_type. Must be one of: {', '.join(sorted(VALID_MESSAGE_TYPES))}"})

    timestamp = int(time.time() * 1000)
    message_id = _ulid()

    # Handle ping — no SQS needed
    if message_type == "ping":
        print(f"Ping from {bot_id}")
        return _json_response(200, {
            "status": "ok",
            "bot": "bartimaeus",
            "message_id": message_id,
            "timestamp": timestamp,
        })

    # Handle upload_request — generate presigned PUT URL
    if message_type == "upload_request":
        filename = payload.get("filename", f"{uuid.uuid4().hex[:8]}.json")
        content_type = payload.get("content_type", "application/json")
        key = f"bot-data/{bot_id}/{int(time.time())}_{filename}"

        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": MEDIA_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=300,  # 5 minutes
        )
        object_url = f"https://{MEDIA_BUCKET}.s3.{REGION}.amazonaws.com/{key}"

        print(f"Upload URL generated for {bot_id}: {key}")
        return _json_response(200, {
            "status": "ok",
            "upload_url": upload_url,
            "object_url": object_url,
            "key": key,
            "message_id": message_id,
            "timestamp": timestamp,
        })

    # Normal message — validate content
    if not message and not attachments:
        return _json_response(400, {"error": "Message or attachments required"})

    # Push to OrchestratorInbox SQS
    sqs_message = {
        "source": "bot",
        "bot_id": bot_id,
        "message_type": message_type,
        "message": message,
        "reply_to": reply_to,
        "attachments": attachments,
        "message_id": message_id,
        "timestamp": timestamp,
    }

    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(sqs_message),
            MessageAttributes={
                "source": {
                    "StringValue": "bot",
                    "DataType": "String",
                },
                "bot_id": {
                    "StringValue": bot_id,
                    "DataType": "String",
                },
            },
        )
        print(f"Bot message from {bot_id} ({message_type}): {message[:80]} -> SQS")
    except Exception as e:
        print(f"Failed to send to SQS: {e}")
        return _json_response(500, {"error": "Internal error"})

    return _json_response(200, {
        "status": "ok",
        "message_id": message_id,
        "timestamp": timestamp,
    })
