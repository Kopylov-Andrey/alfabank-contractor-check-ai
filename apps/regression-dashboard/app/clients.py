from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .config import settings
from .judge_models import profile_for


class JudgeClientError(RuntimeError):
    def __init__(self, message: str, *, kind: str, diagnostics: dict | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.diagnostics = diagnostics or {}


def _redact(value: str, limit: int = 2000) -> str:
    value = value[:limit]
    for secret in (settings.judge_api_key, settings.yandex_api_key):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


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


    async def evaluate(
        self,
        *,
        model: str,
        system: str,
        user: str,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict:
        if model not in settings.judge_models:
            raise JudgeClientError("Модель судьи отсутствует в серверном allowlist", kind="model")
        if not settings.judge_api_key or not settings.judge_base_url:
            raise JudgeClientError("JUDGE_API_KEY или JUDGE_BASE_URL не настроены", kind="integration")
        endpoint = settings.judge_base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        profile = profile_for(model)
        if not profile.supports_chat_completions:
            raise JudgeClientError("Профиль модели не поддерживает Chat Completions", kind="model")
        payload = {"model": model, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]}
        response = await self.client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {settings.judge_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.is_error:
            detail = response.text.strip() or "empty response body"
            raise JudgeClientError(
                f"CAILA HTTP {response.status_code}: {_redact(detail)}", kind="judge",
                diagnostics={"model": model, "http_status": response.status_code,
                             "request_shape": sorted(payload), "upstream": _redact(detail)},
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise JudgeClientError(
                "CAILA returned an invalid Chat Completions response", kind="judge",
                diagnostics={"model": model, "http_status": response.status_code,
                             "request_shape": sorted(payload), "upstream": _redact(response.text)},
            ) from error
        from .evaluation import parse_judge_response
        try:
            return parse_judge_response(content)
        except (ValueError, KeyError, TypeError) as error:
            # Exactly one correction request; never retry upstream/auth/rate/server errors.
            if should_cancel and should_cancel():
                raise JudgeClientError(
                    "Run was cancelled before the judge correction retry", kind="cancelled",
                    diagnostics={"model": model, "request_shape": sorted(payload),
                                 "correction_retry": {"attempted": False, "reason": "cancelled"}},
                ) from error
            correction = {"model": model, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "user", "content": "Верни тот же вердикт в валидном JSON по схеме. Никакого текста вне JSON."},
            ]}
            retry = await self.client.post(endpoint, headers={
                "Authorization": f"Bearer {settings.judge_api_key}", "Content-Type": "application/json"
            }, json=correction)
            if not retry.is_error:
                try:
                    parsed = parse_judge_response(retry.json()["choices"][0]["message"]["content"])
                    parsed["correction_retry"] = {"attempted": True, "succeeded": True}
                    return parsed
                except (ValueError, KeyError, IndexError, TypeError):
                    pass
            raise JudgeClientError(
                f"Невалидный JSON LLM-судьи: {error}", kind="judge",
                diagnostics={"model": model, "http_status": response.status_code,
                             "request_shape": sorted(payload), "raw_judge_response": _redact(str(content)),
                             "correction_retry": {"attempted": True, "succeeded": False,
                                                   "http_status": retry.status_code}},
            ) from error
