from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


class GroqError(RuntimeError):
    pass


@dataclass(frozen=True)
class GroqChatMessage:
    role: str
    content: str


def _parse_groq_error(resp: requests.Response) -> tuple[str | None, str]:
    try:
        data = resp.json()
        err = data.get("error") if isinstance(data, dict) else None
        code = err.get("code") if isinstance(err, dict) else None
        msg = err.get("message") if isinstance(err, dict) else None
        if isinstance(msg, str) and msg.strip():
            return (code if isinstance(code, str) else None, msg.strip())
    except Exception:
        pass
    return (None, resp.text.strip())


def chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[GroqChatMessage],
    temperature: float = 0.0,
    max_tokens: int = 700,
    timeout_s: int = 30,
    fallback_models: list[str] | None = None,
) -> str:
    if not api_key:
        raise GroqError("Missing GROQ_API_KEY")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    tried_models: list[str] = []
    candidates = [model] + [m for m in (fallback_models or []) if m and m != model]
    for candidate in candidates:
        payload: dict[str, Any] = {
            "model": candidate,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        except requests.RequestException as e:
            raise GroqError(f"Groq request failed: {e}") from e

        if resp.status_code < 400:
            try:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                raise GroqError("Unexpected Groq response format") from e

        tried_models.append(candidate)
        code, msg = _parse_groq_error(resp)
        if code == "model_decommissioned" and candidate != candidates[-1]:
            continue
        raise GroqError(f"Groq API error {resp.status_code} (model={candidate}): {msg}")

    raise GroqError(f"Groq API error: all models failed: {', '.join(tried_models)}")
