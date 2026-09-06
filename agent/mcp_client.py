from __future__ import annotations

import json
from typing import Any

from mcp import Client


class MCPAnalyticsClient:
    def __init__(self, url: str, timeout_seconds: float = 15.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def execute(self, calls: list[tuple[str, dict[str, Any]]]):
        results = []
        async with Client(self.url) as client:
            for name, args in calls:
                result = await client.call_tool(name, args, read_timeout_seconds=self.timeout_seconds)
                data = result.structured_content
                if data is None:
                    texts = []
                    for block in result.content:
                        text = getattr(block, 'text', None)
                        if text:
                            texts.append(text)
                    try:
                        data = json.loads('\n'.join(texts))
                    except Exception:
                        data = {'ok': False, 'error': {'code': 'MCP_RESPONSE', 'message': '\n'.join(texts)}}
                results.append((name, args, data, bool(result.is_error)))
        return results
