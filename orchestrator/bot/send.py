#!/usr/bin/env python3
"""Standalone utility to send a message to a friend bot.

Usage:
    py send.py <bot_id> "message text" [--type chat]
    py send.py <bot_id> "message text" --type data_response --attachment /path/to/file.json
"""

import argparse
import asyncio
import json
import os
import sys

# Add project paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, "/Users/bartimaeus/land-bot")

from orchestrator.bot.handler import BotHandler
from orchestrator.bot.storage import BotCommStorage


async def main():
    parser = argparse.ArgumentParser(description="Send a message to a friend bot")
    parser.add_argument("bot_id", help="Bot ID to send to")
    parser.add_argument("message", help="Message text")
    parser.add_argument("--type", dest="message_type", default="chat",
                        choices=["chat", "data_request", "data_response",
                                 "capability_query", "capability_response"])
    parser.add_argument("--reply-to", default="", help="Message ID to reply to")
    parser.add_argument("--attachment", help="Local file to upload and attach")
    args = parser.parse_args()

    handler = BotHandler()
    attachments = []

    # Handle file attachment — upload to S3 and get presigned URL
    if args.attachment:
        filepath = os.path.expanduser(args.attachment)
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            sys.exit(1)

        filename = os.path.basename(filepath)
        content_type = "application/json" if filename.endswith(".json") else "application/octet-stream"

        # Upload to S3
        upload_info = handler.generate_upload_url(args.bot_id, filename, content_type)
        import urllib.request
        with open(filepath, "rb") as f:
            req = urllib.request.Request(
                upload_info["upload_url"],
                data=f.read(),
                headers={"Content-Type": content_type},
                method="PUT",
            )
            urllib.request.urlopen(req, timeout=30)

        # Generate download URL for the friend bot
        download_url = handler.generate_download_url(upload_info["key"])
        attachments.append({
            "url": download_url,
            "type": content_type,
            "name": filename,
            "size_bytes": os.path.getsize(filepath),
        })
        print(f"Uploaded: {filename} -> {upload_info['key']}")

    # Send the message
    success = await handler.send_message(
        bot_id=args.bot_id,
        message=args.message,
        message_type=args.message_type,
        reply_to=args.reply_to,
        attachments=attachments,
    )

    if success:
        print(f"Message sent to {args.bot_id}")
    else:
        print(f"Failed to send message to {args.bot_id}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
