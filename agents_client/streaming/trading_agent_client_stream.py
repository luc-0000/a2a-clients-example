"""
Trading Agent Client

专门用于 Trading Agent 的客户端
"""

import asyncio
import sys
from agents_client.streaming.base_client import A2AAgentClient
from agents_client.utils import ReportDownloader


# ========================================
# Trading Agent 特有配置
# ========================================

DEFAULT_STOCK_CODE = "600519"
# DEFAULT_AGENT_URL = "http://localhost:9999"
# DEFAULT_AGENT_URL = "http://8.153.13.5:8000/api/v1/agents/69/a2a/"
DEFAULT_AGENT_URL = "http://127.0.0.1:8000/api/v1/agents/69/a2a/"


# ========================================
# 运行 Agent
# ========================================
async def run_trading_agent(stock_code: str, agent_url: str, a2a_token: str = None) -> bool:
    """
    运行 Trading Agent

    Args:
        stock_code: 股票代码
        agent_url: Agent URL
        a2a_token: A2A Token

    Returns:
        是否成功
    """
    print(f"\n{'='*60}")
    print(f"运行 Trading Agent, May take 30-60s to start server...")
    print(f"{'='*60}")
    print(f"股票代码: {stock_code}")
    print(f"Agent地址: {agent_url}")
    print(f"{'='*60}\n")

    async with A2AAgentClient(agent_url, a2a_token) as client:
        result = await client.send_message_streaming(
            user_message="test request",  # Trading Agent 特有消息
            agent_args={"stock_code": stock_code}
        )

        print(f"\n{'='*60}")
        print(f"执行完成！共处理 {result['event_count']} 个事件")
        print(f"{'='*60}\n")

        return result["success"]


# ========================================
# 命令行接口
# ========================================

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # 解析命令行参数
    args = sys.argv[1:]
    stock_code = args[0] if args else DEFAULT_STOCK_CODE
    agent_url = args[1] if len(args) > 1 else DEFAULT_AGENT_URL

    # 后端模式：需要 token
    a2a_token = os.getenv("FINTOOLS_ACCESS_TOKEN")
    if not a2a_token:
        print("❌ 错误: 未设置 FINTOOLS_ACCESS_TOKEN 环境变量")
        print("\n请在 .env 文件中设置:")
        print("  FINTOOLS_ACCESS_TOKEN=your-token-here")
        print("\n或通过命令行设置:")
        print("  export FINTOOLS_ACCESS_TOKEN=your-token-here")
        sys.exit(1)

    print(f"🔗 后端模式: {agent_url}")

    # 运行 + 显示 + 下载
    success = asyncio.run(run_trading_agent(stock_code, agent_url, a2a_token))
    
    # 报告下载器（streaming 模式通过 Backend 时需要正确的路径）
    # 从 agent_url 提取 base URL（去掉 /a2a/ 部分）
    report_base_url = agent_url.rstrip("/")
    if report_base_url.endswith("/a2a"):
        report_base_url = report_base_url[:-4]
    
    manager = ReportDownloader(
        report_base_url,
        a2a_token,
        reports_path="reports",
        reports_zip_path="reports/zip"
    )
    asyncio.run(manager.show_reports())
    asyncio.run(manager.download_zip())
