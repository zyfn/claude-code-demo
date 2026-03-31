# Client Protocols: Anthropic vs OpenAI

本文档说明本项目中两个 LLM Client 的入参和返参格式，帮助理解 Anthropic Messages API 和 OpenAI Chat Completions API 的差异。

---

## 一、统一内部协议

本项目定义了一套统一的内部数据结构，两个 Client 各自负责将内部格式翻译为对应后端的 API 格式。

### 1.1 Message 数据类

```python
@dataclass
class Message:
    role: str           # "system" | "user" | "assistant" | "tool"
    content: str | list  # 纯文本或内容块列表
```

### 1.2 ToolCall 数据类

```python
@dataclass
class ToolCall:
    id: str             # 工具调用唯一标识
    name: str           # 工具名称
    arguments: dict     # 工具参数
```

### 1.3 AssistantResponse 数据类

```python
@dataclass
class AssistantResponse:
    content: str              # 文本回复（无工具调用时）
    tool_calls: list[ToolCall] | None  # 工具调用列表（有工具调用时）
```

---

## 二、Anthropic Messages API

### 2.1 请求

**Endpoint:** `POST https://api.anthropic.com/v1/messages`

**Headers:**
| Header | 说明 |
|--------|------|
| `x-api-key` | API Key |
| `anthropic-version` | API 版本，固定为 `2023-06-01` |
| `content-type` | `application/json` |

**请求体 (JSON):**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 模型名称，如 `claude-sonnet-4-20250514` |
| `max_tokens` | integer | 是 | 最大生成 token 数 |
| `system` | string | 否 | 系统提示词 |
| `messages` | array | 是 | 对话消息列表 |
| `tools` | array | 否 | 工具定义列表 |

**messages 中每条消息的格式:**

| role | content 格式 | 说明 |
|------|-------------|------|
| `user` | string 或 `[{type: "text", text: "..."}]` | 用户输入 |
| `assistant` | string 或 `[{type: "text", text: "..."}, {type: "tool_use", id, name, input}]` | 助手回复，可包含工具调用 |
| `user` (tool result) | `[{type: "tool_result", tool_use_id, content: "..."}]` | 工具执行结果（role 仍为 user） |

**tools 定义格式:**

```json
{
  "name": "read_file",
  "description": "Read a file...",
  "input_schema": {
    "type": "object",
    "properties": { "path": {"type": "string"} },
    "required": ["path"]
  }
}
```

### 2.2 响应

**成功响应 (200):**
```json
{
  "content": [
    {"type": "text", "text": "回复内容"},
    {"type": "tool_use", "id": "toolu_xxx", "name": "read_file", "input": {"path": "main.py"}}
  ]
}
```

**content 块类型:**

| type | 字段 | 说明 |
|------|------|------|
| `text` | `text` | 文本回复 |
| `tool_use` | `id`, `name`, `input` | 工具调用 |

**错误响应:**
| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误 |
| 401 | API Key 无效 |
| 429 | 速率限制 |
| 500 | 服务端错误 |

---

## 三、OpenAI Chat Completions API

### 3.1 请求

**Endpoint:** `POST {base_url}/v1/chat/completions`

**Headers:**
| Header | 说明 |
|--------|------|
| `Authorization` | `Bearer {api_key}` |
| `content-type` | `application/json` |

**请求体 (JSON):**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 模型名称 |
| `max_tokens` | integer | 否 | 最大生成 token 数 |
| `messages` | array | 是 | 对话消息列表 |
| `tools` | array | 否 | 工具定义列表 |
| `tool_choice` | string/object | 否 | 工具调用策略 |

**messages 中每条消息的格式:**

| role | 字段 | 说明 |
|------|------|------|
| `system` | `content` (string) | 系统提示词 |
| `user` | `content` (string) | 用户输入 |
| `assistant` | `content` (string, 可 null) + `tool_calls` (array, 可选) | 助手回复 |
| `tool` | `content` (string) + `tool_call_id` (string) | 工具执行结果 |

**tools 定义格式:**

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file...",
    "parameters": {
      "type": "object",
      "properties": { "path": {"type": "string"} },
      "required": ["path"]
    }
  }
}
```

**assistant.tool_calls 格式:**

```json
{
  "id": "call_xxx",
  "type": "function",
  "function": {
    "name": "read_file",
    "arguments": "{\"path\": \"main.py\"}"
  }
}
```

> 注意: OpenAI 的 `arguments` 是 **JSON 字符串**，不是对象。

### 3.2 响应

**成功响应 (200):**
```json
{
  "choices": [
    {
      "message": {
        "content": "回复内容",
        "tool_calls": [
          {
            "id": "call_xxx",
            "type": "function",
            "function": {
              "name": "read_file",
              "arguments": "{\"path\": \"main.py\"}"
            }
          }
        ]
      }
    }
  ]
}
```

---

## 四、核心差异对比

| 维度 | Anthropic | OpenAI |
|------|-----------|--------|
| **Endpoint** | `/v1/messages` | `/v1/chat/completions` |
| **认证** | `x-api-key` header | `Authorization: Bearer` header |
| **系统提示** | 顶层 `system` 字段 | `messages` 中 `role: "system"` 的消息 |
| **工具定义** | 直接在 tools 数组中 | tools 数组中每项有 `type: "function"` 包装 |
| **工具参数** | `input_schema` | `function.parameters` |
| **工具调用** | content 块 `type: "tool_use"` | `message.tool_calls` 数组 |
| **工具结果** | user 消息中 `type: "tool_result"` 块 | `role: "tool"` 消息 + `tool_call_id` |
| **工具参数类型** | JSON 对象 (`input`) | JSON 字符串 (`arguments`) |
| **thinking 支持** | 支持 `thinking` content block | 不支持原生 thinking block |

---

## 五、本项目中的转换流程

```
用户输入
  │
  ▼
AgentLoop.run(user_message)
  │
  ├── 构建内部 Message(role="user", content=...)
  ├── 构建工具 schema (BaseTool.to_schema())
  │
  ▼
client.chat(messages, tools, max_tokens)
  │
  ├── AnthropicClient: 内部 Message → Anthropic content blocks
  │   └── POST /v1/messages
  │       └── 解析 content blocks → AssistantResponse
  │
  └── OpenAIClient: 内部 Message → OpenAI message format
      └── POST /v1/chat/completions
          └── 解析 choices[0].message → AssistantResponse
  │
  ▼
如果有 tool_calls:
  ├── 执行工具 (AgentLoop 中按 name 查找并执行)
  ├── 将结果追加到 messages
  └── 循环，直到无 tool_calls 或达到 MAX_ITERATIONS(25)
  │
  ▼
返回最终文本回复
