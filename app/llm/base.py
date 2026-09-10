"""LLM provider 抽象。

接新家（Claude / OpenAI / 本地模型）只需要再实现一个子类并在 get_provider()
里注册，pipeline 和 prompt 都不用动。
"""
from __future__ import annotations

import abc
import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMProvider(abc.ABC):
    """所有 provider 都只暴露"给我结构化 JSON"这一个能力。"""

    @abc.abstractmethod
    async def complete(
        self, *, system: str, user: str, model: str, json_mode: bool = True
    ) -> str:
        ...

    async def complete_json(
        self, *, system: str, user: str, model: str
    ) -> dict[str, Any]:
        raw = await self.complete(system=system, user=user, model=model)
        return parse_json(raw)

    async def aclose(self) -> None:
        return None


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def parse_json(raw: str) -> dict[str, Any]:
    """模型偶尔会套 markdown 围栏或在 JSON 前后加寒暄，这里兜住。"""
    text = _FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 退一步：抓第一个 { 到最后一个 } 之间的内容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"模型返回的不是合法 JSON: {text[:300]}") from e
    raise LLMError(f"模型返回的不是合法 JSON: {text[:300]}")
