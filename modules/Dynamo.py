from modules.AWS import session
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from typing import Sequence
import sys
from decimal import Decimal
import decimal
from dataclasses import asdict


_dynamo = None


def get_dynamo():
    global _dynamo
    if _dynamo is None:
        _dynamo = session.resource("dynamodb")
    return _dynamo


def convert_floats_to_decimals(item):
    if isinstance(item, dict):
        return {k: convert_floats_to_decimals(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_floats_to_decimals(i) for i in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    else:
        return item


def replaceDecimals(obj):
    if isinstance(obj, list):
        return [replaceDecimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: replaceDecimals(v) for k, v in obj.items()}
    elif isinstance(obj, decimal.Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj


class Table(object):
    def __init__(self, table_name):
        self.table = get_dynamo().Table(table_name)
        self.table_name = table_name

    def get_all(self):
        response = self.table.scan()
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        return replaceDecimals(items)

    def filter(self, attribute, value, eq=True):
        if eq:
            result = self.table.scan(FilterExpression=Attr(attribute).eq(value))["Items"]
        else:
            result = self.table.scan(FilterExpression=Attr(attribute).ne(value))["Items"]
        return replaceDecimals(result)

    def write(self, data):
        if not isinstance(data, dict):
            data = asdict(data)
        data = convert_floats_to_decimals(data)
        self.table.put_item(Item=data)

    def get(self, key):
        try:
            response = self.table.get_item(Key=key)
        except Exception as e:
            print(e)
            return {}
        if "Item" in response:
            return replaceDecimals(response["Item"])
        else:
            return {}

    def delete(self, key):
        self.table.delete_item(Key=key)

    def updateItem(self, key, updateExpression, expressionAttributeValues, expressionAttributeNames=None):
        kwargs = {
            "Key": key,
            "UpdateExpression": updateExpression,
            "ExpressionAttributeValues": expressionAttributeValues,
        }
        if expressionAttributeNames:
            kwargs["ExpressionAttributeNames"] = expressionAttributeNames
        try:
            self.table.update_item(**kwargs)
        except Exception as e:
            print(e)

    def query_index(self, index_name, key_name, key_value):
        response = self.table.query(
            IndexName=index_name,
            KeyConditionExpression=Key(key_name).eq(key_value),
        )
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = self.table.query(
                IndexName=index_name,
                KeyConditionExpression=Key(key_name).eq(key_value),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        return replaceDecimals(items)

    def query_pk(self, key_name, key_value, scan_forward=False, limit=None):
        kwargs = {
            "KeyConditionExpression": Key(key_name).eq(key_value),
            "ScanIndexForward": scan_forward,
        }
        if limit:
            kwargs["Limit"] = limit
        response = self.table.query(**kwargs)
        return replaceDecimals(response.get("Items", []))

    def batch_delete_items(self, keys):
        for i in range(0, len(keys), 25):
            chunk = keys[i : i + 25]
            with self.table.batch_writer() as batch:
                for key in chunk:
                    batch.delete_item(Key=key)
