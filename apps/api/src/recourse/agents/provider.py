from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class StructuredModelResult:
    content: dict[str, Any]
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    request_id: str
    response_hash: str
    repaired: bool
    cached: bool
    input_hash: str | None = None
    prompt_hash: str | None = None
    schema_hash: str | None = None


class StructuredModelError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class StructuredModel(Protocol):
    async def generate(
        self, *, schema: dict, system_prompt: str, input_json: dict,
        timeout_seconds: float, request_id: str,
        purpose: Literal["diagnosis", "challenge"],
    ) -> StructuredModelResult: ...
