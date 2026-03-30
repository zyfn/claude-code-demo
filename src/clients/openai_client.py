"""OpenAI-compatible API client."""

import httpx
from src.config import settings
from src.clients.base import BaseClient, Message, AssistantResponse, ToolCall


class OpenAIClient(BaseClient):
    def __init__(self):
        base = settings.openai_api_base or "https://api.openai.com"
        self.client = httpx.AsyncClient(
            base_url=base,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
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
        chat_messages = []
        for m in messages:
            msg: dict = {"role": m.role}
            if m.tool_result:
                msg["role"] = "tool"
                msg["tool_call_id"] = m.tool_result.get("id", "")
                msg["content"] = m.tool_result.get("output", "")
            elif m.role == "assistant" and m.tool_calls:
                tool_calls_fmt = []
                for tc in m.tool_calls:
                    tool_calls_fmt.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": str(tc.parameters)},
                    })
                msg["tool_calls"] = tool_calls_fmt
                if m.content:
                    msg["content"] = m.content
            else:
                msg["content"] = m.content
            chat_messages.append(msg)

        payload: dict = {
            "model": settings.openai_model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        resp = await self.client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]["message"]

        text = choice.get("content") or ""
        tool_calls = []
        for tc in choice.get("tool_calls", []):
            import json as _json
            tool_calls.append(ToolCall(
                name=tc["function"]["name"],
                parameters=_json.loads(tc["function"]["arguments"]),
                id=tc["id"],
            ))

        return AssistantResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=data["choices"][0].get("finish_reason", "stop"),
        )
