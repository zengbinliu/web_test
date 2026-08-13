---
name: zentao-mcp
description: >-
  Invokes the configured zentao-mcp MCP server for ZenTao testcases and bugs
  (create/update/search/get, link parsing, bug transitions, user lookup). Use
  when the user mentions ZenTao MCP, zentao-mcp, 禅道 MCP, creating or updating
  test cases or bugs via MCP, parsing testcase/bug URLs, or assigning bugs in
  Reolink PMS workflows. Prefer MCP over REST when MCP is available.
---

# 禅道 MCP（zentao-mcp）技能

## 前置条件

- Cursor 已配置 MCP 服务器 **`zentao-mcp`**（见 `~/.cursor/mcp.json`）。认证由 MCP 的 **`headers`** 提供，**禁止**将账号密码写入本技能或仓库正文。
- 调用 MCP 前：若不确定工具参数，先读 Cursor 缓存的 JSON Schema：工作区下 `.cursor/projects/*/mcps/user-zentao-mcp/tools/<工具名>.json`（随 Cursor 同步更新）。

## 使用原则

1. **优先使用 MCP**：用户未声明「不用 MCP」时，禅道用例/缺陷的查、搜、建、改、状态流转应优先走 **MCP 工具**，而非手写 REST。
2. **先读后写**：修改用例前用 **`zentao_testcase_get`** 拉全量；修改 Bug 前用 **`zentao_bug_get`**。
3. **链接解析**：用户提供禅道列表/详情 URL 时，先用 **`zentao_parse_testcase_link`** / **`zentao_parse_bug_link`** / **`zentao_parse_bug_browse_link`** 提取 `product`、`module`、`bugId` 等再搜索或操作。
4. **指派与抄送**：需要 `assignedTo`、`mailto` 等账号字段时，先 **`zentao_user_list`**（`full=1` 可取 id），再调用创建/流转接口。

## 团队约定（与 MCP 参数对齐）

- **测试用例**：步骤与预期须 **一一对应**（每条 `desc` 有对应 `expect`）；条数一致、因果关系清晰。
- **更新用例 `zentao_testcase_update`**：除 `id` 外，若执行「实质性修改」，应同时给出 **`title`、`pri`、`stage`（如适用）、完整 `steps`**；若需附件则传 **`files`**（以 MCP 工具 schema 为准）。避免只改标题而丢失步骤语义。若 **`files` 上传后服务端仍无附件**（实例 REST/网关异常等），见下文「附件上传」改用 **`zentao-api`** 或浏览器。
- **Bug 激活 `zentao_bug_transition`（`action=active`）**：`payload` 须含 **`openedBuild`**（如 `[\"主干\"]`），否则禅道会报影响版本为空。

## 工具一览（服务器 `zentao-mcp`）

| 工具名 | 用途 |
|--------|------|
| `zentao_testcase_get` | 用例详情 |
| `zentao_testcase_search` | 用例分页/关键词搜索 |
| `zentao_testcase_create` | 新建用例 |
| `zentao_testcase_update` | 更新用例（含步骤覆盖、附件） |
| `zentao_parse_testcase_link` | 解析用例列表 URL → 筛选参数 |
| `zentao_bug_get` | Bug 详情（含 actions/评论） |
| `zentao_bug_search` | Bug 分页/关键词搜索 |
| `zentao_bug_create` | 新建 Bug |
| `zentao_bug_transition` | 指派/解决/关闭/激活/确认 |
| `zentao_parse_bug_link` | 解析 Bug 详情 URL → bugId |
| `zentao_parse_bug_browse_link` | 解析 Bug 列表 URL → 筛选参数 |
| `zentao_user_list` | 用户搜索（指派前建议调用） |

各字段类型、枚举、必填项以 **缓存 JSON** 为准；汇总表见 [reference.md](reference.md)。

## 与 REST 技能的关系

- 需要 **REST API 路径、curl、网页上传附件（含禅道 21 实测路径）** 等：使用个人技能 **`zentao-api`**（`~/.cursor/skills/zentao-api/`），脚本见该技能下 `scripts/`。
- 本技能仅覆盖 **MCP 已暴露** 的能力；MCP 未提供的操作仍用网页或 REST。

## 附件上传（与 MCP 分工）

| 场景 | 建议 |
|------|------|
| 用户 **允许 MCP**，且 `zentao_testcase_update` 的 **`files`** 可成功 | 继续用 MCP，步骤与 `files` 以工具 JSON 为准。 |
| 用户 **声明不用 MCP**，或需 **绕过网页改密/仅用浏览器会话** | 用 **`zentao-api`**：`scripts/upload_testcase_via_edit_form.py`，环境变量 **`ZENTAO_WEB_COOKIE`**（从已登录浏览器复制整段 Cookie）。 |
| 实例上 **`api.php/v2/files` / `v1/files` 不可用**（与 `zentao-api` 中 `docs-files.md` 排错一致） | **不要**指望仅靠损坏的 REST 上传；用 **网页会话** + 下方「禅道 21 网页附件真实入口」。 |

**禅道 21+ 网页端（pms 等实例实测）**：用例附件并非依赖「编辑用例」整表 multipart 里的 **`files[]`** 即可完成落库；源码为 **`module/file/control::ajaxUpload`**。正确做法是：先打开编辑页取得隐藏域 **`uid`**，再 **`POST .../index.php?m=file&f=ajaxUpload&uid=...&objectType=testcase&objectID=<用例ID>`**，表单文件字段名为 **`imgFile`**（默认值，与源码一致）。**`zentao-api`** 中 `upload_testcase_via_edit_form.py` 已 **优先走 ajaxUpload**，失败时再回退整表 multipart；Referer 中 **`version`** 与用例 **`currentVersion`** 对齐。详细排错与 curl 说明见 **`zentao-api/references/docs-files.md`**。

## 维护方式

当 MCP 服务端升级、增减工具时：

1. 在任意已连接 MCP 的 Cursor 工作区打开 `.cursor/projects/.../mcps/user-zentao-mcp/tools/` 对比变更。
2. 更新本目录下的 [reference.md](reference.md) 与上表「工具一览」。
3. 若 **`zentao_testcase_update` 的 `files`** 或与 **`zentao-api`** 联动的附件链路上有实测结论变更，同步修订上文「**附件上传（与 MCP 分工）**」及 `reference.md` 中 **`zentao_testcase_update` → 附件说明** 小节。
4. 勿将 `mcp.json` 中的密钥复制进技能文件。
