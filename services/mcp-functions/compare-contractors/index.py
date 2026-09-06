import json
from pathlib import Path

from report_projection import ProjectionValidationError, project_reports


BUCKET = "contractor-reports"
KEY = "reports_by_inn.json"
MAX_CONTRACTORS = 10
MOUNT_DB_PATH = Path("/function/storage/contractor-reports/reports_by_inn.json")

_DB_CACHE = None
_S3_CLIENT = None


def get_s3_client():
    """Create the S3 fallback lazily using the service-account credential chain."""
    global _S3_CLIENT
    if _S3_CLIENT is None:
        import boto3

        _S3_CLIENT = boto3.client(
            "s3",
            endpoint_url="https://storage.yandexcloud.net",
            region_name="ru-central1",
        )
    return _S3_CLIENT


def get_db():
    global _DB_CACHE
    if _DB_CACHE is None:
        try:
            with MOUNT_DB_PATH.open("r", encoding="utf-8") as mounted_file:
                _DB_CACHE = json.load(mounted_file)
        except FileNotFoundError:
            obj = get_s3_client().get_object(Bucket=BUCKET, Key=KEY)
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
        inn_list = params.get("inn_list", [])
        if not isinstance(inn_list, list) or not 2 <= len(inn_list) <= MAX_CONTRACTORS:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {"error": "Параметр inn_list должен быть списком из 2–10 ИНН"},
                    ensure_ascii=False,
                ),
            }

        normalized_inns = []
        for inn in inn_list:
            if not isinstance(inn, str):
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(
                        {"error": "Каждый ИНН должен быть строкой из 10 или 12 цифр"},
                        ensure_ascii=False,
                    ),
                }
            inn_clean = inn.strip()
            if not inn_clean.isdigit() or len(inn_clean) not in (10, 12):
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(
                        {"error": "Каждый ИНН должен быть строкой из 10 или 12 цифр"},
                        ensure_ascii=False,
                    ),
                }
            normalized_inns.append(inn_clean)

        results = []
        for inn_clean in normalized_inns:
            report = db.get(inn_clean)
            results.append(
                report if report else {"inn": inn_clean, "error": "не найден в базе"}
            )

        projected_results = project_reports(
            results,
            view=params.get("view", "full"),
            sections=params.get("sections"),
            active_limit=params.get("active_limit", 20),
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"reports": projected_results}, ensure_ascii=False),
        }
    except ProjectionValidationError as exc:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(exc)}, ensure_ascii=False),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(exc)}, ensure_ascii=False),
        }
