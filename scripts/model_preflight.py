from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from pydantic import ValidationError

from finance_advisor.agent.model_config import load_model_runtime_config

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_snapshot",
            "description": "Return an ETF market snapshot.",
            "parameters": {
                "type": "object",
                "properties": {"symbols": {"type": "array", "items": {"type": "string"}}},
                "required": ["symbols"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assess_investor_profile",
            "description": "Assess an investor profile.",
            "parameters": {
                "type": "object",
                "properties": {"amount_cny": {"type": "number"}},
                "required": ["amount_cny"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_RESULTS = {
    "get_market_snapshot": {"ok": True, "data": {"price": 4.0}},
    "assess_investor_profile": {"ok": True, "data": {"risk_level": "稳健型"}},
}


class PreflightError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _post_chat(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=_headers(api_key),
        json=payload,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("choices"):
        raise PreflightError("chat/completions returned no choices")
    return body


def check_endpoint(
    *,
    label: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> None:
    if not base_url.startswith(("http://", "https://")):
        raise PreflightError(f"{label}: base URL is invalid")
    if not api_key:
        raise PreflightError(f"{label}: API key is empty")
    if not model:
        raise PreflightError(f"{label}: model id is empty")

    leaked_values = [value for value in (api_key, base_url) if value]
    visible_text: list[str] = []
    with httpx.Client(
        timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 15.0))
    ) as client:
        models_ok = False
        try:
            response = client.get(f"{base_url.rstrip('/')}/models", headers=_headers(api_key))
            if response.is_success:
                model_ids = {item.get("id") for item in response.json().get("data", [])}
                models_ok = model in model_ids or bool(model_ids)
        except (httpx.HTTPError, ValueError):
            models_ok = False

        basic = _post_chat(
            client,
            base_url,
            api_key,
            {
                "model": model,
                "messages": [{"role": "user", "content": "只回复 OK"}],
                "temperature": 0,
            },
        )
        basic_content = basic["choices"][0]["message"].get("content") or ""
        if not basic_content.strip():
            raise PreflightError(f"{label}: ordinary chat returned empty content")
        visible_text.append(basic_content)

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "请先调用 get_market_snapshot 查询510300，再调用 "
                    "assess_investor_profile 评估50000元；两个工具都完成后再总结。"
                ),
            }
        ]
        called: set[str] = set()
        final_content = ""
        for _ in range(5):
            response = _post_chat(
                client,
                base_url,
                api_key,
                {
                    "model": model,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0,
                },
            )
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                final_content = message.get("content") or ""
                visible_text.append(final_content)
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                name = call.get("function", {}).get("name")
                arguments_text = call.get("function", {}).get("arguments", "{}")
                arguments = json.loads(arguments_text)
                if not isinstance(arguments, dict) or name not in TOOL_RESULTS:
                    raise PreflightError(f"{label}: malformed tool call")
                called.add(name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(TOOL_RESULTS[name], ensure_ascii=False),
                    }
                )

        required = set(TOOL_RESULTS)
        if called != required:
            raise PreflightError(f"{label}: required tools were not both called")
        if not final_content.strip():
            raise PreflightError(f"{label}: no final answer after tool results")
        if any(secret in text for secret in leaked_values for text in visible_text):
            raise PreflightError(f"{label}: response leaked endpoint configuration")

    models_note = (
        "models endpoint OK" if models_ok else "models endpoint unavailable; chat config OK"
    )
    print(f"{label}: chat, multi-tool and second-round checks passed ({models_note})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-model", action="store_true")
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()

    values = {**dotenv_values(args.env_file), **os.environ}
    relay_key = str(values.get("RELAY_API_KEY") or "")
    deepseek_key = str(values.get("DEEPSEEK_API_KEY") or "")

    try:
        runtime = load_model_runtime_config(args.env_file)
    except ValidationError:
        print("Model preflight failed: model runtime configuration is invalid", file=sys.stderr)
        return 1

    if not relay_key or "example.invalid" in runtime.primary_base_url_text:
        message = "Primary relay preflight skipped: configure RELAY_BASE_URL and RELAY_API_KEY"
        if args.require_model:
            print(message, file=sys.stderr)
            return 1
        print(message)
        return 0

    try:
        check_endpoint(
            label="primary relay",
            base_url=runtime.primary_base_url_text,
            api_key=relay_key,
            model=runtime.primary_model,
            timeout_seconds=runtime.request_timeout_seconds,
        )
        if runtime.fallback_enabled and deepseek_key:
            check_endpoint(
                label="DeepSeek fallback",
                base_url=runtime.deepseek_base_url_text,
                api_key=deepseek_key,
                model=runtime.deepseek_model,
                timeout_seconds=runtime.request_timeout_seconds,
            )
        elif runtime.fallback_enabled and args.require_model:
            raise PreflightError("DeepSeek fallback key is empty")
        elif runtime.fallback_enabled:
            print("DeepSeek fallback preflight skipped: DEEPSEEK_API_KEY is empty")
        else:
            print("DeepSeek fallback preflight disabled by configuration")
    except PreflightError as exc:
        print(f"Model preflight failed: {exc}", file=sys.stderr)
        return 1
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        print(
            f"Model preflight failed: endpoint request failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
