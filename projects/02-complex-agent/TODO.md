# TODO — 02-complex-agent

## 当前架构总结

```
main.py → repl.py → query.py
              │          │
              │          ├─ compact/ (budget → micro → auto)
              │          ├─ api/ (client + retry)
              │          └─ tools/executor (submit→drain→collect + hooks + can_use_tool)
              │
              ├─ hooks.py (HookRegistry, .ccc/hooks.yaml)
              ├─ context.py (git status, CLAUDE.md, date)
              ├─ system_prompt.py (静态模板)
              └─ ui.py (Rich Live 动态刷新)
```

核心设计：
- 无 Agent 类，repl.py 直接持有 messages 并调 query()（对标 Claude Code REPL.tsx）
- query.py 是纯 async generator，只依赖 QueryDeps 抽象接口
- 统一 HookRegistry，所有事件走同一条 dispatch 路径
- can_use_tool 是普通函数（非类），由 REPL 提供（对标 Claude Code canUseTool）
- 上下文三层：system_prompt + system_context | user_context（不被压缩）| messages（可压缩）
- ToolExecutor 拥有完整事件生命周期（submit→drain→collect），query.py 只转发事件
- UI 使用 Rich Live 动态刷新工具状态（⏳→✓/✗），ToolsReady 事件保证 ⏳ 可见

---

## 🔴 TODO 管理系统（对标 Claude Code TodoWriteTool）

### Claude Code 的实现分析

Claude Code 的 TODO 是一个**工具**（TodoWriteTool），不是独立模块：
- 模型通过调用 `TodoWrite` 工具来创建/更新任务列表
- 数据模型：`TodoItem { content, status, activeForm }`，status = pending | in_progress | completed
- 存储在 AppState.todos 里（内存中，按 agentId 隔离）
- 工具的 prompt 非常详细，教模型何时用/何时不用 TODO，以及如何管理状态
- `content` 是祈使句（"Run tests"），`activeForm` 是进行时（"Running tests"）
- 规则：同一时间只能有一个 in_progress，完成后立刻标记 completed
- 工具权限：`checkPermissions` 返回 allow（无需用户确认）
- UI 渲染：独立组件展示 TODO 列表，实时更新

### 我们的实现计划

**Phase 1：TodoWriteTool（核心）**
- [ ] 数据模型 `TodoItem(content, status, active_form)` — `src/tools/impl/todo.py`
- [ ] `TodoWriteTool` 实现 Tool Protocol — 接收完整 todos 列表，替换当前列表
- [ ] 存储在 repl.py 的会话状态中（`todos: dict[str, list[TodoItem]]`，按 agent_id 隔离）
- [ ] `is_read_only() = True`（无需权限确认，模型自主管理）
- [ ] 工具 prompt 参考 Claude Code 的详细指导（何时用、何时不用、状态管理规则）

**Phase 2：UI 展示**
- [ ] TUI 新增 `on_todo(todos)` 方法 — 在终端渲染 TODO 列表
- [ ] 新增 `TodoEvent` 事件类型 — query.py 在 TodoWriteTool 执行后 yield
- [ ] 格式：`☐ pending / ▶ in_progress / ✓ completed`

**Phase 3：持久化（可选）**
- [ ] 保存到 `.ccc/session/<session_id>/todos.json`
- [ ] 恢复会话时加载

---

## 🔴 子 Agent 系统（对标 Claude Code AgentTool）

### Claude Code 的实现分析

Claude Code 的子 Agent 是一个**工具**（AgentTool），核心设计：

**1. AgentTool 是一个普通 Tool**
- 模型调用 `Agent(prompt, description, subagent_type)` 来启动子 agent
- `subagent_type` 选择预定义的 agent 类型（general-purpose、Explore、Plan 等）
- `is_read_only() = True` — 权限委托给子 agent 内部的工具

**2. Agent 定义（AgentDefinition）**
- 每个 agent 类型有：`agentType, whenToUse, tools, getSystemPrompt, model, maxTurns`
- 内置 agent：general-purpose（全工具）、Explore（只读搜索）、Plan（规划）
- 用户自定义 agent：`.claude/agents/*.md` frontmatter 定义

**3. runAgent — 核心执行函数**
- `async function* runAgent(...)` — 也是 async generator
- 内部直接调用 `query()`，传入子 agent 的 system_prompt、tools、messages
- 子 agent 有独立的 messages、context、abort_controller
- 子 agent 共享父 agent 的 `canUseTool`（权限继承）
- 子 agent 的 tool 列表可以被限制（`tools: ['read_file', 'grep']`）

**4. 同步 vs 异步**
- 同步 agent：父 agent 等待子 agent 完成，结果作为 tool_result 返回
- 异步 agent：立刻返回 `async_launched`，子 agent 在后台运行，完成后通知

**5. 上下文隔离**
- 子 agent 有独立的 messages（不污染父 agent 的对话历史）
- 可以 fork 父 agent 的 context messages（共享上下文）
- 子 agent 的 user_context/system_context 可以被覆盖
- 子 agent 有独立的 compaction tracking

### 我们的实现计划

**Phase 1：同步子 Agent（核心）**
- [ ] `AgentDefinition` 数据类 — `src/agents/types.py`
  ```python
  @dataclass
  class AgentDefinition:
      agent_type: str           # "general-purpose"
      when_to_use: str          # 描述何时使用
      tools: list[str] | None   # None = 全部工具，["read_file", "grep"] = 限制
      system_prompt: str        # 子 agent 的 system prompt
      max_turns: int = 10
  ```
- [ ] 内置 agent 定义 — `src/agents/builtin.py`
  - `general-purpose`：全工具，通用任务
  - `explore`：只读工具（read_file, grep, bash），代码探索
- [ ] `AgentTool` 实现 — `src/tools/impl/agent.py`
  - 参数：`prompt, description, subagent_type`
  - 执行：构建子 agent 的 QueryDeps，调用 `query()`，收集结果
  - 子 agent 有独立的 messages、ToolExecutor、abort_signal
  - 子 agent 共享父 agent 的 `can_use_tool`（权限继承）
  - 子 agent 的 tool 列表根据 AgentDefinition.tools 过滤
  - 结果：子 agent 最后一条 assistant message 的 text 作为 tool_result
- [ ] `AgentEvent` 事件类型 — UI 展示子 agent 进度

**Phase 2：用户自定义 Agent**
- [ ] `.ccc/agents/*.yaml` 加载自定义 agent 定义
  ```yaml
  agent_type: code-reviewer
  when_to_use: "Review code changes for quality and correctness"
  tools: ["read_file", "grep", "bash"]
  system_prompt: "You are a code reviewer..."
  max_turns: 5
  ```
- [ ] 启动时扫描 `.ccc/agents/` 目录，注册到 agent 定义列表
- [ ] AgentTool 的 prompt 动态列出可用 agent 类型

**Phase 3：异步子 Agent（进阶）**
- [ ] 异步模式：AgentTool 立刻返回，子 agent 在后台 asyncio.Task 运行
- [ ] 通知机制：子 agent 完成后，结果注入父 agent 的下一轮 messages
- [ ] `SendMessageTool` — 向指定 agent_id 发送消息（恢复已完成的子 agent）

**Phase 4：Agent 间通信（远期）**
- [ ] Mailbox 机制 — agent 之间通过 mailbox 异步通信
- [ ] Team 模式 — 多个 agent 协作，coordinator 分配任务

### 关键设计决策

| 决策 | Claude Code | 我们的选择 |
|------|------------|-----------|
| Agent 是什么 | 一个 Tool | 一个 Tool（保持一致） |
| 执行方式 | 内部调 query() | 内部调 query()（复用核心循环） |
| 上下文隔离 | 独立 messages + 可 fork | 独立 messages（Phase 1 不 fork） |
| 权限继承 | 共享 canUseTool | 共享 can_use_tool |
| 工具限制 | AgentDefinition.tools 过滤 | 同上 |
| 存储 | AppState 内存 | repl.py 会话状态 |
| 异步 | 支持 | Phase 3 再做 |

---

## 🟡 权限系统增强

Claude Code 的完整决策流程：
```
① PreToolUse hooks → allow/deny/ask + updatedInput
② resolveHookPermissionDecision() → 综合 hook + 规则
③ tool.checkPermissions(input) → 工具自定义权限
④ checkRuleBasedPermissions() → settings.json 规则
⑤ canUseTool() → 最终决策（弹框 / AI classifier / auto-deny）
```

- [ ] hook 返回 allow 可跳过 can_use_tool
- [ ] 持久化权限规则 — `.ccc/settings.yaml`
- [ ] tool.check_permissions(input) — 工具自定义权限
- [ ] hook 可返回 updatedInput — 修改 tool 参数
- [ ] auto mode（AI classifier）

---

## 🟡 Hook 系统演进

- [ ] PreLLMCall / PostLLMCall hooks
- [ ] SubagentStart / SubagentStop hooks（子 agent 生命周期）
- [ ] prompt hook 类型 — 用 LLM 评估
- [ ] http hook 类型 — POST 到外部 URL
- [ ] hook 返回 additionalContext — 注入额外上下文

---

## 🟡 其他功能

- [ ] Headless 模式 — `python -m src.main -p "写个hello.py"`
- [ ] Abort / 中断 — Ctrl+C 优雅中断
- [ ] Session 持久化 — 保存/恢复对话历史
- [ ] Tracing — 结构化日志

---

## 🟢 代码质量

- [ ] 单元测试 — query.py、ToolExecutor、compaction stages
- [ ] 集成测试 — 端到端 mock LLM 测试
- [ ] ruff lint + type check 通过

---

## 📝 实施优先级

1. **TodoWriteTool Phase 1** — 最简单，1 个工具 + 1 个事件类型，立刻可用
2. **AgentTool Phase 1（同步）** — 核心价值，复用 query()，独立 messages
3. **TodoWriteTool Phase 2（UI）** — 配合 Agent 使用，展示子 agent 进度
4. **AgentTool Phase 2（自定义）** — 用户扩展能力
5. **权限系统增强** — 安全性
6. **AgentTool Phase 3（异步）** — 高级功能

---

*Last updated: 2026-04-15*
