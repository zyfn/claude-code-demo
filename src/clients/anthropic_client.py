"""Anthropic API client."""

import httpx
from src.config import settings
from src.clients.base import BaseClient, Message, AssistantResponse, ToolCall


class AnthropicClient(BaseClient):
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.api_base,
            headers={
                "x-api-key": settings.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=120.0,
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        max_tokens: int = 8192,
    ) -> AssistantResponse:
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg += m.content + "\n"
            elif m.role == "user":
                content: list[dict] = [{"type": "text", "text": m.content}]
                if m.tool_result:
                    content = [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_result.get("id", ""),
                            "content": m.tool_result.get("output", ""),
                        }
                    ]
                chat_messages.append({"role": "user", "content": content})
            elif m.role == "assistant":
                blocks: list[dict] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc["name"],
                        "input": tc.get("parameters", {}),
                    })
                chat_messages.append({"role": "assistant", "content": blocks})

        payload: dict = {
            "model": settings.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        if system_msg:
            payload["system"] = system_msg.strip()
        if tools:
            payload["tools"] = tools

        resp = await self.client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        text = ""
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                text += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(ToolCall(
                    name=block["name"],
                    parameters=block.get("input", {}),
                    id=block["id"],
                ))

        return AssistantResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=data.get("stop_reason", "end_turn"),
        )
