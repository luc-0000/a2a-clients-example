"""
A2A Agent Client 公共模块

提供通用的 Agent 客户端功能：
- Agent 连接和初始化
- Stream 处理
"""

import logging
import os
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import SendStreamingMessageRequest, MessageSendParams


DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=None,
    write=60.0,
    pool=60.0,
)


class A2AAgentClient:
    """A2A Agent 客户端基类"""

    def __init__(self, agent_url: str, a2a_token: str = None, timeout: httpx.Timeout = None):
        self.agent_url = agent_url
        self.a2a_token = a2a_token or os.getenv("FINTOOLS_ACCESS_TOKEN", "your-secret-token-here")
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.logger = logging.getLogger(self.__class__.__name__)

        self.httpx_client = None
        self.agent_card = None
        self.client = None

    async def __aenter__(self):
        self.httpx_client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.a2a_token}",
                "X-Server-Mode": "streaming",
            },
            trust_env=False,
        )

        resolver = A2ACardResolver(httpx_client=self.httpx_client, base_url=self.agent_url)
        self.agent_card = await resolver.get_agent_card()
        self.logger.info("Agent card fetched: %s", self.agent_card.name)

        self.client = A2AClient(
            httpx_client=self.httpx_client,
            agent_card=self.agent_card,
            url=self.agent_url,
        )
        self.logger.info("A2AClient initialized.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.httpx_client:
            await self.httpx_client.aclose()

    async def send_message_streaming(
        self,
        user_message: str,
        agent_args: dict,
        on_status_update: callable = None,
        on_artifact_update: callable = None,
        on_error: callable = None,
    ) -> dict:
        payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": user_message,
                        "metadata": {"agent_args": agent_args},
                    }
                ],
                "messageId": uuid4().hex,
            }
        }

        req = SendStreamingMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**payload),
        )

        event_count = 0
        success = True

        async for chunk in self.client.send_message_streaming(req):
            event_count += 1
            result = chunk.model_dump(mode="json", exclude_none=True).get("result")
            if not result:
                continue

            if result.get("kind") == "status-update":
                parts = result.get("status", {}).get("message", {}).get("parts", [])
                for part in parts:
                    text = part.get("text")
                    if not text:
                        continue

                    if "error" in text.lower() or "异常" in text:
                        success = False
                        if on_error:
                            await on_error(text)

                    if on_status_update:
                        await on_status_update(text)
                    else:
                        print(text)
                continue

            if result.get("kind") == "artifact-update":
                artifact = result.get("artifact", {})
                if on_artifact_update:
                    await on_artifact_update(artifact)
                else:
                    print(f"\n[生成文件] {artifact.get('name', 'unknown')}")

        return {"event_count": event_count, "success": success}
