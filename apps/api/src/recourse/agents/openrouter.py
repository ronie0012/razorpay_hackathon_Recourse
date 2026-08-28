from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from recourse.agents.provider import StructuredModelError, StructuredModelResult
from recourse.agents.schemas import ChallengeOutput, DiagnosisOutput
from recourse.config import Settings
from recourse.domain.audit import canonical_json

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
VALIDATORS: dict[str, type[BaseModel]] = {"diagnosis": DiagnosisOutput, "challenge": ChallengeOutput}
VERSIONS = {"diagnosis": ("diagnose-v1", "diagnosis-v1"), "challenge": ("challenge-v1", "challenge-v1")}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        if parts:
            return "".join(parts)
    raise TypeError("message content is not text")


def _json_object(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise TypeError("model output is not a JSON object")
    return parsed


def cache_key(*, input_json: dict, model: str, prompt: str, schema: dict, max_tokens: int) -> str:
    key = {
        "input_hash": _hash_text(canonical_json(input_json)), "model": model,
        "prompt_hash": _hash_text(prompt), "schema_hash": _hash_text(canonical_json(schema)),
        "temperature": 0, "max_tokens": max_tokens,
    }
    return _hash_text(canonical_json(key))


class OpenRouterStructuredModel:
    _cache: dict[str, StructuredModelResult] = {}

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    def _headers(self, request_id: str) -> dict[str, str]:
        if not self.settings.openrouter_api_key:
            raise StructuredModelError("OPENROUTER_NOT_CONFIGURED", "OpenRouter is not configured")
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json", "X-Request-ID": request_id,
            "X-Title": self.settings.openrouter_app_title,
        }
        if self.settings.openrouter_app_url:
            headers["HTTP-Referer"] = self.settings.openrouter_app_url
        return headers

    async def generate(
        self, *, schema: dict, system_prompt: str, input_json: dict,
        timeout_seconds: float, request_id: str,
        purpose: Literal["diagnosis", "challenge"],
    ) -> StructuredModelResult:
        if not self.settings.openrouter_enabled:
            raise StructuredModelError("OPENROUTER_DISABLED", "OpenRouter calls are disabled")
        validator = VALIDATORS[purpose]
        prompt_version, schema_version = VERSIONS[purpose]
        key = cache_key(input_json=input_json, model=self.settings.openrouter_model, prompt=system_prompt,
                        schema=schema, max_tokens=self.settings.openrouter_max_tokens)
        cached = self._cache.get(key)
        if cached:
            try:
                validated = validator.model_validate(cached.content)
            except ValidationError:
                self._cache.pop(key, None)
            else:
                return StructuredModelResult(**{**cached.__dict__, "content": validated.model_dump(mode="json"), "cached": True})

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": canonical_json({"schema": schema, "input": input_json})},
        ]
        started = time.perf_counter()
        transient_retry_used = False
        repaired = False
        last_validation_error: str | None = None
        raw_content = ""
        response_data: dict[str, Any] = {}
        own_client = self.client is None
        client = self.client or httpx.AsyncClient()
        try:
            for validation_attempt in range(2):
                while True:
                    payload = {
                        "model": self.settings.openrouter_model, "messages": messages,
                        "temperature": 0, "max_tokens": self.settings.openrouter_max_tokens,
                    }
                    try:
                        async with asyncio.timeout(timeout_seconds):
                            response = await client.post(
                                self.settings.openrouter_base_url.rstrip("/") + "/chat/completions",
                                headers=self._headers(request_id), json=payload,
                                timeout=httpx.Timeout(timeout_seconds),
                            )
                    except (TimeoutError, httpx.TimeoutException) as exc:
                        raise StructuredModelError("OPENROUTER_TIMEOUT", "OpenRouter request timed out", retryable=True) from exc
                    except httpx.TransportError as exc:
                        if not transient_retry_used:
                            transient_retry_used = True
                            await asyncio.sleep(.05)
                            continue
                        raise StructuredModelError("OPENROUTER_TRANSPORT", "OpenRouter transport failed", retryable=True) from exc
                    if response.status_code in TRANSIENT_STATUSES and not transient_retry_used:
                        transient_retry_used = True
                        await asyncio.sleep(.05)
                        continue
                    if response.status_code == 401:
                        raise StructuredModelError("OPENROUTER_AUTH", "OpenRouter authentication failed")
                    if response.status_code == 402:
                        raise StructuredModelError("OPENROUTER_CREDITS", "OpenRouter credits are unavailable")
                    if response.status_code >= 400:
                        code = "OPENROUTER_RATE_LIMIT" if response.status_code == 429 else "OPENROUTER_HTTP_ERROR"
                        raise StructuredModelError(code, f"OpenRouter returned HTTP {response.status_code}", retryable=response.status_code in TRANSIENT_STATUSES)
                    try:
                        response_data = response.json()
                        raw_content = _message_text(response_data["choices"][0]["message"]["content"])
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        raise StructuredModelError("OPENROUTER_RESPONSE_SHAPE", "OpenRouter response shape was invalid") from exc
                    break
                try:
                    parsed = _json_object(raw_content)
                    validated = validator.model_validate(parsed)
                    break
                except (json.JSONDecodeError, TypeError, ValidationError) as exc:
                    last_validation_error = str(exc)[:1000]
                    if validation_attempt == 1:
                        raise StructuredModelError("OPENROUTER_SCHEMA", "OpenRouter output failed schema validation after one repair") from exc
                    repaired = True
                    messages.extend([
                        {"role": "assistant", "content": raw_content[:8000]},
                        {"role": "user", "content": canonical_json({
                            "repair": "Return corrected JSON only. Keep the same evidence IDs; do not add facts.",
                            "schema_error": last_validation_error, "schema": schema,
                        })},
                    ])
        finally:
            if own_client:
                await client.aclose()
        usage = response_data.get("usage") or {}
        result = StructuredModelResult(
            content=validated.model_dump(mode="json"), provider="openrouter",
            model=str(response_data.get("model") or self.settings.openrouter_model),
            prompt_version=prompt_version, schema_version=schema_version,
            latency_ms=round((time.perf_counter() - started) * 1000),
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            request_id=request_id, response_hash=_hash_text(raw_content), repaired=repaired, cached=False,
            input_hash=_hash_text(canonical_json(input_json)), prompt_hash=_hash_text(system_prompt),
            schema_hash=_hash_text(canonical_json(schema)),
        )
        self._cache[key] = result
        return result
