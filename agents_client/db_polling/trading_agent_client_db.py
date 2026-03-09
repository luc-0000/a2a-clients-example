#!/usr/bin/env python
"""
Trading Agent Client - 数据库模式

使用方法：
    python -m a2a_services.agents_client.trading_agent_client_db

或者：
    from a2a_services.agents_client.trading_agent_client_db import TradingAgentClientDB
    
    client = TradingAgentClientDB()
    result = await client.analyze_stock("AAPL")
"""

import asyncio
import logging
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv

from agents_client.db_polling.db_client import TradingAgentClientDB

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 命令行入口 ====================

async def main(agent_url, stock_code, a2a_token, task_id=None):
    """
    测试 Trading Agent Client
    
    Args:
        agent_url: Agent Server URL
        stock_code: 股票代码
        a2a_token: A2A 认证 token
        task_id: 已有任务 ID（可选）。如果提供，只轮询该任务，不创建新任务
    """
    
    print(f"\n{'='*60}")
    print(f"Trading Agent Client (Database Mode)")
    print(f"{'='*60}")
    print(f"Agent URL: {agent_url}")
    print(f"股票代码: {stock_code}")
    print(f"A2A Token: {a2a_token[:10]}...")
    print(f"轮询间隔: 30 秒")
    print(f"心跳超时: 300 秒 (5 分钟)")
    if task_id:
        print(f"恢复任务: {task_id}")
    print(f"{'='*60}\n")
    
    # 初始化 client
    client = TradingAgentClientDB(agent_url, a2a_token=a2a_token, timeout=180.0)
    
    if task_id:
        # 恢复模式：只轮询已有任务
        print(f"[Recovery] Checking task: {task_id}")
        
        try:
            # 查询任务状态
            task_status = await client.get_task_status(task_id)
            status = task_status.get("status")
            
            print(f"[Recovery] Task found, status: {status}")
            
            if status == "completed":
                print(f"[Recovery] Task already completed")
                result = task_status
            elif status == "failed":
                print(f"[Recovery] Task failed")
                result = task_status
            else:
                # 轮询等待完成
                print(f"[Recovery] Polling for completion...")
                result = await client.wait_for_task(task_id)
                
        except Exception as e:
            # 任务不存在或其他错误
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                print(f"[Recovery] Error: Task not found - {task_id}")
                result = {"status": "error", "error": f"Task not found: {task_id}"}
            else:
                print(f"[Recovery] Error: {error_msg}")
                result = {"status": "error", "error": error_msg}
    else:
        # 正常模式：创建新任务
        result = await client.analyze_stock(stock_code)
    
    print(f"\n\n最终结果:")
    print(f"  状态: {result.get('status')}")
    if result.get("result"):
        preview = result['result'][:200] + "..." if len(result['result']) > 200 else result['result']
        print(f"  结果: {preview}")
    if result.get("error"):
        print(f"  错误: {result['error']}")
    
    # 如果任务完成，尝试下载报告
    if result.get("status") == "completed":
        print(f"\n[Reports] Downloading reports...")
        try:
            download_result = await client.download_reports_zip()
            if download_result:
                print(f"[Reports] Downloaded to: {download_result}")
            else:
                print(f"[Reports] No reports available or download failed")
        except Exception as e:
            error_msg = str(e)
            if "410" in error_msg:
                print(f"[Reports] Server has been shut down. Reports are no longer available.")
            elif "404" in error_msg:
                print(f"[Reports] No task found. Please submit a task first.")
            else:
                print(f"[Reports] Download failed: {error_msg}")
    
    return result


if __name__ == "__main__":
    import os

    # agent_url = 'http://localhost:9999'  # 本地测试
    agent_url = 'http://127.0.0.1:8000/api/v1/agents/69/a2a/'  # 云端模式

    stock_code = '000001'
    
    # 恢复模式：提供已有的 task_id，只轮询不创建新任务
    task_id = None

    # 从 .env 读取 token
    a2a_token = os.getenv('FINTOOLS_ACCESS_TOKEN', '')

    if not a2a_token:
        raise ValueError("FINTOOLS_ACCESS_TOKEN not found in .env")

    asyncio.run(main(agent_url, stock_code, a2a_token, task_id))
