#!/usr/bin/env python3
"""Create DynamoDB tables for bot-to-bot communication. Run once."""

import boto3

REGION = "us-east-1"
dynamo = boto3.client("dynamodb", region_name=REGION)


def create_tables():
    existing = dynamo.list_tables()["TableNames"]

    tables = [
        {
            "TableName": "BotCommBots",
            "KeySchema": [{"AttributeName": "bot_id", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "bot_id", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": "BotCommSessions",
            "KeySchema": [
                {"AttributeName": "bot_id", "KeyType": "HASH"},
                {"AttributeName": "session_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "bot_id", "AttributeType": "S"},
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": "BotCommMessages",
            "KeySchema": [
                {"AttributeName": "session_id", "KeyType": "HASH"},
                {"AttributeName": "message_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "message_id", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    ]

    for table_def in tables:
        name = table_def["TableName"]
        if name in existing:
            print(f"  Table {name} already exists, skipping")
            continue
        try:
            dynamo.create_table(**table_def)
            print(f"  Created table: {name}")
        except Exception as e:
            print(f"  Failed to create {name}: {e}")

    # Wait for tables to become active
    for table_def in tables:
        name = table_def["TableName"]
        if name not in existing:
            waiter = dynamo.get_waiter("table_exists")
            print(f"  Waiting for {name} to become active...")
            waiter.wait(TableName=name)
            print(f"  {name} is active")


if __name__ == "__main__":
    print("Creating BotComm DynamoDB tables...")
    create_tables()
    print("Done!")
