"""
A2A Agent Client 公共工具

提供通用的客户端功能：
- 报告下载（可被 streaming 和 db_polling 模式共用）
"""

import logging
from pathlib import Path
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class ReportDownloader:
    """报告下载器（通用，可被 streaming 和 db_polling 模式共用）"""

    def __init__(
        self,
        agent_url: str,
        a2a_token: str = None,
        timeout: float = 60.0,
        reports_path: str = "api/reports",
        reports_zip_path: str = "api/reports/zip",
    ):
        """
        初始化报告下载器

        Args:
            agent_url: Agent Server 地址（如 http://localhost:9999）
            a2a_token: 认证 token
            timeout: HTTP 请求超时时间
            reports_path: 报告列表路径（默认 api/reports）
            reports_zip_path: ZIP 下载路径（默认 api/reports/zip）
        """
        if not agent_url:
            raise ValueError("agent_url is required")

        self.agent_url = agent_url.rstrip("/")
        self.a2a_token = a2a_token or ""
        self.timeout = timeout
        
        # 构造报告 URL
        self.reports_url = f"{self.agent_url}/{reports_path}"
        self.reports_zip_url = f"{self.agent_url}/{reports_zip_path}"

    async def list_reports(self) -> list:
        """获取报告列表"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.a2a_token:
                headers["Authorization"] = f"Bearer {self.a2a_token}"
                
            response = await client.get(self.reports_url, headers=headers)

            if response.status_code != 200:
                logger.error(f"获取报告列表失败: {response.status_code}")
                return []

            data = response.json()
            return data.get("reports", [])

    async def show_reports(self) -> list:
        """显示报告列表"""
        reports = await self.list_reports()

        print(f"\n{'='*60}")
        print(f"报告列表")
        print(f"{'='*60}")

        if not reports:
            print("  暂无可用报告")
            return []

        print(f"共有 {len(reports)} 个报告:\n")

        for i, report in enumerate(reports, 1):
            filename = report.get("filename", "unknown")
            size_kb = report.get("size", 0) / 1024
            modified = report.get("modified", "N/A")

            print(f"{i}. {filename}")
            print(f"   大小: {size_kb:.1f} KB")
            print(f"   修改: {modified}\n")

        print(f"{'='*60}\n")

        return reports

    async def download_zip(self, output_dir: str = "downloaded_reports") -> str | None:
        """
        打包下载所有报告为 ZIP 文件

        Args:
            output_dir: 输出目录

        Returns:
            下载后的文件路径，失败返回 None
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.a2a_token:
                headers["Authorization"] = f"Bearer {self.a2a_token}"
                
            print(f"正在下载 ZIP 包...")
            print(f"  URL: {self.reports_zip_url}")

            try:
                response = await client.get(self.reports_zip_url, headers=headers)
                
                # 处理特定的错误状态码
                if response.status_code == 410:
                    print(f"✗ Server has been shut down. Reports are no longer available.")
                    return None
                elif response.status_code == 404:
                    print(f"✗ No reports available yet. Task may still be running or reports have expired.")
                    return None
                
                response.raise_for_status()

                # 从响应头获取文件名
                content_disposition = response.headers.get("content-disposition", "")
                if "filename=" in content_disposition:
                    filename = content_disposition.split("filename=")[1].strip('"')
                else:
                    filename = f"reports_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"

                output_path = Path(output_dir) / filename
                output_path.write_bytes(response.content)

                print(f"✓ 成功下载: {output_path}")
                print(f"  大小: {len(response.content) / 1024:.1f} KB")
                return str(output_path)
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 410:
                    print(f"✗ Server has been shut down. Reports are no longer available.")
                elif e.response.status_code == 404:
                    print(f"✗ No reports available yet. Task may still be running or reports have expired.")
                else:
                    logger.error(f"下载失败: {e}")
                    print(f"✗ 下载失败: {e}")
                return None
            except Exception as e:
                logger.error(f"下载失败: {e}")
                print(f"✗ 下载失败: {e}")
                return None

    async def download_single_file(
        self,
        file_url: str,
        output_dir: str = "downloaded_reports"
    ) -> str | None:
        """
        下载单个文件

        Args:
            file_url: 文件 URL（如 /reports/report.md）
            output_dir: 输出目录

        Returns:
            下载后的文件路径，失败返回 None
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 构造完整 URL
        if file_url.startswith("/"):
            full_url = f"{self.agent_url}{file_url}"
        else:
            full_url = file_url

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.a2a_token:
                headers["Authorization"] = f"Bearer {self.a2a_token}"

            try:
                response = await client.get(full_url, headers=headers)
                response.raise_for_status()

                # 从 URL 提取文件名
                filename = file_url.split("/")[-1]
                output_path = Path(output_dir) / filename
                output_path.write_bytes(response.content)

                logger.info(f"✓ 下载成功: {output_path}")
                return str(output_path)

            except Exception as e:
                logger.error(f"下载文件失败: {e}")
                return None
