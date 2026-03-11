"""
A2A Agent Client - 数据库模式
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from agents_client.utils import ReportDownloader, normalize_agent_base_url

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)


class DatabaseAgentClient:
    """数据库模式 Agent 客户端"""

    def __init__(
        self,
        agent_url: str,
        poll_interval: float = 30.0,
        heartbeat_timeout: float = 300.0,
        max_wait: float = 3600.0,
        timeout: float = 30.0,
        a2a_token: str = "",
    ):
        self.agent_url = agent_url.rstrip("/")
        self.poll_interval = poll_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_wait = max_wait
        self.timeout = timeout
        self.headers = {}
        if a2a_token:
            self.headers["Authorization"] = f"Bearer {a2a_token}"
        self.task_url = normalize_agent_base_url(self.agent_url)

    @staticmethod
    def _parse_utc_time(iso_time: str | None) -> datetime | None:
        if not iso_time:
            return None
        parsed = datetime.fromisoformat(iso_time)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _age_seconds(self, iso_time: str | None) -> float | None:
        parsed = self._parse_utc_time(iso_time)
        if not parsed:
            return None
        return (datetime.now(timezone.utc) - parsed).total_seconds()

    async def submit_task(self, agent_args: dict) -> str:
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

            print(f"\n{'='*60}")
            print("任务已提交")
            print(f"  Task ID: {task_id}")
            print(f"  Agent: {data.get('agent_name', 'unknown')}")
            print(f"{'='*60}\n")
            return task_id

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.task_url}/tasks/{task_id}", headers=self.headers)
            response.raise_for_status()
            return response.json()

    def _print_task_status(self, task: Dict[str, Any], poll_count: int):
        status = task.get("status", "unknown")
        progress = task.get("progress", "")
        heartbeat_age = self._age_seconds(task.get("heartbeat_at"))
        updated_age = self._age_seconds(task.get("updated_at"))

        print(f"\n[轮询 #{poll_count}] {datetime.now().strftime('%H:%M:%S')}")
        print(f"  状态: {status}")
        if progress:
            print(f"  进度: {progress}")
        if heartbeat_age is not None:
            print(f"  心跳: {heartbeat_age:.0f} 秒前")
        if updated_age is not None:
            print(f"  更新: {updated_age:.0f} 秒前")

    def _print_final_result(self, task: Dict[str, Any]):
        status = task.get("status")
        result = task.get("result", "")
        error = task.get("error", "")
        artifacts = task.get("artifacts", [])
        completed_at = task.get("completed_at")

        print(f"\n{'='*60}")
        print("任务最终结果")
        print(f"{'='*60}")
        print(f"状态: {status}")

        if completed_at:
            print(f"完成时间: {completed_at}")

        if status == "completed":
            print("\n成功")
            if result:
                print("\n结果预览:")
                preview = result[:500] + "..." if len(result) > 500 else result
                print(preview)
            if artifacts:
                print(f"\n生成的文件 ({len(artifacts)} 个):")
                for artifact in artifacts:
                    name = artifact.get("name", "unknown")
                    size = artifact.get("size", 0)
                    print(f"  - {name} ({size} bytes)")
        elif status == "failed":
            print("\n失败")
            if error:
                print("\n错误信息:")
                print(error)
        elif status == "timeout":
            print("\n超时")
            print(f"Server 可能已挂掉（超过 {self.heartbeat_timeout} 秒无心跳）")

        print(f"\n{'='*60}\n")

    async def wait_for_task(self, task_id: str) -> Dict[str, Any]:
        waited = 0.0
        poll_count = 0

        while waited < self.max_wait:
            poll_count += 1
            task = await self.get_task_status(task_id)
            status = task.get("status")
            self._print_task_status(task, poll_count)

            if status in {"completed", "failed"}:
                self._print_final_result(task)
                return task

            heartbeat_age = self._age_seconds(task.get("heartbeat_at"))
            if heartbeat_age is not None and heartbeat_age > self.heartbeat_timeout:
                print(f"\n警告: Server 心跳超时 ({heartbeat_age:.0f}s > {self.heartbeat_timeout}s)")
                task["status"] = "timeout"
                task["error"] = f"Server heartbeat timeout: {heartbeat_age:.0f}s"
                self._print_final_result(task)
                return task

            print(f"  等待 {self.poll_interval} 秒后继续轮询...")
            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval

        print(f"\n警告: 等待超时 ({self.max_wait} 秒)")
        task = await self.get_task_status(task_id)
        task["status"] = "timeout"
        task["error"] = f"Max wait time exceeded: {self.max_wait}s"
        self._print_final_result(task)
        return task

    async def execute(self, agent_args: dict) -> Dict[str, Any]:
        task_id = await self.submit_task(agent_args)
        return await self.wait_for_task(task_id)


class TradingAgentClientDB(DatabaseAgentClient):
    """Trading Agent Client（数据库模式）"""

    def __init__(
        self,
        agent_url: str = "http://localhost:9999",
        poll_interval: float = 30.0,
        heartbeat_timeout: float = 300.0,
        max_wait: float = 3600.0,
        timeout: float = 180.0,
        a2a_token: str = "",
    ):
        super().__init__(
            agent_url=agent_url,
            poll_interval=poll_interval,
            heartbeat_timeout=heartbeat_timeout,
            max_wait=max_wait,
            timeout=timeout,
            a2a_token=a2a_token,
        )

        report_base_url = normalize_agent_base_url(agent_url)
        self.report_downloader = ReportDownloader(
            agent_url=report_base_url,
            a2a_token=a2a_token,
            timeout=60.0,
            reports_path="reports",
            reports_zip_path="reports/zip",
        )

    async def analyze_stock(self, stock_code: str, download_reports: bool = True):
        agent_args = {"stock_code": stock_code}
        logger.info("[TradingAgent] Analyzing %s", stock_code)
        result = await self.execute(agent_args)

        if download_reports and result.get("status") == "completed":
            logger.info("[TradingAgent] Task completed, downloading reports...")
            download_result = await self.download_reports_zip()
            if download_result:
                result["downloaded_file"] = download_result
                logger.info("[TradingAgent] Reports downloaded: %s", download_result)
            else:
                logger.warning("[TradingAgent] Failed to download reports")

        return result

    async def download_reports_zip(self, output_dir: str = "downloaded_reports") -> str | None:
        return await self.report_downloader.download_zip(output_dir)
