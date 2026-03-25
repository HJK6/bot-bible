#!/usr/bin/env python3
"""BotComm registration and key management CLI.

Usage:
    py register_bot.py invite --name "Aria Bot" --scopes chat,data
    py register_bot.py list
    py register_bot.py rotate-key <bot_id>
    py register_bot.py suspend <bot_id>
    py register_bot.py activate <bot_id>
    py register_bot.py revoke <bot_id>
"""

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, "/Users/YOUR_USERNAME/land-bot")

import boto3

REGION = "us-east-1"
ssm = boto3.client("ssm", region_name=REGION)
dynamo = boto3.resource("dynamodb", region_name=REGION)
BOTS_TABLE = dynamo.Table("BotCommBots")

GRACE_PERIOD_MS = 48 * 60 * 60 * 1000  # 48 hours


def cmd_invite(args):
    """Generate a registration invite token."""
    name = args.name
    scopes = [s.strip() for s in args.scopes.split(",")]
    expires_at = int(time.time()) + 86400  # 24h

    token = f"reg_{secrets.token_hex(32)}"
    token_data = {
        "name": name,
        "scopes": scopes,
        "expires_at": expires_at,
        "created_at": int(time.time()),
    }

    ssm.put_parameter(
        Name=f"/bartimaeus/botcomm/reg/{token}",
        Value=json.dumps(token_data),
        Type="SecureString",
        Overwrite=True,
    )

    expires_str = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  Registration invite created for: {name}")
    print(f"  Scopes: {', '.join(scopes)}")
    print(f"  Expires: {expires_str} (24h)")
    print(f"\n  Token: {token}")
    print(f"\n  --- Share the following with your friend ---\n")
    print(f"  1. Set up your bot's webhook (HTTPS endpoint)")
    print(f"     Your webhook must handle these POSTs:")
    print(f"     - registration_challenge: return {{'challenge_response': '<nonce>'}}")
    print(f"     - registration_complete: contains your api_key and hmac_secret")
    print(f"     - key_rotation: contains your new_api_key (switch within 48h)")
    print(f"")
    print(f"  2. POST to Bartimaeus's webhook:")
    print(f"     {{")
    print(f'       "message_type": "register",')
    print(f'       "registration_token": "{token}",')
    print(f'       "bot_id": "your-bot-id",')
    print(f'       "name": "{name}",')
    print(f'       "webhook_url": "https://your-webhook-url",')
    print(f'       "capabilities": ["weather", "search"]')
    print(f"     }}")
    print(f"")
    print(f"  3. Bartimaeus will challenge your webhook, then deliver")
    print(f"     your API key + HMAC secret directly to your endpoint.")
    print()


def cmd_list(args):
    """List all registered bots."""
    resp = BOTS_TABLE.scan()
    bots = resp.get("Items", [])

    if not bots:
        print("No bots registered.")
        return

    print(f"\n{'Bot ID':<20} {'Name':<20} {'Status':<10} {'Scopes':<20} {'Key Rotated':<20}")
    print("-" * 90)
    for b in sorted(bots, key=lambda x: x.get("bot_id", "")):
        bot_id = b.get("bot_id", "")
        name = b.get("name", "")
        status = b.get("status", "")
        scopes = ", ".join(b.get("scopes", []))
        rotated = int(b.get("key_rotated_at", 0))
        rotated_str = datetime.fromtimestamp(rotated / 1000).strftime("%Y-%m-%d %H:%M") if rotated else "never"
        print(f"{bot_id:<20} {name:<20} {status:<10} {scopes:<20} {rotated_str:<20}")
    print()


def cmd_rotate_key(args):
    """Rotate a bot's API key."""
    bot_id = args.bot_id

    # Get current bot record
    resp = BOTS_TABLE.get_item(Key={"bot_id": bot_id})
    bot = resp.get("Item")
    if not bot:
        print(f"Bot '{bot_id}' not found.")
        sys.exit(1)

    if bot.get("status") != "active":
        print(f"Bot '{bot_id}' is {bot.get('status')} — cannot rotate key.")
        sys.exit(1)

    webhook_url = bot.get("webhook_url", "")
    current_hash = bot.get("api_key_hash", "")
    now_ms = int(time.time() * 1000)

    # Generate new key
    new_api_key = f"bk_live_{secrets.token_hex(32)}"
    new_hash = hashlib.sha256(new_api_key.encode()).hexdigest()

    # Update DynamoDB: move current → previous, set grace period
    from decimal import Decimal
    BOTS_TABLE.update_item(
        Key={"bot_id": bot_id},
        UpdateExpression=(
            "SET api_key_hash = :new_hash, "
            "previous_api_key_hash = :old_hash, "
            "key_rotated_at = :now, "
            "key_grace_until = :grace, "
            "updated_at = :now"
        ),
        ExpressionAttributeValues={
            ":new_hash": new_hash,
            ":old_hash": current_hash,
            ":now": Decimal(str(now_ms)),
            ":grace": Decimal(str(now_ms + GRACE_PERIOD_MS)),
        },
    )

    # Update SSM
    ssm.put_parameter(
        Name=f"/bartimaeus/botcomm/keys/{bot_id}",
        Value=new_hash,
        Type="SecureString",
        Overwrite=True,
    )

    # Deliver new key to friend's webhook
    delivery_payload = json.dumps({
        "type": "key_rotation",
        "bot_id": bot_id,
        "new_api_key": new_api_key,
        "grace_period_hours": 48,
        "message": "Your API key has been rotated. Switch to the new key within 48 hours.",
    }).encode()

    delivered = False
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                webhook_url,
                data=delivery_payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            delivered = True
            break
        except Exception as e:
            print(f"  Delivery attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)

    if delivered:
        print(f"\n  Key rotated for '{bot_id}'.")
        print(f"  New key delivered to webhook.")
        print(f"  Previous key valid for 48 more hours.")
    else:
        print(f"\n  Key rotated for '{bot_id}' but FAILED to deliver to webhook.")
        print(f"  Previous key remains valid for 48h grace period.")
        print(f"  You may need to share the new key manually.")
        print(f"  New API key: {new_api_key}")
    print()


def cmd_suspend(args):
    """Suspend a bot."""
    bot_id = args.bot_id
    from decimal import Decimal
    try:
        BOTS_TABLE.update_item(
            Key={"bot_id": bot_id},
            UpdateExpression="SET #st = :s, updated_at = :now",
            ExpressionAttributeValues={
                ":s": "suspended",
                ":now": Decimal(str(int(time.time() * 1000))),
            },
            ExpressionAttributeNames={"#st": "status"},
            ConditionExpression="attribute_exists(bot_id)",
        )
        print(f"Bot '{bot_id}' suspended.")
    except dynamo.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"Bot '{bot_id}' not found.")
        sys.exit(1)


def cmd_activate(args):
    """Reactivate a suspended bot."""
    bot_id = args.bot_id
    from decimal import Decimal
    try:
        BOTS_TABLE.update_item(
            Key={"bot_id": bot_id},
            UpdateExpression="SET #st = :s, updated_at = :now",
            ExpressionAttributeValues={
                ":s": "active",
                ":now": Decimal(str(int(time.time() * 1000))),
            },
            ExpressionAttributeNames={"#st": "status"},
            ConditionExpression="attribute_exists(bot_id)",
        )
        print(f"Bot '{bot_id}' activated.")
    except dynamo.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"Bot '{bot_id}' not found.")
        sys.exit(1)


def cmd_revoke(args):
    """Revoke a bot's API key and suspend it."""
    bot_id = args.bot_id
    from decimal import Decimal

    # Delete key from SSM
    try:
        ssm.delete_parameter(Name=f"/bartimaeus/botcomm/keys/{bot_id}")
    except ssm.exceptions.ParameterNotFound:
        pass

    # Update DynamoDB
    try:
        BOTS_TABLE.update_item(
            Key={"bot_id": bot_id},
            UpdateExpression=(
                "SET #st = :s, api_key_hash = :empty, "
                "previous_api_key_hash = :empty, "
                "key_grace_until = :zero, updated_at = :now"
            ),
            ExpressionAttributeValues={
                ":s": "suspended",
                ":empty": "",
                ":zero": Decimal("0"),
                ":now": Decimal(str(int(time.time() * 1000))),
            },
            ExpressionAttributeNames={"#st": "status"},
            ConditionExpression="attribute_exists(bot_id)",
        )
        print(f"Bot '{bot_id}' revoked — API key deleted, bot suspended.")
    except dynamo.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"Bot '{bot_id}' not found.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="BotComm registration and key management")
    sub = parser.add_subparsers(dest="command", required=True)

    # invite
    p_invite = sub.add_parser("invite", help="Generate a registration invite")
    p_invite.add_argument("--name", required=True, help="Display name for the bot")
    p_invite.add_argument("--scopes", default="chat", help="Comma-separated scopes (default: chat)")

    # list
    sub.add_parser("list", help="List all registered bots")

    # rotate-key
    p_rotate = sub.add_parser("rotate-key", help="Rotate a bot's API key")
    p_rotate.add_argument("bot_id", help="Bot ID to rotate")

    # suspend
    p_suspend = sub.add_parser("suspend", help="Suspend a bot")
    p_suspend.add_argument("bot_id", help="Bot ID to suspend")

    # activate
    p_activate = sub.add_parser("activate", help="Reactivate a suspended bot")
    p_activate.add_argument("bot_id", help="Bot ID to activate")

    # revoke
    p_revoke = sub.add_parser("revoke", help="Revoke API key and suspend bot")
    p_revoke.add_argument("bot_id", help="Bot ID to revoke")

    args = parser.parse_args()

    commands = {
        "invite": cmd_invite,
        "list": cmd_list,
        "rotate-key": cmd_rotate_key,
        "suspend": cmd_suspend,
        "activate": cmd_activate,
        "revoke": cmd_revoke,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
