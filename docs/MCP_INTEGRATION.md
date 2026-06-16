# MCP 原生集成说明

最后更新日期：2026-06-16  
维护人：模镜团队

## 1. 概述

MCP（Model Context Protocol）是一套让 AI 应用通过标准协议连接外部工具、资源和上下文的机制。模镜当前实现的是 **stdio MCP Server 原生集成**：后端负责启动 MCP Server 子进程、建立官方 SDK 的 `ClientSession`，前端负责连接、展示工具 schema、渲染动态参数表单并执行工具。

架构图：

```text
┌─────────────────────────────┐
│ React /mcps                 │
│ - McpServerCard             │
│ - 动态 JSON Schema 参数表单 │
└──────────────┬──────────────┘
               │ HTTP REST
               ▼
┌─────────────────────────────┐
│ FastAPI /api/mcp/*          │
│ - 输入校验                  │
│ - 每 IP 连接限流            │
│ - session 生命周期管理      │
└──────────────┬──────────────┘
               │ 官方 mcp Python SDK
               ▼
┌─────────────────────────────┐
│ MCPClientManager            │
│ - stdio_client              │
│ - ClientSession             │
│ - list_tools / call_tool    │
│ - sandbox cwd               │
└──────────────┬──────────────┘
               │ stdio
               ▼
┌─────────────────────────────┐
│ MCP Server 子进程           │
│ npx / python / docker 等    │
└─────────────────────────────┘
```

安全默认值：

- 后端只接受 `list[str]` 形式的命令，不使用 shell。
- 拒绝 `;`、`&&`、`|`、重定向等 shell 特殊字符。
- 子进程工作目录固定为 `server/mcp/sandboxes/`。
- 每个 IP 每分钟最多建立 5 个 MCP 连接。
- session 存储在内存中，断开连接时清理 stdio 资源和子进程。

## 2. 如何添加新的 MCP Server

前端 MCP 项目数据位于：

```text
client/src/data/mcpProjects.ts
```

新增条目时保留现有字段，并在支持本地 stdio 启动时添加可选字段：

```ts
command: ["npx", "-y", "@example/mcp-server"]
```

示例：

```ts
{
  id: "filesystem-mcp",
  name: "Filesystem MCP",
  repoName: "modelcontextprotocol/servers",
  repoUrl: "https://github.com/modelcontextprotocol/servers",
  description: "把受控目录内的文件读写能力交给 AI。",
  readmeSummary: "官方 npm 包描述为 MCP server for filesystem access。",
  stars: 0,
  language: "TypeScript",
  updatedAt: "2026-06-16",
  installCommand: "npx -y @modelcontextprotocol/server-filesystem <allowed-directory>",
  installNote: "模镜后端会把工作目录限制在 server/mcp/sandboxes。",
  command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."],
  tags: ["官方示例", "文件系统", "沙盒工具"],
}
```

接入检查清单：

1. 确认包名真实存在，例如：

```bash
npm view @example/mcp-server version
```

2. 确认 MCP Server 支持 stdio。
3. 确认是否需要 API Key。需要密钥的 Server 不应把密钥写入 `command`，应改由后端环境变量白名单注入。
4. 确认工具列表能正常返回：

```bash
python server/mcp/test_manager.py
```

如果 MCP Server 只能通过远程 HTTP/SSE 使用，可以继续展示安装信息，但不要添加 `command` 字段，避免前端显示“连接”能力。

## 3. 后端 API 文档

### POST `/api/mcp/connect`

启动一个 stdio MCP Server，创建 session。

请求：

```bash
curl -X POST http://localhost:8000/api/mcp/connect \
  -H "Content-Type: application/json" \
  -d '{"server_command":["npx","-y","@playwright/mcp@latest"]}'
```

响应：

```json
{
  "session_id": "8f3d8d6cc4af4f5c9a3e7b0d0f0fd9a0",
  "tools_count": 5
}
```

常见错误：

| 状态码 | 含义 |
| --- | --- |
| 400 | 命令非法或 MCP Server 启动失败 |
| 429 | 每 IP 每分钟连接数超过 5 次 |

### GET `/api/mcp/{session_id}/tools`

获取 session 暴露的工具列表。

```bash
curl http://localhost:8000/api/mcp/<session_id>/tools
```

响应：

```json
{
  "tools": [
    {
      "name": "fetch",
      "description": "Fetch a URL",
      "inputSchema": {
        "type": "object",
        "properties": {
          "url": { "type": "string" }
        },
        "required": ["url"]
      }
    }
  ]
}
```

### POST `/api/mcp/{session_id}/call`

调用工具。

```bash
curl -X POST http://localhost:8000/api/mcp/<session_id>/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"fetch","arguments":{"url":"https://example.com"}}'
```

响应：

```json
{
  "content": [
    {
      "type": "text",
      "text": "Example Domain"
    }
  ],
  "is_error": false,
  "raw": {}
}
```

### DELETE `/api/mcp/{session_id}`

断开 session 并清理子进程。

```bash
curl -X DELETE http://localhost:8000/api/mcp/<session_id>
```

响应：

```json
{ "ok": true }
```

## 4. 前端组件说明

核心组件：

```text
client/src/components/McpServerCard.tsx
```

页面入口：

```text
client/src/pages/McpBrowserPage.tsx
```

状态流：

1. 初始状态为 `idle`。
2. 点击“连接”后进入 `connecting`，调用 `POST /api/mcp/connect`。
3. 连接成功后进入 `connected`，读取工具列表。
4. 对每个工具，根据 `inputSchema.properties` 动态生成表单：
   - `string` → 文本输入框。
   - `number` / `integer` → 数字输入框。
   - `boolean` → true/false 下拉。
   - `enum` → 下拉选择。
   - `object` / `array` → JSON 文本框。
5. 点击“执行”后调用 `/api/mcp/{session_id}/call`，结果使用 Markdown 区域展示。
6. 点击“断开连接”后调用 DELETE 并清理本地状态。

UI 状态要求：

- 连接中按钮禁用。
- 无 `command` 的项目显示“展示项目”，不可连接。
- API 失败时在卡片内展示错误。
- 未知 JSON Schema 字段不应导致页面崩溃。

## 5. 测试指南

安装依赖：

```bash
python -m pip install -r server/requirements.txt
```

运行集成测试：

```bash
python -m pytest server/tests/test_mcp_integration.py -q
```

测试覆盖：

- 成功启动本地 mock MCP Server。
- 获取工具列表。
- 调用 `fetch` 工具并验证返回 `Example Domain`。
- 错误命令启动失败。
- shell 特殊字符拒绝。
- 每 IP 连接限流。

本地 smoke 测试：

```bash
python server/mcp/test_manager.py
```

注意：`test_manager.py` 默认使用公开 npm MCP Server，可能受 npm registry 或网络影响。CI 和常规回归应优先使用 `server/tests/mock_mcp_server.py`。

## 6. 相关文件

| 文件 | 说明 |
| --- | --- |
| `server/mcp/manager.py` | MCPClientManager，负责 stdio session 生命周期。 |
| `server/mcp/test_manager.py` | 外部 fetch server smoke 脚本。 |
| `server/tests/mock_mcp_server.py` | 本地 mock MCP Server。 |
| `server/tests/test_mcp_integration.py` | FastAPI MCP 端点集成测试。 |
| `client/src/components/McpServerCard.tsx` | 前端连接、工具表单、执行结果组件。 |
| `client/src/data/mcpProjects.ts` | MCP 项目与可选 stdio 命令数据。 |
