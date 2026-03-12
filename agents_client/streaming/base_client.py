"""
A2A Agent Client - streaming 模式
"""

import os
from pathlib import Path
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendStreamingMessageRequest
from dotenv import load_dotenv

from agents_client.utils import ReportDownloader, normalize_agent_base_url


DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=60.0, pool=60.0)


def load_project_env(module_file: str) -> None:
    load_dotenv(Path(module_file).resolve().parents[2] / ".env")


class A2AAgentClient:
    def __init__(self, agent_url: str, a2a_token: str | None = None, timeout: httpx.Timeout | None = None):
        self.agent_url = agent_url
        self.a2a_token = a2a_token or os.getenv("FINTOOLS_ACCESS_TOKEN", "your-secret-token-here")
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.httpx_client: httpx.AsyncClient | None = None
        self.client: A2AClient | None = None

    async def __aenter__(self):
        self.httpx_client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.a2a_token}",
                "X-Server-Mode": "streaming",
            },
            trust_env=False,
        )
        agent_card = await A2ACardResolver(
            httpx_client=self.httpx_client,
            base_url=self.agent_url,
        ).get_agent_card()
        self.client = A2AClient(httpx_client=self.httpx_client, agent_card=agent_card, url=self.agent_url)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.httpx_client:
            await self.httpx_client.aclose()

    async def send_message_streaming(
        self,
        *,
        user_message: str,
        agent_args: dict,
        on_status_update=None,
        on_artifact_update=None,
        on_error=None,
    ) -> dict:
        req = SendStreamingMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(
                message={
                    "role": "user",
                    "parts": [{
                        "kind": "text",
                        "text": user_message,
                        "metadata": {"agent_args": agent_args},
                    }],
                    "messageId": uuid4().hex,
                }
            ),
        )

        event_count = 0
        async for chunk in self.client.send_message_streaming(req):
            event_count += 1
            result = chunk.model_dump(mode="json", exclude_none=True).get("result")
            if not result:
                continue
            await self._handle_stream_result(result, on_status_update, on_artifact_update, on_error)

        return {"event_count": event_count, "success": True}

    async def _handle_stream_result(self, result: dict, on_status_update, on_artifact_update, on_error) -> None:
        if result.get("kind") == "status-update":
            for part in result.get("status", {}).get("message", {}).get("parts", []):
                text = part.get("text")
                if not text:
                    continue
                if ("error" in text.lower() or "异常" in text) and on_error:
                    await on_error(text)
                if on_status_update:
                    await on_status_update(text)
                else:
                    print(text)
            return

        if result.get("kind") == "artifact-update":
            artifact = result.get("artifact", {})
            if on_artifact_update:
                await on_artifact_update(artifact)
            else:
                print(f"\n[生成文件] {artifact.get('name', 'unknown')}")


class StreamingStockAgentClient:
    def __init__(self, agent_url: str, user_message: str, a2a_token: str | None = None):
        self.agent_url = agent_url
        self.user_message = user_message
        self.a2a_token = a2a_token
        self.report_downloader = ReportDownloader(
            normalize_agent_base_url(agent_url),
            a2a_token,
            reports_path="reports",
            reports_zip_path="reports/zip",
        )

    async def analyze_stock(self, stock_code: str) -> dict:
        async with A2AAgentClient(self.agent_url, self.a2a_token) as client:
            return await client.send_message_streaming(
                user_message=self.user_message.format(stock_code=stock_code),
                agent_args={"stock_code": stock_code},
            )


async def run_stock_agent_client(
    client_cls: type[StreamingStockAgentClient],
    title: str,
    stock_code: str,
    agent_url: str,
    a2a_token: str,
) -> bool:
    print(f"\n{'=' * 60}")
    print(f"运行 {title}, May take 30-60s to start server...")
    print(f"{'=' * 60}")
    print(f"股票代码: {stock_code}")
    print(f"Agent地址: {agent_url}")
    print(f"{'=' * 60}\n")

    client = client_cls(agent_url=agent_url, a2a_token=a2a_token)
    result = await client.analyze_stock(stock_code)

    print(f"\n{'=' * 60}")
    print(f"执行完成！共处理 {result['event_count']} 个事件")
    print(f"{'=' * 60}\n")

    await client.report_downloader.show_reports()
    await client.report_downloader.download_zip()
    return result["success"]
