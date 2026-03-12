"""
Deep Research Agent Client
"""

import asyncio
import sys

from agents_client.streaming.base_client import StreamingStockAgentClient, load_project_env, run_stock_agent_client
from agents_client.utils import require_access_token

load_project_env(__file__)

DEFAULT_STOCK_CODE = "600519"
# DEFAULT_AGENT_URL = "http://localhost:9999"
DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/82/a2a/"


class DeepResearchAgentClientStream(StreamingStockAgentClient):
    def __init__(self, agent_url: str = DEFAULT_AGENT_URL, a2a_token: str | None = None):
        super().__init__(agent_url=agent_url, a2a_token=a2a_token, user_message="分析股票 {stock_code}")


async def run_dr_agent(stock_code: str, agent_url: str, a2a_token: str | None = None) -> bool:
    return await run_stock_agent_client(DeepResearchAgentClientStream, "Deep Research Agent", stock_code, agent_url, a2a_token)


if __name__ == "__main__":
    args = sys.argv[1:]
    stock_code = args[0] if args else DEFAULT_STOCK_CODE
    asyncio.run(run_dr_agent(stock_code, DEFAULT_AGENT_URL, require_access_token()))
