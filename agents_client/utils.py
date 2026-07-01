"""
A2A Agent Client shared utilities.

Provides common client-side functionality:
- Report downloading (shared across client variants)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


def normalize_agent_base_url(agent_url: str) -> str:
    """Normalize the agent base URL: strip trailing slash and trailing /a2a."""
    normalized = agent_url.rstrip("/")
    if normalized.endswith("/a2a"):
        normalized = normalized[:-4]
    return normalized


def require_access_token(env_var: str = "FINTOOLS_ACCESS_TOKEN") -> str:
    """Read and validate the access token. If missing, print guidance and exit."""
    token = os.getenv(env_var)
    if token:
        return token
    print(f"ERROR: {env_var} environment variable is not set")
    print("\nSet it in your .env file:")
    print(f"  {env_var}=your-token-here")
    print("\nOr export it in your shell:")
    print(f"  export {env_var}=your-token-here")
    sys.exit(1)


class ReportDownloader:
    """Report downloader (shared across client variants)."""

    def __init__(
        self,
        agent_url: str,
        a2a_token: str = None,
        timeout: float = 60.0,
        reports_path: str = "api/reports",
        reports_zip_path: str = "api/reports/zip",
    ):
        """
        Initialize the report downloader.

        Args:
            agent_url: Agent Server URL (e.g. http://localhost:9999)
            a2a_token: Auth token
            timeout: HTTP request timeout
            reports_path: Report list path (default api/reports)
            reports_zip_path: ZIP download path (default api/reports/zip)
        """
        if not agent_url:
            raise ValueError("agent_url is required")

        self.agent_url = agent_url.rstrip("/")
        self.a2a_token = a2a_token or ""
        self.timeout = timeout

        # Build report URLs
        self.reports_url = f"{self.agent_url}/{reports_path}"
        self.reports_zip_url = f"{self.agent_url}/{reports_zip_path}"

    def _auth_headers(self) -> dict:
        if not self.a2a_token:
            return {}
        return {"Authorization": f"Bearer {self.a2a_token}"}

    async def list_reports(self) -> list:
        """Fetch the report list."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.reports_url, headers=self._auth_headers())

            if response.status_code != 200:
                logger.error(f"Failed to fetch report list: {response.status_code}")
                return []

            data = response.json()
            return data.get("reports", [])

    async def show_reports(self) -> list:
        """Display the report list."""
        reports = await self.list_reports()

        print(f"\n{'='*60}")
        print("Reports")
        print(f"{'='*60}")

        if not reports:
            print("  No reports available")
            return []

        print(f"{len(reports)} report(s) available:\n")

        for i, report in enumerate(reports, 1):
            filename = report.get("filename", "unknown")
            size_kb = report.get("size", 0) / 1024
            modified = report.get("modified", "N/A")

            print(f"{i}. {filename}")
            print(f"   size: {size_kb:.1f} KB")
            print(f"   modified: {modified}\n")

        print(f"{'='*60}\n")

        return reports

    async def download_zip(self, output_dir: str | None = None) -> str | None:
        """
        Download all reports as a single ZIP file.

        Args:
            output_dir: Output directory (defaults to relative path "downloaded_reports")

        Returns:
            Path to the downloaded file, or None on failure.
        """
        if output_dir is None:
            output_dir = "downloaded_reports"
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            print(f"Downloading ZIP...")
            print(f"  URL: {self.reports_zip_url}")

            try:
                response = await client.get(self.reports_zip_url, headers=self._auth_headers())

                # Handle specific error status codes
                if response.status_code == 410:
                    print(f"✗ Server has been shut down. Reports are no longer available.")
                    return None
                elif response.status_code == 404:
                    print(f"✗ No reports available yet. Task may still be running or reports have expired.")
                    return None

                response.raise_for_status()

                # Derive filename from response headers
                content_disposition = response.headers.get("content-disposition", "")
                if "filename=" in content_disposition:
                    filename = content_disposition.split("filename=")[1].strip('"')
                else:
                    filename = f"reports_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"

                output_path = Path(output_dir) / filename
                output_path.write_bytes(response.content)

                print(f"✓ Downloaded: {output_path}")
                print(f"  size: {len(response.content) / 1024:.1f} KB")
                return str(output_path)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 410:
                    print(f"✗ Server has been shut down. Reports are no longer available.")
                elif e.response.status_code == 404:
                    print(f"✗ No reports available yet. Task may still be running or reports have expired.")
                else:
                    logger.error(f"Download failed: {e}")
                    print(f"✗ Download failed: {e}")
                return None
            except Exception as e:
                logger.error(f"Download failed: {e}")
                print(f"✗ Download failed: {e}")
                return None
