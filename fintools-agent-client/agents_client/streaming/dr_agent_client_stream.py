"""
Deep Research Agent Client
"""

import asyncio
import sys

from agents_client.streaming.base_client import A2AAgentClient
from agents_client.utils import ReportDownloader, require_access_token


DEFAULT_STOCK_CODE = "600519"
DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/82/a2a/"


async def run_dr_agent(stock_code: str, agent_url: str, a2a_token: str = None) -> bool:
    print(f"\n{'='*60}")
    print("运行 Deep Research Agent, May take ~30~60s to start remote server!")
    print(f"{'='*60}")
    print(f"股票代码: {stock_code}")
    print(f"Agent地址: {agent_url}")
    print(f"{'='*60}\n")

    async with A2AAgentClient(agent_url, a2a_token) as client:
        result = await client.send_message_streaming(
            user_message=f"分析股票 {stock_code}",
            agent_args={"stock_code": stock_code},
        )

        print(f"\n{'='*60}")
        print(f"执行完成！共处理 {result['event_count']} 个事件")
        print(f"{'='*60}\n")

        return result["success"]


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    args = sys.argv[1:]
    stock_code = args[0] if args else DEFAULT_STOCK_CODE
    a2a_token = require_access_token()
    agent_url = DEFAULT_AGENT_URL
    print(f"后端模式: {agent_url}")

    asyncio.run(run_dr_agent(stock_code, agent_url, a2a_token))
    manager = ReportDownloader(agent_url, a2a_token)
    asyncio.run(manager.show_reports())
    asyncio.run(manager.download_zip())
