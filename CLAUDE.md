# CLAUDE.md

本文件为 Claude Code 在本仓库中工作时提供指导。



## 常用命令

```bash
source .venv/bin/activate
pip install -e .
python -m src.main
CCC_DEBUG_LOG=true python -m src.main  # 开启调试日志
```

---

## 架构原则

### 1. 模块结构（对标 Claude Code）

```
main.py           → 入口，选择运行模式
repl.py           → 交互式会话（= Claude Code 的 REPL.tsx）
                     持有 messages，组装 deps，直接调 query()
query.py          → 核心 ReAct 循环（= Claude Code 的 query.ts）
                     纯 async generator，只依赖抽象接口
types.py          → 跨模块共享类型（事件、QueryDeps、压缩接口）
hooks.py          → 统一 hook 系统（HookRegistry + 配置文件加载）
config.py         → 配置（pydantic-settings，env vars）
context.py        → 环境采集（git status、CLAUDE.md、日期）
system_prompt.py  → 静态 prompt 模板（不含 tool 描述）
ui.py             → 终端渲染（Rich）
api/client.py     → LLM 客户端（LiteLLM 封装 + debug 日志）
api/retry.py      → 网络层重试 + 错误分类
compact/          → 压缩阶段（budget、micro、auto）
agents/types.py   → AgentDefinition 数据类
agents/builtin.py → 内置 agent 定义（general-purpose、explore）
tools/types.py    → Tool Protocol、ToolResult、ToolCall
tools/registry.py → get_default_tools()（核心工具，不含 agent/todo）
tools/executor.py → ToolExecutor（submit→drain→collect + hooks + can_use_tool）
tools/impl/       → 具体 tool 实现
  bash.py         → BashTool
  file.py         → ReadFileTool、WriteFileTool、EditFileTool
  grep.py         → GrepTool
  todo.py         → TodoWriteTool（会话任务清单，模型自主管理）
  agent.py        → AgentTool（生成子 agent，调用 query()）
  agent_deps.py   → AgentToolDeps（AgentTool 的依赖注入）
  agent_runner.py → run_subagent()（实际调用 query() 的逻辑）
```

没有 Agent 类，没有 bootstrap。repl.py 直接持有 messages 并调 query()，和 Claude Code 一样。

### 2. 上下文三层结构（与 Claude Code 一致）

- **system_prompt + system_context** → 一条 system message，构建一次不变
- **user_context**（CLAUDE.md、日期）→ 一条 user message，每次 API 调用 prepend，不在历史里，不会被压缩
- **state.messages**（对话历史）→ 可被 compaction 压缩

### 3. 工具执行管道

```
executor.submit(calls) → yields ToolEvent(rejected/running)
  ① validate_input(tool, params)
  ② PreToolUse hooks（HookRegistry，用户配置，matcher 过滤）→ 可阻止
  ③ tool.is_read_only()? → True 跳过权限
  ④ can_use_tool(call)（REPL 提供的函数）→ 可阻止
  ⑤ asyncio.create_task(tool.execute()) → yields ToolEvent(running)

executor.drain() → yields ToolEvent(completed/error)
  ⑥ asyncio.wait(FIRST_COMPLETED) → 并发完成
  ⑦ PostToolUse hooks

executor.collect_tool_messages() → list[Message]
  ⑧ 收集所有 rejected + completed 的 tool messages
```

query.py 只转发 executor 产生的事件，不构造 ToolEvent。

### 4. Hook 系统

统一的 HookRegistry，所有事件走同一条路径：
- `hooks.on("PreToolUse", handler, matcher="bash")` — 代码注册
- `.ccc/hooks.yaml` — 配置文件注册（command 类型，exit code 2 = 阻止）
- `hooks.dispatch("Stop", {...})` — 统一触发

### 5. 消息所有权

- repl.py 持有 `messages`（唯一真实来源）
- query() 接收副本，操作后通过 `QueryComplete.messages` 返回快照
- repl.py 只在收到 QueryComplete 时更新 messages（异常时不更新，无孤立消息）

### 6. 扩展点

| 想要添加... | 方式 | 在哪里接入 |
|------------|------|-----------|
| 新压缩阶段 | `async (CompactionContext) → CompactionResult` | repl.py → stages 列表 |
| 新 tool（无依赖） | 满足 Tool Protocol 的 dataclass | tools/registry.py |
| 新 tool（有依赖） | Tool + deps 注入 | repl.py 创建，加入 all_tools |
| 新 agent 类型 | AgentDefinition | agents/builtin.py 或 .ccc/agents/*.yaml |
| 新 hook | `hooks.on(event, handler, matcher)` 或 `.ccc/hooks.yaml` | repl.py |
| 新 LLM provider | 满足 LLMClient Protocol | repl.py → client |
| 新通道（web） | 新文件，持有 messages，调 query() | main.py 路由 |

### 7. 子 Agent 架构

AgentTool 是一个普通 Tool，内部调用 `query()` 实现子 agent：

```
AgentTool.execute(prompt, subagent_type)
  → agent_runner.run_subagent()
    → 构建独立的 QueryDeps（独立 messages、executor、abort_signal）
    → 调用 query()（复用核心循环）
    → 收集最终文本作为 tool_result 返回
```

关键隔离：
- 子 agent 有独立的 messages（不污染父对话）
- 子 agent 有独立的 ToolExecutor（可限制工具集）
- 子 agent 共享父 agent 的 `can_use_tool`（权限继承）
- 子 agent 有独立的 abort_signal

依赖注入链：`repl.py → AgentToolDeps → AgentTool → agent_runner → query()`
- `agent_runner.py` 是 tools/ 中唯一 import query 的地方
- AgentTool 本身不 import query — 通过 agent_runner 间接调用

### 8. 禁止事项

- 不要在系统提示词中重复工具描述 — API `tools` 参数负责
- 不要在 asyncio.create_task 内运行 can_use_tool — 它可能做同步 I/O
- 不要使用全局单例 — 显式传递
- 不要从上层导入（tools/ 不得 import repl.py）
- 不要混用同步和异步压缩阶段 — 全部 async
