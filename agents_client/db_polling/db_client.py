"""
A2A Agent Client - 数据库轮询模式
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from agents_client.utils import ReportDownloader, normalize_agent_base_url


def load_project_env(module_file: str) -> None:
    """加载项目根目录 .env。"""
    load_dotenv(Path(module_file).resolve().parents[2] / ".env")


class DatabaseAgentClient:
    """数据库模式 Agent 客户端。"""

    def __init__(
        self,
        agent_url: str,
        *,
        poll_interval: float = 30.0,
        heartbeat_timeout: float = 300.0,
        max_wait: float = 3600.0,
        timeout: float = 180.0,
        a2a_token: str = "",
    ):
        self.agent_url = agent_url.rstrip("/")
        self.task_url = normalize_agent_base_url(self.agent_url)
        self.poll_interval = poll_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_wait = max_wait
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {a2a_token}"} if a2a_token else {}

    @staticmethod
    def _parse_utc_time(iso_time: str | None) -> datetime | None:
        if not iso_time:
            return None
        parsed = datetime.fromisoformat(iso_time)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _age_seconds(self, iso_time: str | None) -> float | None:
        parsed = self._parse_utc_time(iso_time)
        if not parsed:
            return None
        return (datetime.now(timezone.utc) - parsed).total_seconds()

    async def submit_task(self, agent_args: dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agent_url}/api/tasks",
                json={"mode": "db_polling", "agent_args": agent_args},
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

        task_id = data.get("task_id") or data.get("run_id")
        if not task_id:
            raise ValueError("Response missing task_id/run_id")

        print(f"\n{'=' * 60}")
        print("✓ 任务已提交")
        print(f"  Task ID: {task_id}")
        print(f"  Agent: {data.get('agent_name', 'unknown')}")
        print(f"{'=' * 60}\n")
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.task_url}/tasks/{task_id}", headers=self.headers)
            response.raise_for_status()
            return response.json()

    def _print_task_status(self, task: dict[str, Any], poll_count: int) -> None:
        print(f"\n[轮询 #{poll_count}] {datetime.now().strftime('%H:%M:%S')}")
        print(f"  状态: {task.get('status', 'unknown')}")
        if progress := task.get("progress"):
            print(f"  进度: {progress}")
        heartbeat_age = self._age_seconds(task.get("heartbeat_at"))
        if heartbeat_age is not None:
            print(f"  心跳: {heartbeat_age:.0f} 秒前")
        updated_age = self._age_seconds(task.get("updated_at"))
        if updated_age is not None:
            print(f"  更新: {updated_age:.0f} 秒前")

    def _print_final_result(self, task: dict[str, Any]) -> None:
        status = task.get("status")
        result = task.get("result", "")
        error = task.get("error", "")
        artifacts = task.get("artifacts", [])

        print(f"\n{'=' * 60}")
        print("任务最终结果")
        print(f"{'=' * 60}")
        print(f"状态: {status}")
        if completed_at := task.get("completed_at"):
            print(f"完成时间: {completed_at}")

        if status == "completed":
            print("\n✓ 成功")
            if result:
                preview = result[:500] + "..." if len(result) > 500 else result
                print(f"\n结果预览:\n{preview}")
            if artifacts:
                print(f"\n生成的文件 ({len(artifacts)} 个):")
                for artifact in artifacts:
                    print(f"  - {artifact.get('name', 'unknown')} ({artifact.get('size', 0)} bytes)")
        elif status == "failed" and error:
            print(f"\n✗ 失败\n\n错误信息:\n{error}")
        elif status == "timeout":
            print(f"\n⏱ 超时\nServer 可能已挂掉（超过 {self.heartbeat_timeout} 秒无心跳）")

        print(f"\n{'=' * 60}\n")

    async def wait_for_task(self, task_id: str) -> dict[str, Any]:
        waited = 0.0
        poll_count = 0

        while waited < self.max_wait:
            poll_count += 1
            task = await self.get_task_status(task_id)
            self._print_task_status(task, poll_count)

            if task.get("status") in {"completed", "failed"}:
                self._print_final_result(task)
                return task

            heartbeat_age = self._age_seconds(task.get("heartbeat_at"))
            if heartbeat_age is not None and heartbeat_age > self.heartbeat_timeout:
                print(f"\n⚠ 警告: Server 心跳超时 ({heartbeat_age:.0f}s > {self.heartbeat_timeout}s)")
                task["status"] = "timeout"
                task["error"] = f"Server heartbeat timeout: {heartbeat_age:.0f}s"
                self._print_final_result(task)
                return task

            print(f"  等待 {self.poll_interval} 秒后继续轮询...")
            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval

        print(f"\n⚠ 警告: 等待超时 ({self.max_wait} 秒)")
        task = await self.get_task_status(task_id)
        task["status"] = "timeout"
        task["error"] = f"Max wait time exceeded: {self.max_wait}s"
        self._print_final_result(task)
        return task

    async def execute(self, agent_args: dict[str, Any]) -> dict[str, Any]:
        return await self.wait_for_task(await self.submit_task(agent_args))


class StockAgentClientDB(DatabaseAgentClient):
    """面向 `stock_code` 参数的通用 DB 客户端。"""

    def __init__(self, agent_url: str, **kwargs):
        super().__init__(agent_url, **kwargs)
        self.report_downloader = ReportDownloader(
            agent_url=normalize_agent_base_url(agent_url),
            a2a_token=kwargs.get("a2a_token"),
            timeout=60.0,
            reports_path="reports",
            reports_zip_path="reports/zip",
        )

    async def analyze_stock(self, stock_code: str, download_reports: bool = True) -> dict[str, Any]:
        result = await self.execute({"stock_code": stock_code})
        if download_reports and result.get("status") == "completed":
            if downloaded_file := await self.download_reports_zip():
                result["downloaded_file"] = downloaded_file
        return result

    async def download_reports_zip(self, output_dir: str = "downloaded_reports") -> str | None:
        return await self.report_downloader.download_zip(output_dir)


async def run_stock_agent_client(
    client_cls: type[StockAgentClientDB],
    title: str,
    agent_url: str,
    stock_code: str,
    a2a_token: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    print(f"\n{'=' * 60}")
    print(f"{title} (Database Mode)")
    print(f"{'=' * 60}")
    print(f"Agent URL: {agent_url}")
    print(f"股票代码: {stock_code}")
    print(f"A2A Token: {a2a_token[:10]}...")
    print("轮询间隔: 30 秒")
    print("心跳超时: 300 秒 (5 分钟)")
    if task_id:
        print(f"恢复任务: {task_id}")
    print(f"{'=' * 60}\n")

    client = client_cls(agent_url=agent_url, a2a_token=a2a_token, timeout=180.0)

    if task_id:
        result = await recover_task(client, task_id)
    else:
        result = await client.analyze_stock(stock_code, download_reports=False)

    print("\n\n最终结果:")
    print(f"  状态: {result.get('status')}")
    if result.get("result"):
        preview = result["result"][:200] + "..." if len(result["result"]) > 200 else result["result"]
        print(f"  结果: {preview}")
    if result.get("error"):
        print(f"  错误: {result['error']}")

    if result.get("status") == "completed":
        await print_report_download_result(client)

    return result


async def recover_task(client: DatabaseAgentClient, task_id: str) -> dict[str, Any]:
    print(f"[Recovery] Checking task: {task_id}")
    try:
        task_status = await client.get_task_status(task_id)
    except Exception as exc:
        error_msg = str(exc)
        if "404" in error_msg or "not found" in error_msg.lower():
            print(f"[Recovery] Error: Task not found - {task_id}")
            return {"status": "error", "error": f"Task not found: {task_id}"}
        print(f"[Recovery] Error: {error_msg}")
        return {"status": "error", "error": error_msg}

    status = task_status.get("status")
    print(f"[Recovery] Task found, status: {status}")
    if status == "completed":
        print("[Recovery] Task already completed")
        return task_status
    if status == "failed":
        print("[Recovery] Task failed")
        return task_status

    print("[Recovery] Polling for completion...")
    return await client.wait_for_task(task_id)


async def print_report_download_result(client: StockAgentClientDB) -> None:
    print("\n[Reports] Downloading reports...")
    try:
        download_result = await client.download_reports_zip()
    except Exception as exc:
        error_msg = str(exc)
        if "410" in error_msg:
            print("[Reports] Server has been shut down. Reports are no longer available.")
        elif "404" in error_msg:
            print("[Reports] No task found. Please submit a task first.")
        else:
            print(f"[Reports] Download failed: {error_msg}")
        return

    if download_result:
        print(f"[Reports] Downloaded to: {download_result}")
    else:
        print("[Reports] No reports available or download failed")
