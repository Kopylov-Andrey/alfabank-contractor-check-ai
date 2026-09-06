import json
import os
import re
import unicodedata

import boto3


BUCKET = "contractor-reports"
KEY = "reports_by_inn.json"
MAX_RESULTS = 20

s3 = boto3.client(
    "s3",
    endpoint_url="https://storage.yandexcloud.net",
    region_name="ru-central1",
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)

_DB_CACHE = None


def normalize_search_text(value):
    """Normalize punctuation and spacing without changing token order."""
    text = unicodedata.normalize("NFKC", str(value)).lower().replace("ё", "е")
    return " ".join(re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).split())


def get_db():
    global _DB_CACHE
    if _DB_CACHE is None:
        obj = s3.get_object(Bucket=BUCKET, Key=KEY)
        _DB_CACHE = json.loads(obj["Body"].read().decode("utf-8"))
    return _DB_CACHE


def extract_params(event):
    """Accept MCP top-level args and the existing HTTP event.body format."""
    if not isinstance(event, dict):
        return {}

    params = dict(event)
    body = event.get("body")
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            body = None
    if isinstance(body, dict):
        params.update(body)
    return params


def handler(event, context):
    try:
        db = get_db()
        params = extract_params(event)
        query = normalize_search_text(params.get("query", ""))
        if not query:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {"error": "Параметр query не должен быть пустым"},
                    ensure_ascii=False,
                ),
            }

        results = []
        for inn, report in db.items():
            base = report.get("baseInfo", {})
            activity = report.get("kindsOfActivityInfo", {})
            main_activity = activity.get("mainKindOfActivity", {})
            other_activities = activity.get("otherKindsOfActivity", [])

            haystack_parts = [
                base.get("shortName", ""),
                base.get("fullName", ""),
                base.get("address", ""),
                main_activity.get("code", ""),
                main_activity.get("description", ""),
            ]
            for item in other_activities:
                haystack_parts.append(item.get("description", ""))

            haystack = normalize_search_text(" ".join(str(part) for part in haystack_parts))
            if query in haystack:
                results.append(
                    {
                        "inn": inn,
                        "name": base.get("shortName", "Без названия"),
                        "riskLevel": base.get("riskLevel", "неизвестно"),
                        "address": base.get("address", ""),
                    }
                )
            if len(results) >= MAX_RESULTS:
                break

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"results": results, "count": len(results)}, ensure_ascii=False
            ),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(exc)}, ensure_ascii=False),
        }
