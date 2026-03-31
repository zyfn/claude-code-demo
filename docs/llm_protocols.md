# LLM API Protocols: Anthropic vs OpenAI

本文档为独立协议说明，不依赖任何特定项目实现。重点覆盖：

- 基础请求/响应规范
- 工具调用（Function Calling）格式
- 流式输出（SSE）差异
- 错误码与重试策略
- 最小可运行示例（curl）

---

## 1. Scope and Notes

- 本文主要对比：
  - Anthropic `Messages API` (`/v1/messages`)
  - OpenAI `Chat Completions API` (`/v1/chat/completions`)
- OpenAI 另有较新的 `Responses API`；本文末附简要对照，避免与 `chat/completions` 混淆。
- 不同模型、时间点可能出现字段演进，请以官方文档为准。本文用于工程落地时的统一认知。

---

## 2. Quick Comparison

| 维度 | Anthropic | OpenAI (Chat Completions) |
|---|---|---|
| Endpoint | `POST /v1/messages` | `POST /v1/chat/completions` |
| 认证头 | `x-api-key` + `anthropic-version` | `Authorization: Bearer <key>` |
| 系统提示词 | 顶层 `system` | `messages` 中 `role: "system"` |
| 消息输入 | `messages[]` + block 风格 content | `messages[]` |
| 工具定义 | `tools[].input_schema` | `tools[].function.parameters` |
| 工具调用输出 | `content[]` 中 `tool_use` block | `message.tool_calls[]` |
| 工具结果回传 | `role: "user"` + `tool_result` block | `role: "tool"` + `tool_call_id` |
| 工具参数类型 | 常见为 JSON 对象 | 常见为 JSON 字符串（需反序列化） |
| 流式 | SSE 增量事件（Anthropic 事件类型） | SSE `chat.completion.chunk` 增量 |

---

## 3. Anthropic Messages API

## 3.1 Endpoint and Headers

- URL: `https://api.anthropic.com/v1/messages`
- Method: `POST`
- Headers:
  - `x-api-key: <ANTHROPIC_API_KEY>`
  - `anthropic-version: 2023-06-01`
  - `content-type: application/json`

## 3.2 Request Body (Common Fields)

- `model` (string, required): 模型名
- `max_tokens` (integer, required): 最大输出 token
- `system` (string or content blocks, optional): 系统提示词
- `messages` (array, required): 历史对话
- `tools` (array, optional): 工具定义
- `temperature`, `top_p` (optional)
- `stream` (boolean, optional): 是否流式

### messages 示例

```json
[
  { "role": "user", "content": "帮我查询北京天气" },
  {
    "role": "assistant",
    "content": [
      { "type": "text", "text": "我来帮你查询。" },
      { "type": "tool_use", "id": "toolu_123", "name": "get_weather", "input": { "city": "Beijing" } }
    ]
  },
  {
    "role": "user",
    "content": [
      { "type": "tool_result", "tool_use_id": "toolu_123", "content": "{\"temp\":22,\"condition\":\"sunny\"}" }
    ]
  }
]
```

## 3.3 Tools Schema

```json
{
  "name": "get_weather",
  "description": "Get weather by city",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": { "type": "string" }
    },
    "required": ["city"]
  }
}
```

## 3.4 Response Body (Typical)

```json
{
  "id": "msg_...",
  "model": "claude-...",
  "content": [
    { "type": "text", "text": "北京当前晴，22 摄氏度。" }
  ],
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 123,
    "output_tokens": 45
  }
}
```

当模型决定调用工具时，`content` 会包含 `type: "tool_use"` block。

---

## 4. OpenAI Chat Completions API

## 4.1 Endpoint and Headers

- URL: `https://api.openai.com/v1/chat/completions`
- Method: `POST`
- Headers:
  - `Authorization: Bearer <OPENAI_API_KEY>`
  - `Content-Type: application/json`

## 4.2 Request Body (Common Fields)

- `model` (string, required)
- `messages` (array, required)
- `max_tokens`（部分模型/版本可能使用 `max_completion_tokens`）
- `temperature`, `top_p` (optional)
- `tools` (array, optional)
- `tool_choice` (string/object, optional)
- `stream` (boolean, optional)

### messages 示例

```json
[
  { "role": "system", "content": "You are a helpful assistant." },
  { "role": "user", "content": "帮我查询北京天气" },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_abc",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"city\":\"Beijing\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_abc",
    "content": "{\"temp\":22,\"condition\":\"sunny\"}"
  }
]
```

## 4.3 Tools Schema

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get weather by city",
    "parameters": {
      "type": "object",
      "properties": {
        "city": { "type": "string" }
      },
      "required": ["city"]
    }
  }
}
```

## 4.4 Response Body (Typical)

```json
{
  "id": "chatcmpl_...",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "北京当前晴，22 摄氏度。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 40,
    "total_tokens": 160
  }
}
```

---

## 5. Input/Output Mapping for Tool Calling

## 5.1 Anthropic Tool Loop

1. 发起请求（含 `tools`）
2. 检查响应 `content[]` 是否有 `tool_use`
3. 执行本地函数
4. 将结果作为 `tool_result` block 回传（`role` 为 `user`）
5. 再次请求，直到返回纯文本或达到循环上限

## 5.2 OpenAI Tool Loop

1. 发起请求（含 `tools`）
2. 检查 `choices[0].message.tool_calls`
3. 执行本地函数
4. 追加 `role: "tool"` 消息，携带 `tool_call_id`
5. 再次请求，直到无 `tool_calls`

---

## 6. Streaming (SSE) Differences

- 两家都支持 SSE，但增量事件格式不同。
- Anthropic 常见事件语义是内容块级别增量；OpenAI `chat.completions` 常见是 `choices[].delta` 逐步补全文本或工具参数。
- 工程建议：
  - 分别实现解码器，不要共用一个 JSON 路径假设。
  - 流式期间缓存增量，结束后组装为统一内部结构。
  - 对工具调用参数做完整性校验（尤其 OpenAI 的 arguments 字符串拼接阶段）。

---

## 7. Error Codes and Retry Strategy

常见状态码：

- `400`: 参数错误（字段、schema、类型不匹配）
- `401`: 鉴权失败（key 无效/缺失）
- `403`: 权限不足（模型权限、组织策略）
- `404`: 路径或模型不存在
- `429`: 限流
- `5xx`: 服务端或网关错误

建议重试策略：

- 仅对 `429`、`5xx` 自动重试
- 使用指数退避 + 抖动（例如 1s, 2s, 4s, 8s, 随机 0-300ms）
- 记录关键观测字段：请求 ID、模型名、耗时、token 用量、finish reason

---

## 8. Common Pitfalls

- OpenAI `function.arguments` 可能是字符串化 JSON，需要显式反序列化。
- `content` 为空不代表失败：可能是“仅工具调用”回合。
- 工具 schema 与实际函数签名不一致时，模型会稳定地产生无效参数。
- 历史消息角色拼装错误会导致上下文错乱（尤其 `tool`/`tool_result` 轮次）。
- 不同模型支持能力不同（图像、音频、并行工具调用），不要把“某个模型行为”当成“接口通用行为”。

---

## 9. Minimal curl Examples

## 9.1 Anthropic (Text)

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 512,
    "system": "You are a concise assistant.",
    "messages": [
      {"role":"user","content":"Explain TCP 3-way handshake briefly."}
    ]
  }'
```

## 9.2 OpenAI (Text)

```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role":"system","content":"You are a concise assistant."},
      {"role":"user","content":"Explain TCP 3-way handshake briefly."}
    ],
    "max_tokens": 512
  }'
```

---

## 10. Optional: OpenAI Responses API (One-Paragraph Note)

`/v1/responses` 是 OpenAI 的新一代统一接口，目标是统一多模态、工具、输出控制与跟踪能力。若是新系统可优先评估 `responses`；若是兼容大量既有 SDK/中间件，`chat/completions` 仍是常见选择。迁移时建议先做字段映射层（message 转换、tool call 适配、usage 统计统一）。

---

## 11. Recommended Internal Abstraction

如需同时支持 Anthropic 与 OpenAI，建议内部统一为：

- `Message { role, content }`
- `ToolCall { id, name, arguments(object) }`
- `AssistantResponse { text, tool_calls[], raw }`

然后分别实现：

- Provider Request Mapper（内部 -> 外部）
- Provider Response Parser（外部 -> 内部）
- Streaming Decoder（provider-specific）
- Error Normalizer（provider-specific -> internal error codes）

这样可以最小化上层 Agent/Workflow 对供应商差异的感知。
