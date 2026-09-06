from __future__ import annotations

import re

from agent.interfaces import AgentResult, ToolTrace
from agent.mcp_client import MCPAnalyticsClient


class RuleBasedAgent:
    """Deterministic safety net: pick one analytics tool using keywords and always use a bar chart downstream."""

    def __init__(self, mcp_url: str, tool_timeout: float):
        self.mcp = MCPAnalyticsClient(mcp_url, tool_timeout)

    @staticmethod
    def _params(query: str) -> dict:
        q = query.lower()
        args: dict = {}
        if 'last year' in q:
            args.update(date_from='2017-01-01', date_to='2017-12-31')
        elif 'first half of 2017' in q:
            args.update(date_from='2017-01-01', date_to='2017-06-30')
        else:
            years = re.findall(r'\b(2016|2017|2018)\b', q)
            if years:
                y = years[0]
                args.update(date_from=f'{y}-01-01', date_to=f'{y}-12-31')
        top = re.search(r'top\s+(\d+)', q)
        if top:
            args['limit'] = min(int(top.group(1)), 100)
        if 'worst rated' in q:
            args['sort'] = 'asc'
        state_map = {'são paulo': 'SP', 'sao paulo': 'SP', 'rio de janeiro': 'RJ', 'minas gerais': 'MG', 'bahia': 'BA'}
        for name, code in state_map.items():
            if name in q:
                args['state'] = code
                break
        return args

    @staticmethod
    def _choose(query: str) -> str:
        q = query.lower()
        if any(k in q for k in ('payment', 'boleto', 'credit card', 'installment')):
            return 'payment_breakdown_tool'
        if any(k in q for k in ('review', 'star', 'rating', 'rated')):
            return 'review_analysis_tool' if 'distribution' in q or 'electronics' in q else 'seller_performance_tool'
        if any(k in q for k in ('delivery', 'on-time', 'delay', 'route')):
            return 'delivery_performance_tool'
        if any(k in q for k in ('seller', 'sellers')):
            return 'seller_performance_tool'
        if any(k in q for k in ('category', 'categories', 'product')):
            return 'category_performance_tool'
        return 'order_trends_tool'

    async def run(self, query: str) -> AgentResult:
        name = self._choose(query)
        args = self._params(query)
        result = (await self.mcp.execute([(name, args)]))[0]
        _, sent_args, data, is_error = result
        rows = data.get('rows', []) if isinstance(data, dict) else []
        warning = []
        if is_error or not data.get('ok'):
            warning.append(data.get('error', {}).get('message', 'Tool failed safely'))
        assumptions = []
        if not any(x in query.lower() for x in ('2016', '2017', '2018', 'last year', 'first half')):
            assumptions.append('No date range was specified, so the full available dataset was used.')
        if not rows and not warning:
            warning.append('The filter returned no matching rows.')
        return AgentResult(
            rows=rows,
            tool_results=[{'name': name, 'arguments': sent_args, 'data': data}],
            title='Rule-based Olist analysis',
            insight='Results were produced with the deterministic fallback agent; the chart type is intentionally fixed to a bar chart.',
            chart_type_hint='bar',
            assumptions=assumptions,
            warnings=warning,
            tool_trace=[ToolTrace(name, sent_args, not is_error and bool(data.get('ok')), len(rows), warning[0] if warning else None)],
        )
