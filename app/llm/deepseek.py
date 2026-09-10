"""DeepSeek provider。API 与 OpenAI 兼容，直接用 httpx，不引 sdk。"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.llm.base import LLMError, LLMProvider
from config.settings import settings

log = logging.getLogger(__name__)

_RETRYABLE = {408, 429, 500, 502, 503, 504}


class DeepSeekProvider(LLMProvider):
    def __init__(self, timeout: float = 180.0, max_retries: int = 3) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.deepseek_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self._max_retries = max_retries

    async def complete(
        self, *, system: str, user: str, model: str, json_mode: bool = True
    ) -> str:
        payload: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "stream": False,
        }
        # reasoner 模型不接受 response_format，会直接报错
        if json_mode and "reasoner" not in model:
            payload["response_format"] = {"type": "json_object"}

        last: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                if resp.status_code in _RETRYABLE:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except (httpx.HTTPStatusError, httpx.TransportError, KeyError) as e:
                last = e
                if attempt == self._max_retries:
                    break
                backoff = 2 ** attempt
                log.warning(
                    "DeepSeek 调用失败 (%s/%s)，%ss 后重试: %s",
                    attempt, self._max_retries, backoff, e,
                )
                await asyncio.sleep(backoff)
        raise LLMError(f"DeepSeek 调用失败: {last}") from last

    async def aclose(self) -> None:
        await self._client.aclose()


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = DeepSeekProvider()
    return _provider


async def close_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.aclose()
        _provider = None
