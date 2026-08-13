# Documents & Files

## Table of Contents
- [Document Libraries](#document-libraries)
- [Documents](#documents)
- [Files](#files)

---

## Document Libraries

### List Doc Libraries

**`GET /doclibs`**

| Param | Type | Description |
|---|---|---|
| type | string | Library type (`product`, `project`, `execution`, `custom`, `mine`) |
| objectID | int | Object ID for the type |
| extra | string | Extra filter |
| appendLibs | bool | Append additional libraries |

```bash
# List all doc libraries
curl -s "${ZENTAO_URL}/api.php/v1/doclibs" \
  -H "Token: ${TOKEN}"

# List libraries for a product
curl -s "${ZENTAO_URL}/api.php/v1/doclibs?type=product&objectID=1" \
  -H "Token: ${TOKEN}"
```

---

## Documents

### List Documents in Library

**`GET /docs`** or **`GET /doclibs/:id`**

| Param | Type | Description |
|---|---|---|
| lib | int | Required — Library ID |

Returns document tree for the specified library.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/doclibs/1" \
  -H "Token: ${TOKEN}"
```

### Get Document

**`GET /docs/:id`**

Returns document with files and library name.

```bash
curl -s "${ZENTAO_URL}/api.php/v1/docs/1" \
  -H "Token: ${TOKEN}"
```

### Delete Document

**`DELETE /docs/:id`**

```bash
curl -s -X DELETE "${ZENTAO_URL}/api.php/v1/docs/1" \
  -H "Token: ${TOKEN}"
```

---

## Files

### Upload File

**`POST /files`**

Upload a file attachment. Uses multipart form data.

| Param | Type | Description |
|---|---|---|
| uid | string | Upload unique ID |

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v1/files" \
  -H "Token: ${TOKEN}" \
  -F "files=@/path/to/file.pdf" \
  -F "uid=unique-upload-id"
```

### 直接关联对象的附件上传（官方 v2，推荐）

禅道官方文档中，**上传并关联**到用例/缺陷/需求等对象时，应使用 **`POST /api.php/v2/files`**（与 v1 的「仅上传 uid」流程不同）。

- **URL**：`{ZENTAO_URL}/api.php/v2/files`
- **请求头**：`Token: <token>`（与 v1 相同方式取 token：`POST /api.php/v1/tokens`）
- **请求体**：`multipart/form-data`
  - **`file`**：文件字段（表单文件，不是 JSON 路径字符串）
  - **`objectType`**：`testcase` | `bug` | `story` | `task` 等
  - **`objectID`**：对象数字 ID（例如用例 `390666`）

```bash
curl -s -X POST "${ZENTAO_URL}/api.php/v2/files" \
  -H "Token: ${TOKEN}" \
  -F "file=@/path/to/screenshot.png" \
  -F "objectType=testcase" \
  -F "objectID=390666"
```

成功时响应通常为 JSON，含 `status`（如 `success`）、`id`、`url` 等字段（以服务器版本为准）。说明出处：[禅道 API - 上传附件](https://www.zentao.net/book/api/post-files-2325.html)。

**请求头说明**：官方表格写作 `token`；多数实例与 v1 一致使用 **`Token: <session>`** 也可。若一种失败可换另一种试一次（以实例为准）。

**排错（通用）**：401 则检查账号密码或 token 过期（`GET /api.php/v1/ping`）。403/404 则检查对象权限与 `objectID`。

**排错（实例 pms.reolink.com.cn / 禅道 21.7.6 实测，2026-04）**：

1. **`POST .../api.php/v2/files` 返回 PHP 报错**（如 `the control file module/common/control.php not found`）：属于 **服务端 v2 路由/安装不完整或与当前部署方式不兼容**，不是客户端 multipart 写错。处理：**联系禅道运维**检查 `www/module/common` 是否齐全、API 入口与伪静态配置、版本补丁；修复前 REST 无法走官方 v2 上传。
2. **`POST .../api.php/v1/files` 固定返回** `{"error":" 文件上传失败，文件格式不在规定范围内"}`：即使用 **空 `.txt`、`.png`、`.zip`** 等仍相同，而 **同一账号在网页端可以给同一用例挂上 `.png` 附件**，则基本可判断为 **REST「上传文件」接口在该实例上未按预期开放或被额外策略拦截**，而非单纯后台「允许附件后缀」白名单问题。处理：仍由 **运维/二次开发**对照 `module/file` 相关 API 与 `file` 配置排查；在修复前改用 **网页用例详情页本地上传** 或 **浏览器自动化（携带网页 Session）** 作为变通。

### 网页「用例编辑」multipart 上传（REST 不可用时的变通）

与浏览器在「测试 → 用例 → 编辑」中保存一致：请求 **`POST /index.php?m=testcase&f=edit&caseID=<id>&comment=false&executionID=&from=testcase&zin=1`**，`Content-Type: multipart/form-data`，字段包含 `title`、`precondition`、`steps[n]`、`expects[n]`、`stepType[n]`、`product`、`module`、`branch`、`uid`、**`files[]`（文件）**、空占位 **`scriptFile`** 等（与浏览器抓包一致）。

- **登录**：禅道 21 + zin 下，网页登录需 **`POST /index.php?m=user&f=login&zin=1`**，密码为 **`md5(md5(明文密码) + verifyRand)`**，其中 `verifyRand` 来自 **`GET .../user/refreshRandom`**（先 `GET` 登录页以建立 Cookie）。仅用 `api.php/v1/tokens` 得到的 session **不能**替代网页 Cookie 访问 `index.php`。
- **上传批次 `uid`**：须与当前「编辑用例」页隐藏域 **`name="uid"`** 一致（脚本会先 `GET` 编辑页解析）；随机 `uid` 易导致附件不落库。
- **若保存后响应跳转到「修改密码」**（HTML 中含 `"rawMethod":"changepassword"`）：说明当前网页会话被策略拦截，用例**不会**保存。可 **先在浏览器完成改密**，或设置环境变量 **`ZENTAO_WEB_COOKIE`** 为浏览器已登录状态下复制的 **完整 Cookie 请求头**，再运行下方脚本（跳过脚本内登录）。

**本地脚本（不经过 MCP）**：

| 脚本 | 作用 |
|------|------|
| `scripts/upload_testcase_attachment.py` | 走 REST `v2/files` → `v1/files`；需 `ZENTAO_*`；在 REST 损坏的实例上会失败。 |
| `scripts/upload_testcase_via_edit_form.py` | 单用例附件：优先 **`file/ajaxUpload` + `imgFile`**（见上文），失败再整表 multipart；需 **`ZENTAO_WEB_COOKIE`**（或脚本内网页登录）；依赖 **`requests`**。 |
| `scripts/xmind_sync_attachments_by_module.py` | **批量**：从 XMind Zen（`content.json` + `resources/*.png`）提取带图节点，与 **`GET .../products/{id}/testcases?module=`** 下列出的用例标题做模糊匹配，再对每条用例 **`ajaxUpload`** 关联附件。环境变量同前，另可选 **`XMIND_PATH`**；支持 **`--dry-run`**、**`--min-score`**。匹配非 100% 准确，上传后请在禅道人工抽查。 |

**更新本技能的方式**：把你们实例上 **v2 响应原文 / v1 报错 JSON / 网页改密拦截** 等实测结论追加进本小节（或新建 `references/docs-files-troubleshooting.md` 并在本文件链接），便于 Agent 选用正确上传路径。

### Download File

**`GET /files/:id`**

```bash
curl -s "${ZENTAO_URL}/api.php/v1/files/1" \
  -H "Token: ${TOKEN}" \
  -o downloaded_file.pdf
```

### Update File (Unlink)

**`PUT /files/:id`**

| Field | Type | Description |
|---|---|---|
| uid | string | Upload UID |
| action | string | `remove` — unlink file from object |

```bash
curl -s -X PUT "${ZENTAO_URL}/api.php/v1/files/1" \
  -H "Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"action": "remove", "uid": "unique-upload-id"}'
```
