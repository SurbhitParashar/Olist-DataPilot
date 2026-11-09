import asyncio

from agent.fallback_agent import RuleBasedAgent
from app.pipeline import compare_payloads


class RecordingMCP:
    async def execute(self, calls):
        self.calls = calls
        name, args = calls[0]
        return [(name, args, {'ok': True, 'rows': []}, False)]


def test_fallback_applies_electronics_filter_and_valid_arguments():
    agent = RuleBasedAgent('inprocess', 15)
    agent.mcp = RecordingMCP()
    asyncio.run(agent.run('Top 10 review score distribution for electronics'))
    assert agent.mcp.calls == [('review_analysis_tool', {'category': 'electronics'})]


def test_dates_outside_dataset_are_not_silently_ignored():
    assert RuleBasedAgent._params('Revenue in 2025')['date_from'] == '2025-01-01'


def test_refresh_detects_new_categories_with_equal_values():
    old = {'chart_config': {'data': {'labels': ['books'], 'datasets': [{'data': [100]}]}}}
    new = {'chart_config': {'data': {'labels': ['electronics'], 'datasets': [{'data': [100]}]}}}
    assert compare_payloads(old, new)[0]


def test_refresh_detects_added_series_values():
    old = {'chart_config': {'data': {'datasets': [{'data': [100]}]}}}
    new = {'chart_config': {'data': {'datasets': [{'data': [100, 100]}]}}}
    assert compare_payloads(old, new)[0]
