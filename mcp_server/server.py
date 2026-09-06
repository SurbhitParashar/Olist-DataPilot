from mcp.server import MCPServer

from mcp_server.db import ensure_dataset
from mcp_server.tools import (
    category_performance,
    delivery_performance,
    order_trends,
    payment_breakdown,
    review_analysis,
    seller_performance,
)

mcp = MCPServer(
    'olist-sales-analytics',
    instructions=(
        'Use these tools to answer e-commerce analytics questions over the Olist dataset. '
        'Always preserve the English product category translation. Tools return structured JSON-style dictionaries and handle failures safely.'
    ),
)


@mcp.tool(title='Order trends')
def order_trends_tool(date_from: str | None = None, date_to: str | None = None, metric: str = 'revenue') -> dict:
    return order_trends(date_from, date_to, metric)


@mcp.tool(title='Product category performance')
def category_performance_tool(date_from: str | None = None, date_to: str | None = None, limit: int = 20, sort: str = 'desc', category: str | None = None) -> dict:
    return category_performance(date_from, date_to, limit, sort, category)


@mcp.tool(title='Seller performance')
def seller_performance_tool(date_from: str | None = None, date_to: str | None = None, state: str | None = None, limit: int = 20, sort: str = 'desc') -> dict:
    return seller_performance(date_from, date_to, state, limit, sort)


@mcp.tool(title='Customer review analysis')
def review_analysis_tool(date_from: str | None = None, date_to: str | None = None, category: str | None = None, state: str | None = None, group_by: str = 'score') -> dict:
    return review_analysis(date_from, date_to, category, state, group_by)


@mcp.tool(title='Payment breakdown')
def payment_breakdown_tool(date_from: str | None = None, date_to: str | None = None, payment_types: list[str] | None = None) -> dict:
    return payment_breakdown(date_from, date_to, payment_types)


@mcp.tool(title='Delivery performance')
def delivery_performance_tool(date_from: str | None = None, date_to: str | None = None, state: str | None = None, route: bool = False) -> dict:
    return delivery_performance(date_from, date_to, state, route)


if __name__ == '__main__':
    ensure_dataset()
    mcp.run(transport='streamable-http', host='0.0.0.0', port=8000)
