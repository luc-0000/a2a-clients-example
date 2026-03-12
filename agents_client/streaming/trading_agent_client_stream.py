"""
Trading Agent Client
"""

import asyncio
import sys

from agents_client.streaming.base_client import StreamingStockAgentClient, load_project_env, run_stock_agent_client
from agents_client.utils import require_access_token

load_project_env(__file__)

DEFAULT_STOCK_CODE = "600519"
DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/69/a2a/"


class TradingAgentClientStream(StreamingStockAgentClient):
    def __init__(self, agent_url: str = DEFAULT_AGENT_URL, a2a_token: str | None = None):
        super().__init__(agent_url=agent_url, a2a_token=a2a_token, user_message="test request")


async def run_trading_agent(stock_code: str, agent_url: str, a2a_token: str | None = None) -> bool:
    return await run_stock_agent_client(TradingAgentClientStream, "Trading Agent", stock_code, agent_url, a2a_token)


if __name__ == "__main__":
    args = sys.argv[1:]
    stock_code = args[0] if args else DEFAULT_STOCK_CODE
    agent_url = args[1] if len(args) > 1 else DEFAULT_AGENT_URL
    asyncio.run(run_trading_agent(stock_code, agent_url, require_access_token()))
