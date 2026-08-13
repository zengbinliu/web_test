# zentao-mcp 工具参数摘要

以下内容根据 Cursor 缓存的 MCP 描述符整理；若与线上服务不一致，以 **`.cursor/projects/*/mcps/user-zentao-mcp/tools/*.json`** 为准。

---

## zentao_testcase_get

- **必填**：`id`（integer）
- **可选**：`version`（integer，0=最新）

---

## zentao_testcase_search

- **必填**：`product`（integer）
- **可选**：`branch`（string）、`status`（draft | normal | blocked | deprecated）、`module`（integer）、`caseType`（feature | performance | unit | system | interface | config）、`order`、`limit`、`page`、`keyword`、`scanPages`

---

## zentao_testcase_create

- **必填**：`product`、`title`、`type`（feature | performance | unit | system | interface | config）、`pri`、`steps`（数组，每项至少 `desc`；可选 `expect`、`type` step|group、`name`、`id`）
- **可选**：`module`、`stage`（unit | integration | system | acceptance）、`precondition`

---

## zentao_testcase_update

- **必填**：`id`
- **可选**：`title`、`pri`（number|string）、`stage`（unit|integration|system|acceptance）、`steps`（**覆盖**原步骤；项内 `desc` 必填，可选 `expect`、`type` step|group、`name`、`id`）、`files`（附件数组，binary；具体字段名、是否多文件以 **缓存 tools JSON** 为准）

> 团队习惯：更新时尽量带齐标题、优先级、阶段与完整步骤，避免半量更新导致语义丢失。

### 附件说明（MCP 与禅道 21 实例）

- MCP 的 **`files`** 最终仍依赖禅道服务端对「上传/关联附件」的实现；若调用成功但页面上 **仍无附件**，或实例上 **REST `v2/files`、`v1/files` 已确认不可用**，请勿反复猜测 multipart 字段名；应改走 **`zentao-api`** 技能：
  - 脚本：`zentao-api/scripts/upload_testcase_via_edit_form.py`
  - 禅道 **21+ 网页** 实测：附件直传接口为 **`index.php?m=file&f=ajaxUpload`**，文件字段 **`imgFile`**，URL 参数 **`objectType=testcase`**、**`objectID=<用例id>`**，并需与编辑页同一浏览器会话中的 **`uid`**（隐藏域）；该脚本在提供 **`ZENTAO_WEB_COOKIE`** 时会 **优先 ajaxUpload**，详见 **`zentao-api/references/docs-files.md`**。
- 用户要求 **不走 MCP** 时：不要用本表替代脚本；按 **`zentao-api`** 文档设置 **`ZENTAO_URL`、`ZENTAO_ACCOUNT`、`ZENTAO_PASSWORD`、`ZENTAO_WEB_COOKIE`** 后执行脚本即可。

---

## zentao_parse_testcase_link

- **必填**：`url`（URI）— 禅道用例浏览链接

---

## zentao_bug_get

- **必填**：`id`（Bug ID）

---

## zentao_bug_search

- **必填**：`product`
- **可选**：`branch`、`status`（active | resolved | closed | all）、`module`、`order`、`limit`、`page`、`keyword`、`scanPages`

---

## zentao_bug_create

- **必填**：`product`、`title`、`severity`（1–4）、`pri`（1–4）、`type`（codeerror | design | designdefect | config | install | security | performance | standard | automation | others）
- **可选**：`module`、`branch`、`execution`、`keywords`、`os`、`browser`、`steps`（string）、`task`、`story`、`deadline`、`openedBuild`（string 数组）

---

## zentao_bug_transition

- **必填**：`id`、`action`（assign | resolve | close | active | confirm）、`payload`（object，按动作传字段，如 `assignedTo`、`comment`、`resolution` 等）
- **注意**：`action=active` 时 `payload` 需含 **`openedBuild`**

---

## zentao_parse_bug_link

- **必填**：`url` — Bug 详情链接（支持 bugID / id 参数）

---

## zentao_parse_bug_browse_link

- **必填**：`url` — Bug 列表浏览链接

---

## zentao_user_list

- **可选**：`query`（姓名/账号关键词）、`full`（0 精简，1 完整含 id）、`limit`、`page`

---

## MCP 配置说明（不含密钥）

全局配置路径：`~/.cursor/mcp.json`。字段 `mcpServers.zentao-mcp` 含 `url` 与 `headers`（如 `x-zentao-username` / `x-zentao-password`）。**勿**将 headers 内容提交到 Git 或粘贴进技能 Markdown。
