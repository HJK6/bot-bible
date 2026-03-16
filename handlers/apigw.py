import json
import functools
import logging

logger = logging.getLogger(__name__)


def apigw_adapter(handler_fn):
    """
    Decorator that makes a direct-invocation Lambda handler compatible with
    API Gateway proxy integration (AWS_PROXY).

    When called via API Gateway:
      - Parses event["body"] as JSON and passes it as the event to the handler
      - Wraps the handler's plain-dict return into API Gateway response format
      - Maps the handler's "code" field to the HTTP status code

    When called via direct invocation (no requestContext):
      - Passes through unchanged for full backward compatibility
    """

    @functools.wraps(handler_fn)
    def wrapper(event, context):
        is_apigw = "requestContext" in event

        if is_apigw:
            # Extract params from API Gateway event body
            body = event.get("body", "{}")
            if isinstance(body, str):
                try:
                    params = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    params = {}
            else:
                params = body or {}

            result = handler_fn(params, context)

            # If handler already returned an API Gateway response, pass through
            if isinstance(result, dict) and "statusCode" in result and "body" in result:
                return result

            # Determine HTTP status code
            status_code = 200
            if isinstance(result, dict):
                code = result.get("code")
                if isinstance(code, int):
                    status_code = code
                elif result.get("status") == "error":
                    status_code = 400

            return {
                "statusCode": status_code,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                    "Access-Control-Allow-Methods": "POST,OPTIONS",
                },
                "body": json.dumps(result, default=str),
            }
        else:
            return handler_fn(event, context)

    return wrapper
