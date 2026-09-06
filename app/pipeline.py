from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from app.charts import build_chart
from app.config import settings
from app.guardrails import guard_query
from agent.fallback_agent import RuleBasedAgent
from agent.llm_agent import OpenRouterAgent


class AnalyticsPipeline:
    def __init__(self):
        self.llm = OpenRouterAgent(
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.mcp_url,
            settings.llm_timeout_seconds,
            settings.tool_timeout_seconds,
        )
        self.fallback = RuleBasedAgent(settings.mcp_url, settings.tool_timeout_seconds)

    async def run(self, query: str, force_mode: str | None = None) -> dict[str, Any]:
        blocked = guard_query(query)
        if blocked:
            return {
                'query': query, 'assumptions': [], 'chart_type': 'none',
                'chart_justification': blocked, 'insight': blocked,
                'chart_config': {}, 'rows': [], 'tool_trace': [],
                'agent_mode': force_mode or settings.agent_mode, 'warnings': [],
            }

        mode = force_mode or settings.agent_mode
        warnings: list[str] = []
        if mode == 'llm' and not settings.openrouter_api_key:
            warnings.append('OPENROUTER_API_KEY is not configured; using the rule-based fallback.')
            mode = 'fallback'

        try:
            agent = self.llm if mode == 'llm' else self.fallback
            result = await agent.run(query)
        except Exception as exc:
            if mode == 'llm':
                result = await self.fallback.run(query)
                mode = 'fallback'
                warnings.append(f'LLM agent failed and fallback was used: {type(exc).__name__}.')
            else:
                raise

        chart_type, justification, chart_config = build_chart(query, result.tool_results)
        if chart_type == 'none':
            chart_config = {}
        warnings.extend(result.warnings)
        return {
            'query': query,
            'assumptions': result.assumptions,
            'chart_type': chart_type,
            'chart_justification': justification,
            'insight': result.insight,
            'chart_config': chart_config,
            'rows': result.rows[:200],
            'tool_trace': [
                {'name': t.name, 'arguments': t.arguments, 'ok': t.ok, 'rows': t.rows, 'error': t.error}
                for t in result.tool_trace
            ],
            'agent_mode': mode,
            'warnings': warnings,
        }


def numeric_fingerprint(payload: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for dataset in payload.get('chart_config', {}).get('data', {}).get('datasets', []):
        for item in dataset.get('data', []):
            if isinstance(item, dict):
                for key in ('x', 'y'):
                    val = item.get(key)
                    if isinstance(val, (int, float)):
                        values.append(float(val))
            elif isinstance(item, (int, float)):
                values.append(float(item))
    return values


def compare_payloads(old: dict[str, Any], new: dict[str, Any]) -> tuple[bool, float]:
    a, b = numeric_fingerprint(old), numeric_fingerprint(new)
    if not a or not b:
        return old.get('chart_config') != new.get('chart_config'), 1.0 if old.get('chart_config') != new.get('chart_config') else 0.0
    n = min(len(a), len(b))
    if n == 0:
        return True, 1.0
    denom = sum(abs(x) for x in a[:n]) / n or 1.0
    diff = sum(abs(x-y) for x, y in zip(a[:n], b[:n])) / n
    score = diff / denom
    return score >= 0.05, score
