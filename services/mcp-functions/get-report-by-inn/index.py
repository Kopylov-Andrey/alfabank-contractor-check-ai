import json
from pathlib import Path

from report_projection import ProjectionValidationError, project_report


BUCKET = "contractor-reports"
KEY = "reports_by_inn.json"
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


def error_response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}, ensure_ascii=False),
    }


def handler(event, context):
    try:
        params = extract_params(event)
        inn = params.get("inn")
        if (
            not isinstance(inn, str)
            or not inn.isdigit()
            or len(inn) not in (10, 12)
        ):
            return error_response(
                400, "Параметр inn должен быть строкой из 10 или 12 цифр"
            )

        report = get_db().get(inn)
        if report is None:
            return error_response(404, "Контрагент с указанным ИНН не найден в базе")

        projected = project_report(
            report,
            view=params.get("view", "full"),
            sections=params.get("sections"),
            active_limit=params.get("active_limit", 20),
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(projected, ensure_ascii=False),
        }
    except ProjectionValidationError as exc:
        return error_response(400, str(exc))
    except Exception as exc:
        return error_response(500, str(exc))
