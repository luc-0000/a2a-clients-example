#!/usr/bin/env python
"""
Deep Research Agent Client - 数据库模式
"""

import asyncio
from pathlib import Path
import sys

from agents_client.db_polling.db_client import StockAgentClientDB, load_project_env, run_stock_agent_client
from agents_client.utils import require_access_token

load_project_env(__file__)

DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/82/a2a/"
DEFAULT_STOCK_CODE = "600519"
DEFAULT_REPORTS_DIR = str(Path(__file__).resolve().parent / "downloaded_reports")


class DeepResearchAgentClientDB(StockAgentClientDB):
    def __init__(self, agent_url: str = DEFAULT_AGENT_URL, **kwargs):
        super().__init__(agent_url=agent_url, default_reports_dir=DEFAULT_REPORTS_DIR, **kwargs)


async def main(
    agent_url: str = DEFAULT_AGENT_URL,
    stock_code: str = DEFAULT_STOCK_CODE,
    a2a_token: str = "",
    task_id: str | None = None,
    report_output_dir: str | None = None,
):
    return await run_stock_agent_client(
        DeepResearchAgentClientDB,
        "Deep Research Agent Client",
        agent_url,
        stock_code,
        a2a_token,
        task_id,
        report_output_dir,
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    stock_code = args[0] if args else DEFAULT_STOCK_CODE
    agent_url = args[1] if len(args) > 1 else DEFAULT_AGENT_URL
    report_output_dir = args[2] if len(args) > 2 else None
    task_id = args[3] if len(args) > 3 else None
    asyncio.run(main(agent_url, stock_code, require_access_token(), task_id, report_output_dir))
