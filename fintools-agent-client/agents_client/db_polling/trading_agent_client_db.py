#!/usr/bin/env python
"""
Trading Agent Client - 数据库模式
"""

import asyncio

from agents_client.db_polling.db_client import TradingAgentClientDB
from agents_client.utils import require_access_token


async def main(agent_url, stock_code, a2a_token, task_id=None):
    print(f"\n{'='*60}")
    print("Trading Agent Client (Database Mode)")
    print(f"{'='*60}")
    print(f"Agent URL: {agent_url}")
    print(f"股票代码: {stock_code}")
    print(f"A2A Token: {a2a_token[:10]}...")
    print("轮询间隔: 30 秒")
    print("心跳超时: 300 秒 (5 分钟)")
    if task_id:
        print(f"恢复任务: {task_id}")
    print(f"{'='*60}\n")

    client = TradingAgentClientDB(agent_url, a2a_token=a2a_token, timeout=180.0)

    if task_id:
        print(f"[Recovery] Checking task: {task_id}")

        try:
            task_status = await client.get_task_status(task_id)
            status = task_status.get("status")

            print(f"[Recovery] Task found, status: {status}")

            if status == "completed":
                print("[Recovery] Task already completed")
                result = task_status
            elif status == "failed":
                print("[Recovery] Task failed")
                result = task_status
            else:
                print("[Recovery] Polling for completion...")
                result = await client.wait_for_task(task_id)

        except Exception as exc:
            error_msg = str(exc)
            if "404" in error_msg or "not found" in error_msg.lower():
                print(f"[Recovery] Error: Task not found - {task_id}")
                result = {"status": "error", "error": f"Task not found: {task_id}"}
            else:
                print(f"[Recovery] Error: {error_msg}")
                result = {"status": "error", "error": error_msg}
    else:
        result = await client.analyze_stock(stock_code)

    print("\n\n最终结果:")
    print(f"  状态: {result.get('status')}")
    if result.get("result"):
        preview = result["result"][:200] + "..." if len(result["result"]) > 200 else result["result"]
        print(f"  结果: {preview}")
    if result.get("error"):
        print(f"  错误: {result['error']}")

    if result.get("status") == "completed":
        print("\n[Reports] Downloading reports...")
        try:
            download_result = await client.download_reports_zip()
            if download_result:
                print(f"[Reports] Downloaded to: {download_result}")
            else:
                print("[Reports] No reports available or download failed")
        except Exception as exc:
            error_msg = str(exc)
            if "410" in error_msg:
                print("[Reports] Server has been shut down. Reports are no longer available.")
            elif "404" in error_msg:
                print("[Reports] No task found. Please submit a task first.")
            else:
                print(f"[Reports] Download failed: {error_msg}")

    return result


if __name__ == "__main__":
    agent_url = "http://127.0.0.1:8000/api/v1/agents/69/a2a/"
    stock_code = "000001"
    task_id = None
    a2a_token = require_access_token()
    asyncio.run(main(agent_url, stock_code, a2a_token, task_id))
