"""
Voice Call Webhook Lambda Handler.

Handles Twilio voice call webhooks for conversational AI phone calls.
Uses AWS Bedrock (Amazon Nova Lite) for generating responses.
Conversation history stored in DynamoDB keyed by CallSid.

Flow:
  1. Twilio calls webhook when outbound call connects
  2. Lambda returns TwiML greeting + <Gather input="speech">
  3. User speaks -> Twilio POSTs transcription to same webhook
  4. Lambda calls Bedrock for AI response -> returns <Say> + <Gather>
  5. Loop continues until user hangs up or conversation ends
"""

import base64
import json
import os
import time
from decimal import Decimal
from urllib.parse import parse_qs

import boto3

VOICE_CALLS_TABLE = os.environ.get("VOICE_CALLS_TABLE", "BartVoiceCalls")
REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamo = boto3.resource("dynamodb", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SYSTEM_PROMPT = (
    "You are Bartimaeus, a helpful AI assistant on a phone call. "
    "Keep responses concise and conversational — 2-3 sentences max since this will be spoken aloud. "
    "Be natural, friendly, and helpful. Don't use markdown, bullet points, lists, or any formatting "
    "that doesn't work in speech. Don't use emojis or special characters. "
    "Speak naturally like a person would on a phone call. "
    "If the user seems to want to end the call, say a brief goodbye."
)

VOICE = "Polly.Matthew"
MODEL_ID = "amazon.nova-lite-v1:0"
GREETING = "Hey! This is Bartimaeus. What's up?"


def voiceWebhookHandler(event, context):
    """Main Lambda handler for Twilio voice webhooks."""
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="ignore")

    params = parse_qs(body, keep_blank_values=True) if body else {}

    call_sid = _param(params, "CallSid")
    speech_result = _param(params, "SpeechResult")

    # Build the webhook URL from the incoming request
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    host = headers.get("host") or ""
    proto = headers.get("x-forwarded-proto") or "https"
    webhook_url = f"{proto}://{host}"

    raw_path = event.get("rawPath") or "/"
    print(f"[{call_sid}] path={raw_path} speech={'yes' if speech_result else 'no'}")

    # Status callback — just log
    if raw_path.endswith("/status"):
        status = _param(params, "CallStatus")
        print(f"[{call_sid}] Call status: {status}")
        return _resp(200, "")

    # No speech result = initial call connection
    if not speech_result:
        # Store greeting in conversation history
        _init_conversation(call_sid, [])

        return _twiml(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{VOICE}">{_esc(GREETING)}</Say>
    <Gather input="speech" action="{webhook_url}/" speechTimeout="auto" language="en-US">
    </Gather>
    <Say voice="{VOICE}">I didn't catch anything. Let me know if you need anything. Goodbye!</Say>
</Response>""")

    # Speech received — process with AI
    print(f"[{call_sid}] User: {speech_result}")

    messages = _get_conversation(call_sid)
    messages.append({"role": "user", "content": [{"text": speech_result}]})

    ai_response = _call_bedrock(messages)
    print(f"[{call_sid}] AI: {ai_response}")

    messages.append({"role": "assistant", "content": [{"text": ai_response}]})
    _save_conversation(call_sid, messages)

    # Check if conversation should end
    goodbye_words = ["goodbye", "bye", "talk later", "see you", "take care", "have a good"]
    is_ending = any(w in ai_response.lower() for w in goodbye_words)

    if is_ending:
        return _twiml(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{VOICE}">{_esc(ai_response)}</Say>
    <Hangup/>
</Response>""")

    return _twiml(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{VOICE}">{_esc(ai_response)}</Say>
    <Gather input="speech" action="{webhook_url}/" speechTimeout="auto" language="en-US">
    </Gather>
    <Say voice="{VOICE}">I didn't catch that. Could you say that again?</Say>
    <Gather input="speech" action="{webhook_url}/" speechTimeout="auto" language="en-US">
    </Gather>
    <Say voice="{VOICE}">I'm having trouble hearing you. Goodbye!</Say>
</Response>""")


# -- Helpers ---------------------------------------------------------------


def _param(params, key):
    vals = params.get(key, [""])
    return vals[0] if vals else ""


def _esc(text):
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _twiml(body):
    return {"statusCode": 200, "headers": {"Content-Type": "text/xml"}, "body": body}


def _resp(code, body):
    return {"statusCode": code, "body": body}


# -- DynamoDB conversation storage -----------------------------------------


def _init_conversation(call_sid, messages):
    if not call_sid:
        return
    table = dynamo.Table(VOICE_CALLS_TABLE)
    table.put_item(
        Item={
            "call_sid": call_sid,
            "messages": json.dumps(messages),
            "created_at": Decimal(str(int(time.time()))),
            "ttl": Decimal(str(int(time.time()) + 86400)),
        }
    )


def _get_conversation(call_sid):
    if not call_sid:
        return []
    table = dynamo.Table(VOICE_CALLS_TABLE)
    try:
        resp = table.get_item(Key={"call_sid": call_sid})
        item = resp.get("Item")
        if item and "messages" in item:
            return json.loads(item["messages"])
    except Exception as e:
        print(f"Error reading conversation: {e}")
    return []


def _save_conversation(call_sid, messages):
    if not call_sid:
        return
    table = dynamo.Table(VOICE_CALLS_TABLE)
    try:
        table.update_item(
            Key={"call_sid": call_sid},
            UpdateExpression="SET messages = :m",
            ExpressionAttributeValues={":m": json.dumps(messages)},
        )
    except Exception as e:
        print(f"Error saving conversation: {e}")


# -- Bedrock AI ------------------------------------------------------------


def _call_bedrock(messages):
    try:
        body = json.dumps(
            {
                "system": [{"text": SYSTEM_PROMPT}],
                "messages": messages,
                "inferenceConfig": {"maxTokens": 250},
            }
        )
        resp = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(resp["body"].read())
        return result["output"]["message"]["content"][0]["text"]
    except Exception as e:
        print(f"Bedrock error: {e}")
        return "Sorry, I'm having a bit of trouble right now. Can you try again?"
