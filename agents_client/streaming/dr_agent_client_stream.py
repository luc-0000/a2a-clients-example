"""
Deep Research Agent Client (streaming-style)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from agents_client.streaming.base_client import (
    StreamingAgentClient,
    load_project_env,
    run_stock_agent_stream,
)
from agents_client.utils import require_access_token

load_project_env(__file__)

DEFAULT_STOCK_CODE = "600519"
DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/82/a2a/"
DEFAULT_REPORTS_DIR = str(Path(__file__).resolve().parent / "downloaded_reports")


async def main(
    stock_code: str,
    agent_url: str,
    a2a_token: str,
    report_output_dir: str | None = None,
):
    client = StreamingAgentClient(agent_url, a2a_token=a2a_token)
    return await run_stock_agent_stream(
        client,
        "Deep Research Agent Client",
        stock_code,
        report_output_dir=report_output_dir or DEFAULT_REPORTS_DIR,
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    stock_code = args[0] if args else DEFAULT_STOCK_CODE
    agent_url = args[1] if len(args) > 1 else DEFAULT_AGENT_URL
    report_output_dir = args[2] if len(args) > 2 else None
    asyncio.run(main(stock_code, agent_url, require_access_token(), report_output_dir))
