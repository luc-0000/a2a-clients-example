"""
A2A Agent Client - 数据库模式

与 streaming 模式独立的实现：
- 提交任务后立即返回 task_id
- 轮询数据库获取状态
- 检测 Server 是否挂掉（心跳超时）
- 打印每次轮询的状态和最终结果
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

import httpx

from agents_client.utils import ReportDownloader, normalize_agent_base_url

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseAgentClient:
    """数据库模式 Agent 客户端
    
    使用两个 URL：
    - agent_url: 用于创建任务（POST /a2a/api/tasks）
    - task_url: 用于查询状态（GET /tasks/{task_id}）
    """
    
    def __init__(
        self,
        agent_url: str,
        poll_interval: float = 30.0,      # 轮询间隔（秒）
        heartbeat_timeout: float = 300.0,  # 心跳超时（秒）- 5分钟
        max_wait: float = 3600.0,         # 最大等待时间（秒）
        timeout: float = 30.0,            # HTTP 请求超时
        a2a_token: str = "",              # A2A 认证 token
    ):
        self.agent_url = agent_url.rstrip("/")
        self.poll_interval = poll_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_wait = max_wait
        self.timeout = timeout
        
        # 构建 headers
        self.headers = {}
        if a2a_token:
            self.headers["Authorization"] = f"Bearer {a2a_token}"
        
        # 从 agent_url 提取 task_url（去掉 /a2a/ 部分）
        # agent_url: http://xxx/api/v1/agents/69/a2a/
        # task_url:  http://xxx/api/v1/agents/69/
        self.task_url = normalize_agent_base_url(self.agent_url)

    @staticmethod
    def _parse_utc_time(iso_time: str | None) -> datetime | None:
        """解析 ISO 时间，若无时区则按 UTC 处理。"""
        if not iso_time:
            return None
        parsed = datetime.fromisoformat(iso_time)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _age_seconds(self, iso_time: str | None) -> float | None:
        """返回给定时间距当前 UTC 的秒数。"""
        parsed = self._parse_utc_time(iso_time)
        if not parsed:
            return None
        return (datetime.now(timezone.utc) - parsed).total_seconds()
        
    async def submit_task(self, agent_args: dict) -> str:
        """提交任务，返回 task_id
        
        Args:
            agent_args: Agent 参数
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agent_url}/api/tasks",
                json={"mode": "db_polling", "agent_args": agent_args},
                headers=self.headers
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 兼容 run_id 和 task_id
            task_id = data.get("task_id") or data.get("run_id")
            if not task_id:
                raise ValueError("Response missing task_id/run_id")
            
            print(f"\n{'='*60}")
            print(f"✓ 任务已提交")
            print(f"  Task ID: {task_id}")
            print(f"  Agent: {data.get('agent_name', 'unknown')}")
            print(f"{'='*60}\n")
            
            return task_id
            
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态（使用独立的 task endpoint）"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.task_url}/tasks/{task_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
            
    def _print_task_status(self, task: Dict[str, Any], poll_count: int):
        """打印任务状态"""
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
        """打印最终结果"""
        status = task.get("status")
        result = task.get("result", "")
        error = task.get("error", "")
        artifacts = task.get("artifacts", [])
        completed_at = task.get("completed_at")
        
        print(f"\n{'='*60}")
        print(f"任务最终结果")
        print(f"{'='*60}")
        print(f"状态: {status}")
        
        if completed_at:
            print(f"完成时间: {completed_at}")
            
        if status == "completed":
            print(f"\n✓ 成功")
            if result:
                print(f"\n结果预览:")
                # 只显示前 500 字符
                preview = result[:500] + "..." if len(result) > 500 else result
                print(f"{preview}")
                
            if artifacts:
                print(f"\n生成的文件 ({len(artifacts)} 个):")
                for artifact in artifacts:
                    name = artifact.get("name", "unknown")
                    size = artifact.get("size", 0)
                    print(f"  - {name} ({size} bytes)")
                    
        elif status == "failed":
            print(f"\n✗ 失败")
            if error:
                print(f"\n错误信息:")
                print(f"{error}")
                
        elif status == "timeout":
            print(f"\n⏱ 超时")
            print(f"Server 可能已挂掉（超过 {self.heartbeat_timeout} 秒无心跳）")
            
        print(f"\n{'='*60}\n")
        
    async def wait_for_task(self, task_id: str) -> Dict[str, Any]:
        """
        等待任务完成
        
        Returns:
            任务详情（包含 status, result, error 等）
        """
        waited = 0.0
        poll_count = 0
        
        while waited < self.max_wait:
            poll_count += 1
            
            # 查询状态
            task = await self.get_task_status(task_id)
            status = task.get("status")
            
            # 打印状态
            self._print_task_status(task, poll_count)
            
            # 检查是否完成
            if status in {"completed", "failed"}:
                self._print_final_result(task)
                return task
            
            # 检查心跳超时（Server 可能挂了）
            # 但只在任务未完成时才检查心跳
            heartbeat_age = self._age_seconds(task.get("heartbeat_at"))
            if heartbeat_age is not None:
                if heartbeat_age > self.heartbeat_timeout:
                    print(f"\n⚠ 警告: Server 心跳超时 ({heartbeat_age:.0f}s > {self.heartbeat_timeout}s)")
                    task["status"] = "timeout"
                    task["error"] = f"Server heartbeat timeout: {heartbeat_age:.0f}s"
                    self._print_final_result(task)
                    return task
            
            # 等待下次轮询
            print(f"  等待 {self.poll_interval} 秒后继续轮询...")
            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval
            
        # 超时
        print(f"\n⚠ 警告: 等待超时 ({self.max_wait} 秒)")
        task = await self.get_task_status(task_id)
        task["status"] = "timeout"
        task["error"] = f"Max wait time exceeded: {self.max_wait}s"
        self._print_final_result(task)
        return task
        
    async def execute(self, agent_args: dict) -> Dict[str, Any]:
        """
        一站式执行：提交 + 等待
        
        Args:
            agent_args: Agent 参数
            
        Returns:
            任务详情
        """
        # 提交任务
        task_id = await self.submit_task(agent_args)
        
        # 等待完成
        return await self.wait_for_task(task_id)


class TradingAgentClientDB(DatabaseAgentClient):
    """Trading Agent Client（数据库模式）"""

    def __init__(
            self,
            agent_url: str = "http://localhost:9999",
            poll_interval: float = 30.0,
            heartbeat_timeout: float = 300.0,  # 改为 300 秒（5 分钟）
            max_wait: float = 3600.0,
            timeout: float = 180.0,  # HTTP 请求超时（等待 Job 启动）
            a2a_token: str = ""
    ):
        """
        初始化 Trading Agent Client

        Args:
            agent_url: Agent Server 地址
            poll_interval: 轮询间隔（秒）
            heartbeat_timeout: 心跳超时（秒）
            max_wait: 最大等待时间（秒）
            timeout: HTTP 请求超时（秒）
            a2a_token: A2A 认证 token
        """
        super().__init__(
            agent_url=agent_url,
            poll_interval=poll_interval,
            heartbeat_timeout=heartbeat_timeout,
            max_wait=max_wait,
            timeout=timeout,
            a2a_token=a2a_token
        )

        # 报告下载器使用统一的 URL（去掉 /a2a/ 部分）
        # agent_url: http://127.0.0.1:8000/api/v1/agents/69/a2a/
        # report_url: http://127.0.0.1:8000/api/v1/agents/69/
        report_base_url = normalize_agent_base_url(agent_url)

        self.report_downloader = ReportDownloader(
            agent_url=report_base_url,
            a2a_token=a2a_token,
            timeout=60.0,
            reports_path="reports",  # 通过 Backend 时用 /reports
            reports_zip_path="reports/zip"
        )

    async def analyze_stock(
            self,
            stock_code: str,
            download_reports: bool = True
    ):
        """
        分析股票

        Args:
            stock_code: 股票代码（如 "AAPL" 或 "000001.SZ"）
            download_reports: 是否自动下载报告（默认 True）

        Returns:
            任务结果（包含下载的文件路径）
        """
        agent_args = {
            "stock_code": stock_code,  # 注意：参数名是 stock_code，不是 symbol
        }

        logger.info(f"[TradingAgent] Analyzing {stock_code}")

        # 执行任务
        result = await self.execute(agent_args)

        # 如果任务成功完成，自动下载报告
        if download_reports and result.get("status") == "completed":
            logger.info(f"[TradingAgent] Task completed, downloading reports...")

            download_result = await self.download_reports_zip()

            if download_result:
                result["downloaded_file"] = download_result
                logger.info(f"[TradingAgent] Reports downloaded: {download_result}")
            else:
                logger.warning(f"[TradingAgent] Failed to download reports")

        return result

    async def download_reports_zip(self, output_dir: str = "downloaded_reports") -> str | None:
        """
        下载报告 ZIP 包

        Args:
            output_dir: 输出目录

        Returns:
            下载后的文件路径，失败返回 None
        """
        return await self.report_downloader.download_zip(output_dir)
