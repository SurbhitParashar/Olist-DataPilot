import asyncio
from mcp import Client

async def main():
    async with Client('http://127.0.0.1:8000/mcp') as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}
        required = {'order_trends_tool', 'category_performance_tool', 'seller_performance_tool', 'review_analysis_tool', 'payment_breakdown_tool', 'delivery_performance_tool'}
        if not required.issubset(names):
            raise SystemExit(1)

if __name__ == '__main__':
    asyncio.run(main())
