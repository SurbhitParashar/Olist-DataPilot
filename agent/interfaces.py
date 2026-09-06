from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    ok: bool
    rows: int = 0
    error: str | None = None


@dataclass
class AgentResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    insight: str = ''
    chart_type_hint: str | None = None
    title: str = 'Olist analysis'
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_trace: list[ToolTrace] = field(default_factory=list)


class ILLMAgent(Protocol):
    async def run(self, query: str) -> AgentResult:
        ...
