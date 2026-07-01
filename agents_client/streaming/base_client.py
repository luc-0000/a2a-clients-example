"""
Streaming-style A2A client for FinTools task agents.

Backend behavior (a2a_plane.py:794): all task agents (trading / deep_research /
data_agent / hk_ai_agent / test_agent) run in job-mode — POST /a2a/ returns
{run_id, job_name, status:"job_started"} immediately, no SSE stream. The Pod
runs main.py, exits, and writes reports to OSS.

This client wraps that contract into a streaming-like UX:
1. POST /a2a/ → run_id
2. Poll GET /tasks/{run_id} every N seconds
3. Print status transitions as they happen (the "stream")
4. When status=completed, download reports ZIP

No a2a-sdk dependency — pure httpx.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from agents_client.utils import ReportDownloader, normalize_agent_base_url


DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=60.0)


def load_project_env(module_file: str) -> None:
    load_dotenv(Path(module_file).resolve().parents[2] / ".env")


class StreamingAgentClient:
    """Submit a task and stream status transitions until terminal state.

    Emits three kinds of inline events to make polling feel like a stream:
      [submitted]  run_id assigned
      [status]     status changed (pending → running → completed/failed)
      [heartbeat]  periodic heartbeat confirmation
    """

    def __init__(
        self,
        agent_url: str,
        *,
        a2a_token: str | None = None,
        poll_interval: float = 5.0,
        heartbeat_timeout: float = 300.0,
        max_wait: float = 1800.0,
        timeout: httpx.Timeout | None = None,
    ):
        self.agent_url = agent_url.rstrip("/")
        self.base_url = normalize_agent_base_url(self.agent_url)
        self.a2a_token = a2a_token or os.getenv("FINTOOLS_ACCESS_TOKEN", "")
        self.poll_interval = poll_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_wait = max_wait
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.headers = {"Authorization": f"Bearer {self.a2a_token}"} if self.a2a_token else {}
        self.report_downloader = ReportDownloader(
            self.base_url,
            self.a2a_token,
            reports_path="reports",
            reports_zip_path="reports/zip",
        )

    def _emit(self, kind: str, **fields: Any) -> None:
        if kind == "submitted":
            print(f"\n[submitted] run_id={fields.get('run_id')}")
            print(f"            job={fields.get('job_name')}")
        elif kind == "status":
            print(f"[status]    {fields.get('prev')} → {fields.get('now')}")
        elif kind == "heartbeat":
            age = fields.get("age_seconds")
            if age is not None:
                print(f"[heartbeat] {age:.0f}s ago")
        elif kind == "result":
            print(f"\n[result]    status={fields.get('status')}")
            if fields.get("result"):
                preview = str(fields["result"])[:300]
                print(f"            result={preview}")
            if fields.get("error"):
                print(f"            error={fields['error']}")
        elif kind == "info":
            print(f"[info]      {fields.get('msg')}")

    async def submit(self, agent_args: dict[str, Any], user_text: str = "submit task") -> str:
        """POST /a2a/ with A2A JSON-RPC body. Returns run_id."""
        body = {
            "jsonrpc": "2.0",
            "method": "message/stream",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{
                        "type": "text",
                        "text": user_text,
                        "metadata": {"agent_args": agent_args},
                    }],
                }
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(self.agent_url, json=body, headers=self.headers)
            response.raise_for_status()
            data = response.json()

        run_id = data.get("run_id") or data.get("task_id")
        if not run_id:
            raise ValueError(f"backend response missing run_id: {data}")

        self._emit("submitted", run_id=run_id, job_name=data.get("job_name", "unknown"))
        return run_id

    async def poll_once(self, run_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/tasks/{run_id}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def stream_until_terminal(self, run_id: str) -> dict[str, Any]:
        """Poll /tasks/{run_id} until status is completed/failed. Emit transitions."""
        prev_status: str | None = None
        waited = 0.0
        last_emit_at = 0.0

        while waited < self.max_wait:
            task = await self.poll_once(run_id)
            status = task.get("status", "unknown")

            if status != prev_status:
                self._emit("status", prev=prev_status or "(start)", now=status)
                prev_status = status
                last_emit_at = waited
            elif status != "completed" and status != "failed" and (waited - last_emit_at) >= 30.0:
                # Tick: status hasn't changed for 30s, reassure user we're still alive
                self._emit("info", msg=f"waited {waited:.0f}s, still {status}")
                last_emit_at = waited

            if status in {"completed", "failed"}:
                self._emit(
                    "result",
                    status=status,
                    result=task.get("result"),
                    error=task.get("error"),
                )
                return task

            # heartbeat: emit only if backend reports heartbeat_at
            hb_age = self._heartbeat_age_seconds(task.get("heartbeat_at"))
            if hb_age is not None and (waited - last_emit_at) >= 30.0:
                self._emit("heartbeat", age_seconds=hb_age)
                last_emit_at = waited
                if hb_age > self.heartbeat_timeout:
                    self._emit(
                        "info",
                        msg=f"heartbeat stale ({hb_age:.0f}s > {self.heartbeat_timeout}s) — Pod may have died",
                    )

            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval

        self._emit("info", msg=f"max_wait exceeded ({self.max_wait}s), final poll below")
        return await self.poll_once(run_id)

    @staticmethod
    def _heartbeat_age_seconds(iso_time: str | None) -> float | None:
        from datetime import datetime, timezone
        if not iso_time:
            return None
        try:
            parsed = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed).total_seconds()

    async def run(self, agent_args: dict[str, Any], user_text: str = "submit task") -> dict[str, Any]:
        run_id = await self.submit(agent_args, user_text=user_text)
        return await self.stream_until_terminal(run_id)


async def run_stock_agent_stream(
    client: StreamingAgentClient,
    title: str,
    stock_code: str,
    *,
    download_reports: bool = True,
    report_output_dir: str | None = None,
) -> dict[str, Any]:
    """Convenience entrypoint for stock-code-driven agents (trading / deep_research)."""
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")
    print(f"Agent URL:    {client.agent_url}")
    print(f"Stock code:   {stock_code}")
    print(f"A2A Token:    {client.a2a_token[:10]}...")
    print(f"Poll interval: {client.poll_interval}s")
    print(f"Heartbeat timeout: {client.heartbeat_timeout}s")
    print(f"{'=' * 60}")

    result = await client.run({"stock_code": stock_code})

    if download_reports and result.get("status") == "completed":
        print("\n[reports]   downloading ZIP...")
        try:
            downloaded = await client.report_downloader.download_zip(output_dir=report_output_dir)
            if downloaded:
                print(f"[reports]   saved to {downloaded}")
            else:
                print("[reports]   no ZIP available (Pod may have exited, fetch from OSS signed URL instead)")
        except Exception as e:
            print(f"[reports]   download failed: {e}")

    return result
