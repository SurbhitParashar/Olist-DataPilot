from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)


class AskResponse(BaseModel):
    query: str
    assumptions: list[str]
    chart_type: str
    chart_justification: str
    insight: str
    chart_config: dict[str, Any]
    rows: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]] = []
    agent_mode: Literal['llm', 'fallback']
    warnings: list[str] = []


class PinRequest(BaseModel):
    query: str
    chart_payload: dict[str, Any]


class RefreshResponse(BaseModel):
    id: str
    changed: bool
    change_score: float
    message: str
    payload: dict[str, Any]
