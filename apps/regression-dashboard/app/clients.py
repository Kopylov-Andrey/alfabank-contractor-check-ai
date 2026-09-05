from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import settings


@dataclass
class AgentResponse:
    text: str
    response_id: str
    latency_ms: float
    usage: dict
    citations: list[dict]
    tool_calls: list[dict]
    raw: dict


def _extract_agent_response(data: dict, latency_ms: float) -> AgentResponse:
    texts: list[str] = []
    citations: list[dict] = []
    tool_calls: list[dict] = []
    for item in data.get("output", []):
        item_type = item.get("type", "")
        if item_type.endswith("_call") or item_type in {"mcp_call", "web_search_call"}:
            tool_calls.append(
                {
                    "type": item_type,
                    "name": item.get("name"),
                    "arguments": item.get("arguments"),
                    "status": item.get("status"),
                }
            )
        if item_type != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])
            for annotation in content.get("annotations", []):
                if annotation.get("type") == "url_citation":
                    url = annotation.get("url")
                    if url and not any(existing.get("url") == url for existing in citations):
                        citations.append({"url": url, "title": annotation.get("title", "")})
    text = "\n".join(texts).strip()
    if data.get("status") != "completed" or not text:
        raise RuntimeError(f"Незавершённый ответ агента: status={data.get('status')!r}")
    return AgentResponse(
        text=text,
        response_id=data.get("id", ""),
        latency_ms=latency_ms,
        usage=data.get("usage") or {},
        citations=citations,
        tool_calls=tool_calls,
        raw=data,
    )


class YandexAgentClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=settings.request_timeout_seconds, trust_env=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def ask(self, text: str, previous_response_id: str | None = None) -> AgentResponse:
        if not settings.yandex_api_key:
            raise RuntimeError("YANDEX_API_KEY не настроен")
        payload: dict[str, Any] = {
            "prompt": {"id": settings.yandex_agent_id},
            "input": text,
            "max_output_tokens": 12000,
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "contractor-check-mcp",
                    "server_url": settings.mcp_server_url,
                    "server_description": "База банковских отчётов о контрагентах",
                    "require_approval": "never",
                },
                {
                    "type": "web_search",
                    "filters": {"allowed_domains": []},
                    "search_context_size": "low",
                },
            ],
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        started = time.perf_counter()
        response = await self.client.post(
            settings.yandex_responses_url,
            json=payload,
            headers={
                "Authorization": f"Api-Key {settings.yandex_api_key}",
                "OpenAI-Project": settings.yandex_folder_id,
                "Content-Type": "application/json",
            },
        )
        latency_ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        return _extract_agent_response(response.json(), latency_ms)


class JudgeClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=settings.request_timeout_seconds, trust_env=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def evaluate(self, *, model: str, system: str, user: str) -> dict:
        if model not in settings.judge_models:
            raise RuntimeError("Модель судьи отсутствует в серверном allowlist")
        if not settings.judge_api_key or not settings.judge_base_url:
            raise RuntimeError("JUDGE_API_KEY или JUDGE_BASE_URL не настроены")
        endpoint = settings.judge_base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        response = await self.client.post(
            endpoint,
            headers={"Authorization": f"Bearer {settings.judge_api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            return content
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(cleaned)
