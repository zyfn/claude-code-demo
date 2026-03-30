"""Agent loop: ReAct-style think-act cycle."""

import asyncio
from src.clients.base import BaseClient, Message, AssistantResponse
from src.tools.base import BaseTool, ToolResult


SYSTEM_PROMPT = """You are a coding assistant running in a terminal. You can read files, write files, edit files, and execute shell commands.

Rules:
- Be concise and direct
- Use tools to accomplish tasks
- When editing files, use the edit tool with exact string matching
- Always verify your changes worked by reading the file after editing
- If a command fails, analyze the error and try to fix it
- Think step by step before acting
"""

MAX_ITERATIONS = 25


class AgentLoop:
    def __init__(self, client: BaseClient, tools: list[BaseTool]):
        self.client = client
        self.tools = tools
        self.tools_by_name = {t.name: t for t in tools}
        self.messages: list[Message] = []
        self.tool_schemas = [t.to_schema() for t in tools]

    async def run(self, user_input: str, on_think=None, on_tool_use=None, on_result=None):
        """Run the agent loop with a user message."""
        self.messages.append(Message(role="user", content=user_input))

        iteration = 0
        while iteration < MAX_ITERATIONS:
            iteration += 1

            # Call LLM
            resp = await self.client.chat(
                messages=self.messages,
                tools=self.tool_schemas,
            )

            # Handle thinking/thinking blocks
            if resp.text and on_think:
                on_think(resp.text)

            # If no tool calls, we're done
            if not resp.tool_calls:
                self.messages.append(Message(role="assistant", content=resp.text))
                return resp.text

            # Execute tool calls
            assistant_msg = Message(role="assistant", content=resp.text, tool_calls=[
                {"name": tc.name, "parameters": tc.parameters, "id": tc.id}
                for tc in resp.tool_calls
            ])
            self.messages.append(assistant_msg)

            for tc in resp.tool_calls:
                tool = self.tools_by_name.get(tc.name)
                if not tool:
                    result = ToolResult(f"Unknown tool: {tc.name}", is_error=True)
                else:
                    if on_tool_use:
                        on_tool_use(tc.name, tc.parameters)
                    result = await tool.execute(**tc.parameters)
                    if on_result:
                        on_result(result.output, result.is_error)

                self.messages.append(Message(
                    role="user",
                    content="",
                    tool_result={"id": tc.id, "output": result.output},
                ))

        return "⚠️ Reached maximum iterations"
