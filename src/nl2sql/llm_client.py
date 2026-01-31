from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import requests


class LLMError(RuntimeError):
    pass


Provider = Literal["gemini", "groq"]


@dataclass(frozen=True)
class LLMChatMessage:
    role: str
    content: str


def _parse_json_error(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            if isinstance(data.get("error"), dict):
                err = data["error"]
                msg = err.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            if isinstance(data.get("message"), str) and data["message"].strip():
                return data["message"].strip()
    except Exception:
        pass
    return resp.text.strip()


def _gemini_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[LLMChatMessage],
    temperature: float,
    max_tokens: int,
    timeout_s: int,
) -> str:
    if not api_key:
        raise LLMError("Missing GEMINI_API_KEY")

    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = (m.role or "").strip().lower()
        text = (m.content or "").strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue
        gemini_role = "user" if role == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": text}]})

    payload: dict[str, Any] = {
        "contents": contents or [{"role": "user", "parts": [{"text": ""}]}],
        "generationConfig": {"temperature": float(temperature), "maxOutputTokens": int(max_tokens)},
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

    model = (model or "").strip()
    if model.startswith("models/"):
        model = model[len("models/") :]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
    except requests.RequestException as e:
        raise LLMError(f"Gemini request failed: {e}") from e

    if resp.status_code >= 400:
        detail = _parse_json_error(resp)
        if resp.status_code == 404:
            fallback = _choose_gemini_model(api_key=api_key, timeout_s=timeout_s)
            if fallback and fallback != model:
                return _gemini_chat_completion(
                    api_key=api_key,
                    model=fallback,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_s=timeout_s,
                )
        raise LLMError(f"Gemini API error {resp.status_code}: {detail}")

    try:
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise KeyError("candidates")
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise KeyError("parts")
        text = parts[0].get("text")
        if not isinstance(text, str):
            raise TypeError("text")
        return text
    except Exception as e:
        raise LLMError("Unexpected Gemini response format") from e


def _choose_gemini_model(*, api_key: str, timeout_s: int) -> str | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        resp = requests.get(url, timeout=timeout_s)
    except requests.RequestException:
        return None
    if resp.status_code >= 400:
        return None
    try:
        data = resp.json()
        models = data.get("models", []) if isinstance(data, dict) else []
        available: list[str] = []
        for m in models:
            if not isinstance(m, dict):
                continue
            name = m.get("name")
            methods = m.get("supportedGenerationMethods") or m.get("supported_generation_methods")
            if not isinstance(name, str):
                continue
            if isinstance(methods, list) and "generateContent" not in methods:
                continue
            if name.startswith("models/"):
                name = name[len("models/") :]
            available.append(name)
    except Exception:
        return None

    if not available:
        return None

    preferred = [
        "gemini-2.0-flash",
        "gemini-2.0-pro",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]
    for p in preferred:
        if p in available:
            return p
    return available[0]


def _groq_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[LLMChatMessage],
    temperature: float,
    max_tokens: int,
    timeout_s: int,
    fallback_models: list[str] | None,
) -> str:
    if not api_key:
        raise LLMError("Missing GROQ_API_KEY")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

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
            raise LLMError(f"Groq request failed: {e}") from e

        if resp.status_code < 400:
            try:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                raise LLMError("Unexpected Groq response format") from e

        tried_models.append(candidate)
        raise LLMError(f"Groq API error {resp.status_code} (model={candidate}): {_parse_json_error(resp)}")

    raise LLMError(f"Groq API error: all models failed: {', '.join(tried_models)}")


def chat_completion(
    *,
    provider: Provider,
    api_key: str,
    model: str,
    messages: list[LLMChatMessage],
    temperature: float = 0.0,
    max_tokens: int = 700,
    timeout_s: int = 45,
    fallback_models: list[str] | None = None,
) -> str:
    if provider == "gemini":
        return _gemini_chat_completion(
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    if provider == "groq":
        return _groq_chat_completion(
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            fallback_models=fallback_models,
        )
    raise LLMError("Unknown provider")
