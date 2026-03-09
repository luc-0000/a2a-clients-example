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
from typing import Optional, Dict, Any

import httpx

from agents_client.utils import ReportDownloader

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
        self.a2a_token = a2a_token
        
        # 构建 headers
        self.headers = {}
        if a2a_token:
            self.headers["Authorization"] = f"Bearer {a2a_token}"
        
        # 从 agent_url 提取 task_url（去掉 /a2a/ 部分）
        # agent_url: http://xxx/api/v1/agents/69/a2a/
        # task_url:  http://xxx/api/v1/agents/69/
        self.task_url = self.agent_url.rstrip("/")
        if self.task_url.endswith("/a2a"):
            self.task_url = self.task_url[:-4]
        
    async def submit_task(self, agent_args: dict, mode: str = "db_polling") -> str:
        """提交任务，返回 task_id
        
        Args:
            agent_args: Agent 参数
            mode: Server 模式 (streaming | db_polling)，默认 db_polling
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agent_url}/api/tasks",
                json={"mode": mode, "agent_args": agent_args},
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
        heartbeat_at = task.get("heartbeat_at")
        updated_at = task.get("updated_at")
        
        # 计算心跳时间差（使用 UTC 时间）
        heartbeat_age = None
        if heartbeat_at:
            heartbeat_time = datetime.fromisoformat(heartbeat_at)
            # 如果时间没有时区信息，假设是 UTC
            if heartbeat_time.tzinfo is None:
                heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)
            heartbeat_age = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()
            
        # 计算更新时间差（使用 UTC 时间）
        updated_age = None
        if updated_at:
            updated_time = datetime.fromisoformat(updated_at)
            # 如果时间没有时区信息，假设是 UTC
            if updated_time.tzinfo is None:
                updated_time = updated_time.replace(tzinfo=timezone.utc)
            updated_age = (datetime.now(timezone.utc) - updated_time).total_seconds()
        
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
        
    async def wait_for_task(
        self,
        task_id: str,
        on_status_update: callable = None
    ) -> Dict[str, Any]:
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
            
            # 回调（可选）
            if on_status_update:
                await on_status_update(task)
            
            # 检查是否完成
            if status == "completed":
                self._print_final_result(task)
                return task
                
            if status == "failed":
                self._print_final_result(task)
                return task
            
            # 检查心跳超时（Server 可能挂了）
            # 但只在任务未完成时才检查心跳
            heartbeat_at = task.get("heartbeat_at")
            if heartbeat_at:
                heartbeat_time = datetime.fromisoformat(heartbeat_at)
                # 如果时间没有时区信息，假设是 UTC
                if heartbeat_time.tzinfo is None:
                    heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)
                heartbeat_age = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()
                
                # 只有在心跳超时且任务状态不是 completed/failed 时才判断超时
                if heartbeat_age > self.heartbeat_timeout and status not in ["completed", "failed"]:
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
        
    async def execute(
        self,
        agent_args: dict,
        on_status_update: callable = None
    ) -> Dict[str, Any]:
        """
        一站式执行：提交 + 等待
        
        Args:
            agent_args: Agent 参数
            on_status_update: 状态更新回调（可选）
            
        Returns:
            任务详情
        """
        # 提交任务
        task_id = await self.submit_task(agent_args)
        
        # 等待完成
        return await self.wait_for_task(task_id, on_status_update)
        
    async def list_tasks(self, status: str = None) -> list:
        """列出任务"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            params = {}
            if status:
                params["status"] = status
                
            response = await client.get(
                f"{self.agent_url}/api/tasks",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            tasks = data.get("tasks", [])
            
            print(f"\n{'='*60}")
            print(f"任务列表 ({len(tasks)} 个)")
            print(f"{'='*60}")
            
            for task in tasks:
                task_id = task.get("task_id", "unknown")
                status = task.get("status", "unknown")
                progress = task.get("progress", "")
                created_at = task.get("created_at", "")
                
                print(f"\nTask: {task_id}")
                print(f"  状态: {status}")
                if progress:
                    print(f"  进度: {progress}")
                if created_at:
                    print(f"  创建: {created_at}")
                    
            print(f"\n{'='*60}\n")
            
            return tasks


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
        report_base_url = agent_url.rstrip("/")
        if report_base_url.endswith("/a2a"):
            report_base_url = report_base_url[:-4]

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
            depth: str = "quick",
            query: str = None,
            download_reports: bool = True
    ):
        """
        分析股票

        Args:
            stock_code: 股票代码（如 "AAPL" 或 "000001.SZ"）
            depth: 分析深度（"quick" 或 "deep"）
            query: 自定义查询（可选）
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

    async def list_reports(self) -> list:
        """获取报告列表"""
        return await self.report_downloader.show_reports()

    async def batch_analyze(
            self,
            symbols: list,
            depth: str = "quick"
    ):
        """
        批量分析股票

        Args:
            symbols: 股票代码列表
            depth: 分析深度

        Returns:
            结果列表
        """
        logger.info(f"[TradingAgent] Batch analyzing {len(symbols)} stocks")

        # 提交所有任务
        task_ids = []
        for symbol in symbols:
            task_id = await self.submit_task({
                "symbol": symbol,
                "depth": depth,
                "query": f"分析 {symbol} 股票"
            })
            task_ids.append((symbol, task_id))

        # 等待所有任务完成
        results = []
        for symbol, task_id in task_ids:
            logger.info(f"[TradingAgent] Waiting for {symbol}...")
            result = await self.wait_for_task(task_id)
            results.append({
                "symbol": symbol,
                "task_id": task_id,
                "result": result
            })

        return results


# ==================== 命令行入口 ====================

async def main():
    """测试用例"""
    import sys
    
    # 默认参数
    agent_url = "http://localhost:9999"
    
    # 从命令行读取
    if len(sys.argv) > 1:
        agent_url = sys.argv[1]
        
    print(f"\n{'='*60}")
    print(f"A2A Agent Client (Database Mode)")
    print(f"{'='*60}")
    print(f"Agent URL: {agent_url}")
    print(f"轮询间隔: 30 秒")
    print(f"心跳超时: 90 秒")
    print(f"{'='*60}\n")
    
    client = DatabaseAgentClient(
        agent_url=agent_url,
        poll_interval=30.0,
        heartbeat_timeout=90.0,
        max_wait=3600.0
    )
    
    # 执行任务
    result = await client.execute(
        agent_args={
            "query": "测试任务",
            "depth": "quick"
        }
    )
    
    print(f"\n最终状态: {result.get('status')}")
    if result.get("result"):
        print(f"结果长度: {len(result['result'])} 字符")


if __name__ == "__main__":
    asyncio.run(main())
