#!/usr/bin/env python3
"""Test which CAILA models are available with your API key.

Usage:
    python test_caila_models.py

This will test each model from the candidate list and show which ones work.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from dotenv import load_dotenv

# Load .env
load_dotenv()

CAILA_API_KEY = os.getenv("JUDGE_API_KEY", "")
CAILA_BASE_URL = os.getenv("JUDGE_BASE_URL", "https://caila.io/api/adapters/openai")

# Candidate models to test based on caila.io/catalog
CANDIDATE_MODELS = [
    # OpenAI GPT-5.6 series
    ("gpt-5.6-luna", "OpenAI GPT-5.6 Luna"),
    ("gpt-5.6-terra", "OpenAI GPT-5.6 Terra"),
    ("gpt-5.6-sol", "OpenAI GPT-5.6 Sol"),
    # OpenAI GPT-5.x
    ("gpt-5", "OpenAI GPT-5"),
    ("gpt-5.5", "OpenAI GPT-5.5"),
    ("gpt-5-mini", "OpenAI GPT-5 Mini"),
    # OpenAI GPT-4.1 series
    ("gpt-4.1", "OpenAI GPT-4.1"),
    ("gpt-4.1-mini", "OpenAI GPT-4.1 Mini"),
    ("gpt-4o", "OpenAI GPT-4o"),
    ("gpt-4o-mini", "OpenAI GPT-4o Mini"),
    # Anthropic Claude
    ("claude-opus-5", "Anthropic Claude Opus 5"),
    ("claude-fable-5", "Anthropic Claude Fable 5"),
    ("claude-opus-4-8", "Anthropic Claude Opus 4.8"),
    ("claude-opus-4.8", "Anthropic Claude Opus 4.8 (alt ID)"),
    ("claude-sonnet-4", "Anthropic Claude Sonnet 4"),
    ("claude-haiku-4.5", "Anthropic Claude Haiku 4.5"),
    # Google Gemini
    ("gemini-3.1-pro", "Google Gemini 3.1 Pro"),
    ("gemini-2.0-flash-exp", "Google Gemini 2.0 Flash Exp"),
    # Zhipu GLM
    ("glm-5.3-flash", "Zhipu GLM-5.3 Flash"),
    # DeepSeek
    ("deepseek-v3", "DeepSeek v3"),
]

async def test_model(client: httpx.AsyncClient, model_id: str, display_name: str) -> dict:
    """Test if a model is available."""
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
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "model_id": model_id,
                "display_name": display_name,
                "status": "✅ WORKS",
                "http_status": 200,
                "response": content[:50],
            }
        elif response.status_code == 400:
            error_data = response.json()
            error_msg = error_data.get("message", "")
            if "unknown_model_by_proxy" in error_msg or "unknown" in error_msg.lower():
                return {
                    "model_id": model_id,
                    "display_name": display_name,
                    "status": "❌ NOT IN PRICING",
                    "http_status": 400,
                    "error": "Model not in your pricing plan",
                }
            else:
                return {
                    "model_id": model_id,
                    "display_name": display_name,
                    "status": "⚠️ ERROR",
                    "http_status": 400,
                    "error": error_msg[:100],
                }
        else:
            return {
                "model_id": model_id,
                "display_name": display_name,
                "status": "⚠️ ERROR",
                "http_status": response.status_code,
                "error": response.text[:100],
            }
    except Exception as e:
        return {
            "model_id": model_id,
            "display_name": display_name,
            "status": "⚠️ ERROR",
            "error": str(e)[:100],
        }

async def main():
    if not CAILA_API_KEY:
        print("❌ ERROR: JUDGE_API_KEY not found in .env")
        print("Please add your CAILA API key to .env file:")
        print("  JUDGE_API_KEY=your-caila-key")
        return

    print("🔍 Testing CAILA models with your API key...")
    print(f"📍 Base URL: {CAILA_BASE_URL}")
    print(f"🔑 API Key: {CAILA_API_KEY[:10]}...{CAILA_API_KEY[-4:]}")
    print(f"📊 Testing {len(CANDIDATE_MODELS)} models...")
    print()

    async with httpx.AsyncClient() as client:
        results = []
        for model_id, display_name in CANDIDATE_MODELS:
            print(f"Testing {model_id:30} ", end="", flush=True)
            result = await test_model(client, model_id, display_name)
            results.append(result)
            print(result["status"])

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80 + "\n")

    working = [r for r in results if r["status"] == "✅ WORKS"]
    not_available = [r for r in results if "NOT IN PRICING" in r["status"]]
    errors = [r for r in results if r["status"] == "⚠️ ERROR"]

    print(f"✅ WORKING MODELS ({len(working)}):")
    print("-" * 80)
    if working:
        for r in working:
            print(f"  {r['model_id']:30} — {r['display_name']}")
    else:
        print("  None found")

    print(f"\n❌ NOT IN YOUR PRICING PLAN ({len(not_available)}):")
    print("-" * 80)
    if not_available:
        for r in not_available:
            print(f"  {r['model_id']:30} — {r['display_name']}")
    else:
        print("  None")

    if errors:
        print(f"\n⚠️ ERRORS ({len(errors)}):")
        print("-" * 80)
        for r in errors:
            print(f"  {r['model_id']:30} — {r.get('error', 'Unknown error')[:50]}")

    print("\n" + "="*80)
    print("CONFIGURATION")
    print("="*80 + "\n")

    if working:
        print("Add these to your .env file:")
        print()
        print("JUDGE_MODELS=" + ",".join(r["model_id"] for r in working))
        print(f"DEFAULT_JUDGE_MODEL={working[0]['model_id']}")
        print()
        print("Or copy this Python code to app/judge_models.py PROFILES:")
        print()
        for r in working:
            provider = r["display_name"].split()[0]
            tier = "fast" if "mini" in r["model_id"] or "luna" in r["model_id"] else "standard"
            print(f'    "{r["model_id"]}": JudgeModelProfile(')
            print(f'        "{r["model_id"]}", "{provider}", "{r["display_name"]}", "{tier}"')
            print('    ),')
    else:
        print("❌ No working models found!")
        print("Check your CAILA API key and pricing plan.")

if __name__ == "__main__":
    asyncio.run(main())
