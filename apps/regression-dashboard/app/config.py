from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    yandex_api_key: str = os.getenv("YANDEX_API_KEY", "")
    yandex_folder_id: str = os.getenv("YANDEX_FOLDER_ID", "b1gfdj9gscod1qetbbpj")
    yandex_agent_id: str = os.getenv("YANDEX_AGENT_ID", "fvtq3dj5gqmo38h4mk94")
    yandex_responses_url: str = os.getenv(
        "YANDEX_RESPONSES_URL", "https://ai.api.cloud.yandex.net/v1/responses"
    )
    mcp_server_url: str = os.getenv(
        "MCP_SERVER_URL",
        "https://db81uub1t2h5sr9vjs0u.fi4781wp.mcpgw.serverless.yandexcloud.net",
    )
    judge_api_key: str = os.getenv("JUDGE_API_KEY", "")
    judge_base_url: str = os.getenv("JUDGE_BASE_URL", "https://caila.io/api/adapters/openai").rstrip("/")
    # Only verified working models - customize in .env based on your CAILA pricing plan
    judge_models: tuple[str, ...] = _csv(
        "JUDGE_MODELS",
        "gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol"
    )
    default_judge_model: str = os.getenv("DEFAULT_JUDGE_MODEL", "gpt-5.6-luna")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./regression.db").replace(
        "postgres://", "postgresql+psycopg://", 1
    )
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    max_concurrency: int = max(1, min(int(os.getenv("MAX_CONCURRENCY", "2")), 5))
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "240"))


settings = Settings()

