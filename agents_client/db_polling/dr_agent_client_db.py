#!/usr/bin/env python
"""
Deep Research Agent Client - 数据库模式
"""

import asyncio

from agents_client.db_polling.db_client import StockAgentClientDB, load_project_env, run_stock_agent_client
from agents_client.utils import require_access_token

load_project_env(__file__)

DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/82/a2a/"
DEFAULT_STOCK_CODE = "600519"


class DeepResearchAgentClientDB(StockAgentClientDB):
    def __init__(self, agent_url: str = DEFAULT_AGENT_URL, **kwargs):
        super().__init__(agent_url=agent_url, **kwargs)


async def main(
    agent_url: str = DEFAULT_AGENT_URL,
    stock_code: str = DEFAULT_STOCK_CODE,
    a2a_token: str = "",
    task_id: str | None = None,
):
    return await run_stock_agent_client(
        DeepResearchAgentClientDB,
        "Deep Research Agent Client",
        agent_url,
        stock_code,
        a2a_token,
        task_id,
    )


if __name__ == "__main__":
    asyncio.run(main(a2a_token=require_access_token()))
