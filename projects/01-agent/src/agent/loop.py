"""Agent loop: ReAct-style think-act cycle."""

from src.clients.client import LLMClient, Message, AssistantResponse
from src.tools.base import BaseTool, ToolResult
from src.agent.hooks import HookRegistry

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
    def __init__(self, client: LLMClient, tools: list[BaseTool]):
        self.client = client
        self.tools = tools
        self.tools_by_name = {t.name: t for t in tools}
        self.messages: list[Message] = []
        self.tool_schemas = [t.to_schema() for t in tools]
        self.hooks = HookRegistry()

    def on(self, name: str, handler) -> None:
        """Register a hook handler. Shortcut for agent.hooks.on()."""
        self.hooks.on(name, handler)

    async def run(self, user_input: str) -> str:
        """Run the agent loop with a user message."""
        h = self.hooks

        # Inject system prompt once at the start of the conversation
        if not self.messages:
            self.messages.append(Message(role="system", content=SYSTEM_PROMPT))

        self.messages.append(Message(role="user", content=user_input))

        iteration = 0
        while iteration < MAX_ITERATIONS:
            iteration += 1

            h.emit("stream_start")

            resp = await self.client.chat(
                messages=self.messages,
                tools=self.tool_schemas,
                on_chunk=lambda chunk: h.emit("stream_chunk", chunk=chunk),
            )

            h.emit("stream_end")

            # Tool calls mean this isn't the final answer — reset stream state
            if resp.tool_calls:
                h.emit("stream_reset")

            # No tool calls → final answer
            if not resp.tool_calls:
                self.messages.append(Message(role="assistant", content=resp.text))
                h.emit("done", text=resp.text)
                return resp.text

            # Show reasoning
            thinking = resp.reasoning or resp.text
            if thinking:
                h.emit("think", text=thinking)

            # Record assistant message with tool calls
            assistant_msg = Message(role="assistant", content=resp.text, tool_calls=resp.tool_calls)
            self.messages.append(assistant_msg)

            # Execute each tool
            for tc in resp.tool_calls:
                tool = self.tools_by_name.get(tc.name)
                if not tool:
                    result = ToolResult(f"Unknown tool: {tc.name}", is_error=True)
                else:
                    h.emit("tool_use", name=tc.name, params=tc.parameters)
                    result = await tool.execute(**tc.parameters)
                    h.emit("tool_result", output=result.output, is_error=result.is_error)

                self.messages.append(Message(
                    role="tool",
                    content=result.output,
                    tool_call_id=tc.id,
                ))

        return "Reached maximum iterations"
