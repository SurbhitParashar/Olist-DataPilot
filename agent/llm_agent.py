from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
import re
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from agent.interfaces import AgentResult, ToolTrace
from agent.mcp_client import MCPAnalyticsClient
from agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AgentJSON(BaseModel):
    title: str = 'Olist analysis'
    insight: str = ''
    chart_type_hint: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OpenRouterAgent:
    def __init__(self, api_key: str, model: str, mcp_url: str, llm_timeout: float, tool_timeout: float):
        self.client = AsyncOpenAI(base_url='https://openrouter.ai/api/v1', api_key=api_key)
        self.model = model
        self.mcp_url = mcp_url
        self.llm_timeout = llm_timeout
        self.mcp = MCPAnalyticsClient(mcp_url, tool_timeout)

    async def _tool_specs(self) -> list[dict[str, Any]]:
        from mcp import Client
        async with Client(self.mcp_url) as client:
            page = await client.list_tools()
            return [
                {
                    'type': 'function',
                    'function': {
                        'name': t.name,
                        'description': t.description or t.title or t.name,
                        'parameters': t.input_schema,
                    },
                }
                for t in page.tools
            ]

    async def _completion(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        kwargs: dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': 0,
        }
        if tools is not None:
            kwargs['tools'] = tools
            kwargs['tool_choice'] = 'auto'
        return await asyncio.wait_for(
            self.client.chat.completions.create(**kwargs),
            timeout=self.llm_timeout,
        )

    async def run(self, query: str) -> AgentResult:
        tools = await self._tool_specs()
        messages: list[dict[str, Any]] = [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': query},
        ]

        trace: list[ToolTrace] = []
        all_rows: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        warnings: list[str] = []

        for _ in range(3):
            response = await self._completion(messages, tools)
            message = response.choices[0].message
            if not message.tool_calls:
                break

            messages.append(message.model_dump(exclude_none=True))
            for tool_call in message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments or '{}')
                except json.JSONDecodeError:
                    args = {}
                    warnings.append(f'Invalid arguments returned for {tool_call.function.name}; tool skipped.')
                    trace.append(ToolTrace(tool_call.function.name, {}, False, error='invalid JSON arguments'))
                    continue

                try:
                    results = await self.mcp.execute([(tool_call.function.name, args)])
                    name, sent_args, data, is_error = results[0]
                    ok = bool(data.get('ok')) and not is_error
                    rows = data.get('rows', []) if isinstance(data, dict) else []
                    all_rows.extend(rows)
                    tool_results.append({'name': name, 'arguments': sent_args, 'data': data})
                    error = None
                    if not ok:
                        error = data.get('error', {}).get('message', 'tool failed') if isinstance(data, dict) else 'tool failed'
                        warnings.append(f'{name}: {error}')
                    trace.append(ToolTrace(name, sent_args, ok, len(rows), error))
                    content = json.dumps(data, ensure_ascii=False)
                except Exception as exc:
                    error = f'{type(exc).__name__}: {str(exc)[:200]}'
                    warnings.append(f'{tool_call.function.name} failed or timed out: {error}')
                    trace.append(ToolTrace(tool_call.function.name, args, False, error=error))
                    content = json.dumps({'ok': False, 'error': {'code': 'TOOL_TIMEOUT_OR_FAILURE', 'message': error}})
                messages.append({'role': 'tool', 'tool_call_id': tool_call.id, 'content': content})
        else:
            warnings.append('Maximum tool-call rounds reached; using the data already returned.')

        # Ask the model for the human-facing one-liner only after tool results exist.
        summary_messages = messages + [
            {
                'role': 'user',
                'content': 'Now summarize the returned evidence. Return ONLY the requested JSON object, with a concise one-sentence insight and no invented metrics.',
            }
        ]
        try:
            final = await self._completion(summary_messages, None)
            raw = final.choices[0].message.content or '{}'
            try:
                parsed = AgentJSON.model_validate_json(raw)
            except ValidationError:
                cleaned = raw.strip()
                if cleaned.startswith('```'):
                    cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0]
                parsed = AgentJSON.model_validate(json.loads(cleaned))
        except Exception as exc:
            logger.warning('final LLM summary failed: %s', exc)
            parsed = AgentJSON(
                title='Olist analysis',
                insight='The requested data was retrieved, but the language-model summary was unavailable.',
                warnings=[*warnings, 'Final LLM summary unavailable.'],
            )

        assumptions = list(parsed.assumptions or [])

        # Do not add a full-dataset assumption when the LLM has already
        # resolved a specific year/date range.
        has_resolved_date = any(
            (
                'date range' in assumption.lower()
                or 'full available dataset' in assumption.lower()
                or re.search(r'\b20\d{2}\b', assumption)
                or re.search(r'\b\d{4}-\d{2}-\d{2}\b', assumption)
            )
            for assumption in assumptions
        )

        if not has_resolved_date:
            assumptions.append(
                'No date range was specified, so the full available dataset was used.'
            )


        return AgentResult(
            rows=all_rows,
            tool_results=tool_results,
            insight=parsed.insight,
            chart_type_hint=parsed.chart_type_hint,
            title=parsed.title,
            assumptions=assumptions,
            warnings=[*warnings, *parsed.warnings],
            tool_trace=trace,
        )
