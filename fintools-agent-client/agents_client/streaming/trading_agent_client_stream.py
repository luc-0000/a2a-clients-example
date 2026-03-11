"""
Trading Agent Client
"""

import asyncio
import sys

from agents_client.streaming.base_client import A2AAgentClient
from agents_client.utils import ReportDownloader, normalize_agent_base_url, require_access_token


DEFAULT_STOCK_CODE = "600519"
DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/69/a2a/"


async def run_trading_agent(stock_code: str, agent_url: str, a2a_token: str = None) -> bool:
    print(f"\n{'='*60}")
    print("运行 Trading Agent, May take 30-60s to start server...")
    print(f"{'='*60}")
    print(f"股票代码: {stock_code}")
    print(f"Agent地址: {agent_url}")
    print(f"{'='*60}\n")

    async with A2AAgentClient(agent_url, a2a_token) as client:
        result = await client.send_message_streaming(
            user_message="test request",
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
    agent_url = args[1] if len(args) > 1 else DEFAULT_AGENT_URL
    a2a_token = require_access_token()

    print(f"后端模式: {agent_url}")
    asyncio.run(run_trading_agent(stock_code, agent_url, a2a_token))

    report_base_url = normalize_agent_base_url(agent_url)
    manager = ReportDownloader(
        report_base_url,
        a2a_token,
        reports_path="reports",
        reports_zip_path="reports/zip",
    )
    asyncio.run(manager.show_reports())
    asyncio.run(manager.download_zip())
