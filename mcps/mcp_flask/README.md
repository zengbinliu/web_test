# Flask MCP Server

这是一个基于 `Flask` 的最小可运行 MCP 服务器示例，适合在当前目录直接启动，并接入 Cursor。

当前实现了 Cursor 常用的 MCP 基础握手和会话流程：

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`
- `resources/list`
- `prompts/list`

内置示例工具：

- `echo`
- `add_numbers`
- `server_time`
- `askreolink`：调用本机 `D:\reolink_knowledge\ask_reolink_testcase_kb.py`，检索 Reolink 禅道测试用例知识库（与你在终端里 `python ... "问题"` 的行为一致）。其他用户连上该 MCP 后，在对话里让模型调用工具 `askreolink` 并传入 `query` 即可查询业务逻辑。
- `askcamovue`：调用本机 `C:\Users\Reolink\.cursor\ask_camovue_kb.py`，检索 Camovue 云服务套餐本地知识库（与终端 `python ... "问题" [--top N] [--full]` 一致）。传入 `query`，可选 `top`（默认 3）、`full`。

环境变量（可选）：

- `ASKREOLINK_SCRIPT`：知识库脚本路径，默认 `D:\reolink_knowledge\ask_reolink_testcase_kb.py`
- `ASKREOLINK_PYTHON`：解释器路径，默认使用当前运行 Flask 的 `sys.executable`
- `ASKREOLINK_TIMEOUT`：单次查询超时秒数，默认 `120`，最大 `600`
- `ASKCAMOVUE_SCRIPT`：Camovue 知识库脚本路径，默认 `C:\Users\Reolink\.cursor\ask_camovue_kb.py`
- `ASKCAMOVUE_PYTHON`：解释器路径，默认与 `ASKREOLINK_PYTHON` 规则相同（当前 Flask 进程的 `sys.executable`）
- `ASKCAMOVUE_TIMEOUT`：单次查询超时秒数，默认 `120`，最大 `600`

支持的协议版本：

- `2025-11-25`
- `2025-06-18`

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 启动服务

```bash
python app.py
```

默认监听地址：

- `http://127.0.0.1:5000/`
- MCP 端点：`http://127.0.0.1:5000/mcp`

## 3. 接入 Cursor

项目里已经提供了 `.cursor/mcp.json`，内容如下：

```json
{
  "mcpServers": {
    "flask-mcp-local": {
      "url": "http://127.0.0.1:5000/mcp"
    }
  }
}
```

使用方式：

1. 先执行 `python app.py`
2. 完全重启 Cursor
3. 打开项目后，在 MCP / Tools 里确认 `flask-mcp-local` 已加载

说明：

- 这份配置使用 `url` 方式接入，所以 Flask 服务需要先启动
- 当前没有实现 SSE 推送，因此 `GET /mcp` 返回 `405` 是正常的
- Cursor 仍然可以通过 `POST /mcp` 正常完成初始化和工具调用

## 4. 健康检查

```bash
curl http://127.0.0.1:5000/healthz
```

## 5. MCP 调用示例

下面是一个 PowerShell 示例，演示初始化后再调用 `tools/list`：

```powershell
$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0.0"}}}'
$initResp = Invoke-WebRequest -Uri "http://127.0.0.1:5000/mcp" -Method POST -ContentType "application/json" -Body $initBody
$sessionId = $initResp.Headers["MCP-Session-Id"]

$headers = @{
  "MCP-Session-Id" = $sessionId
  "MCP-Protocol-Version" = "2025-11-25"
}

$toolsListBody = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
Invoke-RestMethod -Uri "http://127.0.0.1:5000/mcp" -Method POST -Headers $headers -ContentType "application/json" -Body $toolsListBody
```

## 6. 运行测试

```bash
python -m unittest discover -s tests
```

## 7. 自定义说明

如果你要增加自己的 MCP 工具，只需要在 `app.py` 里继续使用 `@register_tool(...)` 注册即可。

如果后续你准备升级到 Python 3.10 及以上，可以再切换到官方 `mcp` SDK 版本，补齐更完整的 SSE / Streamable HTTP 能力。
