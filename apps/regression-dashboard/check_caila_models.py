#!/usr/bin/env python3
"""Check which CAILA judge models are available for the configured account.

Usage:
    python check_caila_models.py
"""

import asyncio
import os
from pathlib import Path
import sys

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

CAILA_API_KEY = os.getenv("JUDGE_API_KEY", "")
CAILA_BASE_URL = os.getenv("JUDGE_BASE_URL", "https://caila.io/api/adapters/openai").rstrip("/")

CANDIDATE_MODELS = [
    ("gpt-5.6-luna", "OpenAI GPT-5.6 Luna"),
    ("gpt-5.6-terra", "OpenAI GPT-5.6 Terra"),
    ("gpt-5.6-sol", "OpenAI GPT-5.6 Sol"),
    ("gpt-5", "OpenAI GPT-5"),
    ("gpt-5.5", "OpenAI GPT-5.5"),
    ("gpt-5-mini", "OpenAI GPT-5 Mini"),
    ("gpt-4.1", "OpenAI GPT-4.1"),
    ("gpt-4.1-mini", "OpenAI GPT-4.1 Mini"),
    ("gpt-4o", "OpenAI GPT-4o"),
    ("gpt-4o-mini", "OpenAI GPT-4o Mini"),
    ("claude-opus-5", "Anthropic Claude Opus 5"),
    ("claude-fable-5", "Anthropic Claude Fable 5"),
    ("claude-opus-4-8", "Anthropic Claude Opus 4.8"),
    ("claude-opus-4.8", "Anthropic Claude Opus 4.8 (alt ID)"),
    ("claude-sonnet-4", "Anthropic Claude Sonnet 4"),
    ("claude-haiku-4.5", "Anthropic Claude Haiku 4.5"),
    ("gemini-3.1-pro", "Google Gemini 3.1 Pro"),
    ("gemini-2.0-flash-exp", "Google Gemini 2.0 Flash Exp"),
    ("glm-5.3-flash", "Zhipu GLM-5.3 Flash"),
    ("deepseek-v3", "DeepSeek v3"),
]


async def check_model(client: httpx.AsyncClient, model_id: str, display_name: str) -> dict:
    endpoint = f"{CAILA_BASE_URL}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with OK"}],
        "max_tokens": 5,
    }
    try:
        response = await client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {CAILA_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        if response.status_code == 200:
            return {"model_id": model_id, "display_name": display_name, "status": "WORKS"}
        if response.status_code == 400:
            try:
                detail = response.json()
            except ValueError:
                detail = {}
            message = str(detail.get("message", ""))
            if "unknown_model_by_proxy" in message or "unknown" in message.lower():
                return {"model_id": model_id, "display_name": display_name, "status": "NOT_AVAILABLE"}
        return {
            "model_id": model_id,
            "display_name": display_name,
            "status": "ERROR",
            "http_status": response.status_code,
        }
    except Exception as exc:
        return {
            "model_id": model_id,
            "display_name": display_name,
            "status": "ERROR",
            "error": type(exc).__name__,
        }


async def main() -> None:
    if not CAILA_API_KEY:
        print("JUDGE_API_KEY is not configured in .env")
        return

    print(f"CAILA endpoint: {CAILA_BASE_URL}")
    print(f"Checking {len(CANDIDATE_MODELS)} candidate models...")

    async with httpx.AsyncClient() as client:
        results = []
        for model_id, display_name in CANDIDATE_MODELS:
            result = await check_model(client, model_id, display_name)
            results.append(result)
            print(f"{model_id:30} {result['status']}")

    working = [item for item in results if item["status"] == "WORKS"]
    print("\nWorking models:")
    for item in working:
        print(f"  {item['model_id']} — {item['display_name']}")

    if working:
        print("\nSuggested configuration:")
        print("JUDGE_MODELS=" + ",".join(item["model_id"] for item in working))
        print(f"DEFAULT_JUDGE_MODEL={working[0]['model_id']}")


if __name__ == "__main__":
    asyncio.run(main())
