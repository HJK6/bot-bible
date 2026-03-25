from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Attr
from modules.Dynamo import Table, replaceDecimals
from modules.Config import BSE_STOCKS_TABLE, VOLUME_SHOCKS_TABLE, TRADES_TABLE
from handlers.apigw import apigw_adapter


@apigw_adapter
def getStocksHandler(event, context):
    """Get all scored BSE stocks with trust_score >= 80, sorted descending."""
    table = Table(BSE_STOCKS_TABLE)

    # Push filter to DynamoDB — only transfer matching items
    filter_expr = Attr("trust_score_status").eq("scored") & Attr("trust_score").gte(75)

    items = []
    response = table.table.scan(FilterExpression=filter_expr)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.table.scan(
            FilterExpression=filter_expr,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    scored = replaceDecimals(items)
    scored.sort(key=lambda s: s.get("trust_score", 0), reverse=True)
    return scored


@apigw_adapter
def getVolumeShocksHandler(event, context):
    """Get volume shocks for a date (defaults to today IST).
    Optional body: {"trade_date": "YYYY-MM-DD"}"""
    IST = timezone(timedelta(hours=5, minutes=30))
    trade_date = event.get("trade_date") or datetime.now(IST).strftime("%Y-%m-%d")

    table = Table(VOLUME_SHOCKS_TABLE)
    items = table.query_pk("trade_date", trade_date)
    items.sort(key=lambda x: x.get("peak_shock_ratio", x.get("shock_ratio", 0)), reverse=True)
    return items


@apigw_adapter
def getTradesHandler(event, context):
    """Get trades from a start date onward (defaults to 2026-03-10).
    Optional body: {"from_date": "YYYY-MM-DD"}"""
    from_date = event.get("from_date") or "2026-03-10"

    table = Table(TRADES_TABLE)
    items = []
    response = table.table.scan()
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    # Filter to trades on or after from_date
    items = [i for i in items if i.get("buy_date", "") >= from_date]
    items = replaceDecimals(items)
    items.sort(key=lambda x: x.get("buy_date", ""), reverse=True)
    return items
