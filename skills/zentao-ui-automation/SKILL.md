---
name: zentao-ui-automation
description: >-
  Generates and debugs automation scripts for official_website_server from ZenTao
  testcase IDs. API-first: call Reolink/backend APIs for business logic and data
  prep; use Playwright UI only for page display validation and payment flows.
  **Must actively execute precondition setup via RAG APIs** (e.g. always purchase
  cloud plan — never skip by checking if one already exists). Reuse Setup outputs
  in steps (assert-only, no duplicate operations). Default deliverable: Flask route
  + payload JSON. askreolink via MCP first. **Debug via phased protocol** (Phase
  A–D: static → setup_only → skip_setup/from_step → one full regression); forbid
  3+ consecutive full curls with PayPal Setup. Cloud UI locator timeout: optional
  debug.healing (LLM + YAML persist in Phase C). After pass, **mandatory step 8**
  (throttled): categorize issues, update skill/examples, merge supplemental RAG,
  batch rebuild index. Use when the user gives a 禅道用例 ID, asks to generate
  automation, official_website_server scripts, or zentao-to-playwright/API workflow.
---

# 禅道用例 → 自动化脚本（接口为主、UI 为辅）

将禅道测试用例转化为 `official_website_server` 项目内的自动化脚本。**优先调用 Reolink / 后台接口**；仅当步骤涉及**页面展示验证**或**支付交互**时，才使用 Playwright UI。

**项目根目录**：`D:/web_1151/05测试数据与脚本/自动化/official_website_server`

## 快速决策卡（编写前 30 秒）

```
禅道用例 ID → zentao-mcp zentao_testcase_get
    ↓
precondition → Setup（主动构造，见 reference）→ 复用 Setup 产出执行 steps
    ↓
每条 step/expect：
  数据正确性？ → API 断言
  页面可见/支付？ → UI 或混合（API 主断言 + UI 抽样）
  已有封装？ → Grep + [Setup 索引](reference.md#setup-封装与通用模式索引)
    ↓
交付：Flask 路由 + data/*/payload_<场景>_<用例ID>.json（默认）
RAG：MCP askreolink 优先 → 不可用再 Shell（见下文）
  └─ 拿到禅道用例后 **必做第二次检索**：`<ID> 接口自动化 jmx`（JMX 历史脚本 API 序列，见下文）
调试：Phase A 静态 → B setup_only → C skip_setup/from_step → D 全量 1 次（见下文）
失败：判断 Setup/steps 阶段 → [失败决策树](reference.md#失败排查决策树) → steps[] / error_screenshot_path
```

| 判断 | 选 |
|------|-----|
| 登录取 token / 解绑 / 数据准备 | **API** `CloudApiUtils` / `DeviceDataService` |
| 已购付费云套餐 Setup | **混合** `CloudPurchaseSetupFlow` + `CloudPurchaseUtils`（PayPal） |
| 订阅/订单**数据** | **API** OpenAPI + validator |
| 订阅/订单**页面** | **混合** API 主断言 + UI 抽样 |
| checkout / 支付 | **UI** Strategy + iframe |
| Store 文案/元素 | **UI** Page Object + YAML |
| Cloud UI 定位 timeout | **先** wait/iframe → **再** `debug.healing` 或改 YAML → Phase D 关 persist |
| 纯接口场景 | **勿**建 Page Object / YAML / BrowserSession |

## 核心原则

| 优先级 | 手段 | 适用场景 |
|--------|------|----------|
| **1 — 接口** | `CloudApiUtils`、Flask 纯 API、`requests` | 登录、解绑、计算、邮件校验、数据断言、Setup |
| **2 — UI** | Playwright + Page Object + YAML | 页面可见性、checkout 支付 |
| **3 — 混合** | API 取数 + UI 抽样 | 数据正确且页面可见 |

**编写前必做**：① MCP/Shell RAG ② Grep 项目封装 ③ 输出前提+步骤选型表（模板见 [reference.md](reference.md)）④ 确认交付物形态（见下文）。

## 前提条件（Setup）摘要

禅道 **`precondition` 必须主动执行**，不是说明文字。完整规则、映射表、代码正反例见 [reference.md — 常见前提条件](reference.md#常见前提条件--api--实现映射) 与 [Setup 封装索引](reference.md#setup-封装与通用模式索引)。

**核心**：主动构造，禁止「先查有数据则跳过 Setup」。查询 API **仅用于 Setup 执行后的校验**。

**复用封装**：付费云套餐优先 `CloudPurchaseSetupFlow.purchase_paid_cloud_plan`（当前 **PayPal + 付费套餐**，禅道 186294）；勿在 Service 内重写购买链路。

```python
# Phase 0: Setup
token = CloudApiUtils.login(...)
plan_ctx = CloudPurchaseSetupFlow(steps_logger=...).purchase_paid_cloud_plan(session, page, token, args)
# Phase 1+: steps 复用 plan_ctx，见「前提与 steps 去重」
```

## 前提与 steps 去重

当 **steps 与 precondition 语义重复**（如都有「登录」「购买套餐」）时：

| 规则 | 说明 |
|------|------|
| Setup 负责构造 | 登录、购买、绑设备等**写操作只在 Setup 执行一次** |
| steps 保留 logger | 每条禅道 `desc` 仍有 `steps_logger`，标注数据来源 |
| steps 只做校验/展示 | 复用 Setup 产出（token、`plan_ctx`、`order_id`），**不重复** login/purchase/bind |
| 断言基准 | 必须针对**本次 Setup 构造的数据**，非账号历史数据 |

```python
# ✅ steps 中「登录」已由 Setup 完成
self._log("步骤1: 登录（复用 Setup token）")
assert token  # 或校验 session 已注入

# ✅ steps 中「查看订阅」— 用 plan_ctx 断言
self._log(f"步骤2: 查看当前订阅（Setup order_id={plan_ctx['order_id']}）")
self._verify_subscription_list(token, plan_ctx, args)

# ❌ Setup 已购买，steps 再次调用 purchase
self._purchase_cloud_plan(token, args)  # 重复构造
```

**编写前**：在步骤选型表增加列 **「与 Setup 重叠？→ 复用/仅断言」**。详见 [reference.md — 去重规则](reference.md#前提与-steps-去重)。

## Cloud UI 登录与 2FA（摘要）

凡 Cloud **浏览器登录 + 邮箱 2FA**，复用 `CloudLoginFlow` + `verify_code_providers.py`；请求体**透传** `get_code_type`，**默认 EmailManager**（IMAP），禁止 Service 内硬编码 `back`。

| `get_code_type` | 实现 |
|-----------------|------|
| 不传 / `email` / `EmailManager` | **EmailManager**（默认） |
| `back` / `mailproxy` | `get_verify_code_by_back` |

实现：`verify_code_providers.py`、`cloud_login_flow.py`。请求体模板与字段说明 → [reference.md — 2FA](reference.md#cloud-ui-登录与-2fa-收码)。

### 调试期登录快路径（优先于完整 2FA）

调试 steps/UI 时，按以下顺序取 token / session，**避免每次全走 Send Code**：

| 优先级 | 手段 | 适用 |
|--------|------|------|
| 1 | payload `access_token` / `cloud_access_token` | 纯 API steps、Setup 后 API 断言 |
| 2 | `cloud_token_storage.json` → 注入 `web_session_auth_code`（cloud + my 域） | 156689 / 262413 等已有账号 |
| 3 | PayPal 后 `extract_cloud_access_token_from_page`（localStorage / Cookie） | 186227 等支付后 API |
| 4 | `CloudLoginFlow.login_with_2fa` | 以上均不可用；新注册账号（186227）首次登录除外 |

**新注册账号**（`register_new_account: true`）Setup 阶段仍须完整注册链；**PayPal 后的 steps 调试**应复用已登录 session，勿重复注册。

## 分阶段调试协议（调试期强制）

**目标**：缩短迭代时间。生产交付（Phase D）仍须「主动构造」全量跑通；**调试期**允许 `debug` 块切片，与「禁止探测式 skip」不冲突。

```
Phase A — 静态校验（<30s，不进浏览器）
  Grep 封装 / YAML 语法 / payload 字段
  纯 API 步骤：直接调 CloudApiUtils 或单接口 curl

Phase B — Setup 隔离（1–15 min，视前提轻重）
  payload: { "debug": { "setup_only": true } }
  只跑 Setup，将 plan_ctx / token / order_id 写入 run_data
  建议落盘：data/cloud/debug_cache/payload_<场景>_<ID>_setup_ctx.json

Phase C — Steps 切片（跳过 Setup，修 UI/API 断言）
  payload: { "debug": { "skip_setup": true, "setup_ctx": { ... } } }
  或 { "debug": { "from_step": 3 } } 从失败步骤起跑
  调试默认：headless=true、slow_mo=0（见 debug 块模板）

Phase D — 全量回归（仅 Phase C 通过后 1 次）
  移除 debug 块或全部 false，验证端到端「主动构造」
```

| 规则 | 说明 |
|------|------|
| 禁止连续全量 | 修 steps/UI 时 **禁止** 连续 3 次以上全量 curl（含 PayPal Setup） |
| 卡步 >2 min | 立即 kill → 判断失败在 Setup 还是 steps → 选 Phase B 或 C |
| Phase B 未过不写 steps UI | Setup API 顺序/支付未稳前，勿在 Phase C 反复猜 UI |
| Phase D 最多 1 次 | 作为交付前验收，通过后进入第 8 步沉淀 |

重 Setup 用例策略表 → [reference.md — 重 Setup 场景](reference.md#重-setup-场景调试策略)。

## payload `debug` 块（标准模板）

交付用 payload **不含** `debug`；调试专用 payload 或同文件内追加 `debug` 对象。完整字段说明 → [reference.md — debug 块](reference.md#payload-debug-块)。

```json
{
  "zentao_case_id": 186227,
  "localhost": "http://127.0.0.1:5010/",
  "debug": {
    "setup_only": false,
    "skip_setup": false,
    "from_step": null,
    "setup_ctx": {},
    "setup_ctx_file": "data/cloud/debug_cache/payload_dashboard_186227_setup_ctx.json",
    "headless": true,
    "slow_mo": 0,
    "pause_on_fail": false,
    "trace_on_fail": true,
    "healing": {
      "enabled": false,
      "persist": true,
      "max_per_run": 5,
      "testcase_id": null
    }
  }
}
```

| 字段 | 用途 |
|------|------|
| `setup_only` | 只跑 Setup，输出 `setup_ctx` 到 `run_data` |
| `skip_setup` + `setup_ctx` / `setup_ctx_file` | 复用本次或上次 Setup 产出 |
| `from_step` | 从指定禅道步骤编号起跑（1-based） |
| `headless` / `slow_mo` | 调试期加速；定位器疑难时可 `headless: false` + `pause_on_fail` |
| `trace_on_fail` | 失败写 `trace.zip`，`playwright show-trace` 复盘 |
| `healing.*` | Cloud UI 定位自愈（见 [AI 元素自愈](#ai-元素自愈cloud-ui-定位失败phase-c-可选)） |

**Service 实现约定**（新场景须遵守）：在 `run()` 入口解析 `args.get("debug") or {}`；`setup_only` / `skip_setup` / `from_step` 分支置于 Setup 与 steps 之间。尚无统一基类时，复制同模块最近 Service 的 debug 分支。

## Playwright 调试工具（UI 步骤）

| 场景 | 手段 |
|------|------|
| 改定位器 | `debug.headless: false` + 代码内 `page.pause()` 或 `PWDEBUG=1 python ...` |
| 新页面结构 | `playwright codegen <url>` 生成初版选择器 → 写入 YAML |
| 偶发失败 | `context.tracing.start/stop` + `playwright show-trace trace.zip` |
| 失败快查 | 响应 `error_screenshot_path` + `logs/YYYY-MM-DD.log` + `steps[]` |
| Cloud 定位器过时 | Phase C 开 `debug.healing`（见下节） |

**禁止提交**：probe 脚本、`page.pause()` 调试残留、临时 `tmp_*.json` 全量结果。

### AI 元素自愈（Cloud UI 定位失败，Phase C 可选）

**适用范围**：`src/cloud/ui_pages` + `src/cloud/page_ele/front/<域>/*.yml` 的 Cloud Page Object（域：login/home/payment/dashboard/lock_card/payment_history）。  
**不适用**：纯 API 步骤、Website 模块、probe 脚本。

**原则**：自愈是 **YAML 定位失败后的自动兜底**，不替代编写前 probe/codegen；Phase D 全量通过前须 **人工 review** 被改写的 YAML。

#### 何时启用

| 场景 | 是否开自愈 | 说明 |
|------|------------|------|
| Phase C 修 UI 定位器 timeout | ✅ 建议 | 减少反复改 YAML + 重启 Flask |
| Phase A / 纯 API | ❌ | 无 Playwright 定位 |
| Phase B Setup（PayPal 等） | ⚠️ 慎用 | Setup 失败优先查业务链，非盲开自愈 |
| Phase D 交付验收 | ❌ 默认关 | 验收应基于稳定选择器；自愈改动须 review 后合入 |
| 首次编写新 Page | ❌ | 先 codegen / 读 error 截图定 marker，再写 YAML |

#### 配置（与 askreolink 同 API / Key）

| 文件 | 作用 |
|------|------|
| `src/cloud/ui_healing/llm.env` | LLM 配置（`CURSOR_API_KEY`、`REOLINK_RAG_LLM_PROVIDER` 等，与 `D:\reolink_knowledge\llm.env` 保持一致） |
| `src/cloud/ui_healing/llm.env.example` | 模板 |
| `configs/config.py` | 行为开关（`CLOUD_HEALING_ENABLED` 等） |
| `src/cloud/UI元素自愈设计方案.md` | 详设 |

**调试前自检**（<1 min）：

```powershell
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
python -c "import json; from src.cloud.ui_healing.llm_client import test_llm_connection; print(json.dumps(test_llm_connection(), ensure_ascii=False, indent=2))"
```

`ok: true` 方可依赖自愈；`usage_limit_exceeded` 时将 `REOLINK_RAG_LLM_MODEL` 改为 `auto` 或提高 Cursor Spend Limit。

#### payload `debug` 块扩展

在现有 `debug` 对象中**可选**增加（调试专用 payload，交付 payload 不含）：

```json
{
  "zentao_case_id": 258094,
  "debug": {
    "skip_setup": true,
    "setup_ctx_file": "data/cloud/debug_cache/payload_dashboard_258094_setup_ctx.json",
    "headless": true,
    "healing": {
      "enabled": true,
      "persist": true,
      "max_per_run": 5,
      "testcase_id": "258094"
    }
  }
}
```

| 字段 | 环境变量等价 | 说明 |
|------|--------------|------|
| `healing.enabled` | `CLOUD_HEALING_ENABLED=1` | 开启自愈 |
| `healing.persist` | `CLOUD_HEALING_PERSIST=1` | 成功后写回 `page_ele/*.yml`（写前备份到 `data/cloud/healing_audit/yaml_backups/`） |
| `healing.max_per_run` | `CLOUD_HEALING_MAX_PER_RUN` | 单次运行 LLM 上限 |
| `healing.testcase_id` | `CLOUD_HEALING_TESTCASE_ID` | 写入审计日志 |

**Service 约定**：`run()` 入口解析 `debug.healing`，在启动 BrowserSession **之前**写入环境变量：

```python
healing = (args.get("debug") or {}).get("healing") or {}
if healing.get("enabled"):
    os.environ["CLOUD_HEALING_ENABLED"] = "1"
    os.environ["CLOUD_HEALING_PERSIST"] = "1" if healing.get("persist", True) else "0"
    if healing.get("max_per_run"):
        os.environ["CLOUD_HEALING_MAX_PER_RUN"] = str(healing["max_per_run"])
    if healing.get("testcase_id") or args.get("zentao_case_id"):
        os.environ["CLOUD_HEALING_TESTCASE_ID"] = str(
            healing.get("testcase_id") or args["zentao_case_id"]
        )
```

#### 与分阶段调试的配合

```
Phase C UI 定位 timeout
    ├─ 1. 读 error_screenshot_path + steps[] 定位失败 key
    ├─ 2. 判断：iframe / 业务未就绪？ → 先 wait_ops / advance_checkout，非自愈
    ├─ 3. 确认选择器过时？ → 开 healing.enabled，Phase C 重跑（skip_setup）
    ├─ 4. 检查 data/cloud/healing_audit/healing_YYYYMMDD.jsonl
    ├─ 5. 检查 page_ele YAML diff + yaml_backups/ 备份
    └─ 6. Phase D 前：关闭 healing 或 persist=false，全量验收稳定选择器
```

**编写约定**：Page Object 继承 `CloudBasePage`，用 `self.locate("yaml_key")`；选择器仍**只维护在** `src/cloud/page_ele/front/<域>/*.yml`。自愈写回 YAML 后 **重启 Flask**。

详表 → [reference.md — AI 元素自愈](reference.md#ai-元素自愈cloud)。

## askreolink RAG 检索

**优先 MCP**（`user-flask-mcp-local` → `askreolink`）；连接失败或缺少参数时再 **Shell fallback**。

### MCP（首选）

| 场景 | 调用 |
|------|------|
| 按关键词/模块检索 | `askreolink(query="已购买云套餐 API checkout", top=8, full=true)` |
| **JMX 接口自动化（必做）** | `askreolink(query="<禅道ID> 接口自动化 jmx", top=8, full=true)` |
| 按 API 反查历史场景 | `askreolink(query="/v2/shop/orders 在哪些自动化场景", top=5)` |
| 仅要片段、少生成 | `askreolink(query="API 分组 /v2/cloud", top=3)`（不加 full） |
| 限定模块 | `askreolink(query="绑定设备", module="cloud", top=5)` |

### JMX 接口自动化知识（RAG 间接读取，非直接读 .jmx）

来源：`C:\Users\Reolink\Downloads\接口自动化场景` 下 194 个 JMeter 脚本，经 `import_jmx_scenarios.py` 解析为 supplemental（case_id `992000001+`，模块 `补充知识 / 接口自动化`）。**技能不打开 .jmx 文件**；编写前通过 askreolink **关键词检索**命中结构化知识（前置/业务 API 序列、断言、变量提取、关联禅道 ID）。

**工作流第 1 步拿到禅道用例后，第 2 步 RAG 至少执行两轮**：

1. `--case <ID>` 或 `query="<标题关键词>"` — 禅道用例 + 站点/API 知识  
2. **`query="<禅道ID> 接口自动化 jmx"`** — 历史 JMX 场景的 API 调用链（约 40 条脚本文件名含禅道 ID 可强关联）

| 用途 | 读 JMX RAG | 仍以何为准 |
|------|------------|------------|
| 接口路径 / 请求体 / 断言字段 | ✅ 参考 `【接口自动化场景】` / `【接口自动化-单接口】` | 项目 `CloudApiUtils` / Flow 封装 |
| 步骤顺序 / 业务语义 | 辅助 | **禅道 `steps`** |
| 实现形态 | ❌ 不生成 JMeter | Flask 路由 + payload JSON |

**注意**：`--case <禅道ID>` 只返回禅道正式用例（`testcases.jsonl`），**不会**自动返回 JMX supplemental（992xxx）；必须用上述关键词检索。维护索引：`import_jmx_scenarios.py --merge` → `build_rag_index.py --rebuild`（详见 [reference.md — JMX](reference.md#rag-补充知识接口自动化--jmx)）。

### Shell fallback（MCP 不可用或需 `--case` / `--retrieve-only`）

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py --case <用例ID> --full
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<禅道ID> 接口自动化 jmx" --retrieve-only --top 8
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<关键词>" --retrieve-only --top 8
```

**交叉验证**：接口路径/请求体 → **JMX RAG + 站点 API RAG** + 项目封装；步骤顺序 → 禅道 `steps`；业务规则 → RAG。

用户消息以 `askreolink` 开头时：**先 MCP `askreolink`**，失败再 Shell。参数对照表 → [reference.md — RAG 调用](reference.md#askreolink-rag-调用)。

## 交付物形态（默认）

| 类型 | 默认产出 | 何时用 pytest |
|------|----------|---------------|
| **Cloud / 混合 / 纯 API** | Flask 路由 + `control/` 注册 + payload JSON | 用户**明确要求**，或模块已有 pytest 惯例 |
| **Website UI** | Flask 路由（`POST /uiTest/guest` 等）+ payload JSON | 同上 |

**payload 命名**：`data/cloud/payload_<场景>_<用例ID>.json` 或 `data/website/payload_<场景>_<用例ID>.json`（例：`payload_dashboard_186294.json`）。

**产出物 Checklist** → [reference.md — 新增场景产出物](reference.md#新增场景产出物-checklist)。

## 工具

| 工具 | 用途 |
|------|------|
| `zentao-mcp` | `zentao_testcase_get` 读取用例 |
| MCP `askreolink` | RAG 检索（首选） |
| [reference.md](reference.md) | Setup 索引、**分阶段调试**、debug 块、**AI 元素自愈**、失败决策树、交付物 |
| [examples.md](examples.md) | 工作流示例 |
| [official-website-ui-debug/reference.md](../official-website-ui-debug/reference.md) | 路径速查、现象表 |

## 工作流（必须按序）

```
- [ ] 1. MCP 拉取禅道用例（含 precondition、steps）
- [ ] 2. RAG 检索：禅道用例/站点 API + **`<ID> 接口自动化 jmx`**（两轮，MCP askreolink 优先）
- [ ] 3. 输出「前提选型表」+「步骤选型表」（含 Setup 重叠列）
- [ ] 4. Grep 项目，选定 Setup Flow / Service / ApiUtils
- [ ] 5a. **骨架交付**（≤15 min 可 curl）：路由 + Service 壳 + Setup 接已有 Flow；steps 先 API，UI 可占位
- [ ] 5b. 完善：steps 去重 → payload JSON（含 debug 调试副本）→ 注册路由
- [ ] 6. **分阶段调试**：Phase A → B（重 Setup）→ C（UI 失败可开 `debug.healing`）→ D 全量 1 次（D 前 review 自愈 YAML）
- [ ] 7. 汇报（见下文）
- [ ] 8. **执行后沉淀（强制，可节流）**：问题归类 → 更新 skill/examples → merge RAG → 批量 rebuild
```

### 1. 读取禅道用例

用户输入 **用例 ID** 或 URL → `zentao_parse_testcase_link`（若 URL）→ **`zentao_testcase_get`**（`version=0`）。

| 字段 | 用途 |
|------|------|
| `precondition` | **Setup 唯一来源** |
| `steps`（desc + expect） | 自动化步骤与断言来源（去重后实现） |
| `title` / `module` | 命名、cloud vs website、RAG 关键词 |

MCP 不可用 → 提示检查配置，**勿猜测步骤**。

### 2. 步骤分类（摘要）

| 用例特征 | 路径 |
|----------|------|
| 登录/设备/解绑 | API `cloud_api_utils.py` |
| 套餐计算/邮件 | API `services/` |
| 订阅数据 | API `GET /v2/cloud/subscriptions/` |
| 订阅页面 | 混合 `cloud_dashboard_subscription_flow.py` |
| 支付 | UI `POST /cloud/payment/login_pay` |
| Store | UI `POST /uiTest/guest` |

优先 **扩展已有 Service/Flow**，避免重复造轮子。模块选型详表 → [reference.md](reference.md)。

### 3. 编写脚本（摘要）

```
control（薄路由）→ services（Setup + steps_logger + debug 分支）→ utils / ui_flows
```

- **骨架先行**：先注册路由 + `StepsLogger` 占位，保证 15 min 内可 curl 返回 `steps[]`
- Setup：`_fulfill_preconditions` 或 `setup_<语义>`；docstring 注明禅道前提原文；支持 `debug.setup_only`
- steps：按编号增量实现；每完成一步用 Phase C `from_step` 验证
- 纯 API：**无需** Page Object / YAML / BrowserSession
- UI：选择器**只写 YAML**；新场景编写前先 codegen / 读 error 截图定 marker
- docstring：**禅道用例 ID**、标题、实现方式（API/UI/混合）

### 4. 调试至通过

**Flask 端口**：以 `main.py` 为准（当前 **5010**）；`payload.localhost` 必须与监听端口一致。

每次重新调试前，需**重启Flask**

```bash
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
# 启动前清多实例：netstat -ano | findstr :5010
python main.py

# Phase B：仅 Setup
curl -X POST http://127.0.0.1:5010/cloud/dashboard/subscription_list \
  -H "Content-Type: application/json" \
  -d "{\"zentao_case_id\":186227,\"debug\":{\"setup_only\":true},...}"

# Phase C：跳过 Setup（示例）
curl -X POST http://127.0.0.1:5010/cloud/dashboard/payment_history_invoice \
  -H "Content-Type: application/json" \
  -d @data/cloud/payload_dashboard_186294.json

# Phase D：全量（payload 无 debug 块）
```

**失败速查（按阶段分流）**：

```
失败发生在哪？
├─ Setup（注册 / PayPal / bind / 购买链）
│   └─ Phase B 单独重跑；禁止为修 steps 反复全量 Setup
├─ Steps（UI 定位 / API 断言）
│   ├─ API → 先单接口 curl，不进浏览器
│   ├─ UI 定位 timeout → wait/iframe → debug.healing 或改 YAML
│   ├─ UI 其他 → Phase C + debug.headless；先改 YAML → wait/iframe
│   └─ 2FA → 检查 web_session 注入是否生效
└─ 环境
    ├─ localhost 端口与 main.py 一致
    └─ 改 YAML/路由后重启 Flask（load_page_yaml 进程内缓存）
```

详表 → [失败决策树](reference.md#失败排查决策树)。**勿用 UI 绕过可用 API**。卡步 **>2 min**：kill → 选 Phase B/C，**禁止**盲目全量重跑。

**AskQuestion 时机**：缺 SKU/coupon/支付类型、RAG 与项目均无接口、前提歧义、步骤与页面明显不一致、需人工 3DS/GPay 且未配置 storage。

### 5. 完成汇报

1. 禅道用例 ID + 标题
2. **前提选型表** + **步骤选型表**（含 Setup 重叠/去重列）
3. 步骤—预期映射表（摘要）
4. **交付物**：路由路径 + payload 路径 + curl 命令
5. 新增/修改文件列表
6. 运行结果（`run_id`、`steps` 片段）
7. 未覆盖项或假设

### 6. 执行后沉淀（强制，可节流）

**触发**：Phase D 全量通过（`success: true`）后，**不得**仅汇报即结束；须完成本步再结束会话。

**节流规则**（缩短调试总时长）：

| 规则 | 说明 |
|------|------|
| 同类问题 | 第 **2** 次出现才写 supplemental；第 1 次只更新 examples 表行 |
| rebuild | 多条 supplemental **合并后一次** `build_rag_index.py --rebuild` |
| 汇报与 RAG | 可先汇报通过结果，RAG merge + rebuild 可在同会话末尾批量做 |

**流程**（模板见 [examples.md — 按类型归类的问题与规避](examples.md#按类型归类的问题与规避执行后沉淀)）：

```
1. 回顾本次迭代中遇到的全部问题（含已修复），按类型归类
2. 写入 examples.md：
   - 「按类型归类的问题与规避」表（现象 → 根因 → 规避规则 → 关联用例 ID）
   - 若为新场景：追加完整工作流示例（示例 J/K/…）
3. 同步更新本 skill / reference.md：
   - 将「规避规则」提升为编写前检查项或禁止事项（避免同类问题再现）
4. 写入 RAG 补充知识 D:/reolink_knowledge/data/supplemental_cases.json：
   - case_id 递增（自动化示例从 991100012 起；**勿占用 992xxx**，该段预留给 JMX 导入）
   - 站点/导航/API 知识 → module_path_text 含「补充知识 / 测试服站点」
   - 自动化链路 → module_path_text 含「补充知识 / 自动化示例」
   - **写入时必须 `--merge` 或手工合并**，禁止覆盖 JMX（992xxx）与站点（991xxx）已有条目
5. 重建索引：
   python D:/reolink_knowledge/build_rag_index.py --rebuild
6. 汇报中增加「本次沉淀」：更新了哪些 skill 段落、新增 RAG case_id
```

**问题类型索引**（写入 examples 时使用）：

| 类型 | 典型现象 |
|------|----------|
| UI 定位 / 断言 | 元素 timeout、截图可见但断言失败 |
| UI 定位 / 自愈 | Cloud YAML 过时，LLM 写回选择器；须 review 后合入 |
| 页面导航 / 交互 | 下拉需 hover、跨域跳转 URL 不符预期 |
| 环境与调试 | Flask 404、改 YAML 不生效、5010 多实例、连续全量 curl 耗时长 |
| RAG / 知识缺失 | 检索无 Dashboard 导航、Tab 文案；或未查 JMX 导致 Setup API 序列缺失 |
| Setup / 前提 | 探测式 skip、steps 重复购买/登录 |
| API 选型 | 用 UI 替代已有 OpenAPI |
| 2FA / 登录 | 收码方式错误、登录后 landing 页断言过严 |

**RAG 写入原则**：只沉淀**可复用的 Reolink 业务/站点知识**（路由、Tab 文案、断言 marker、Flask 路由）；**勿**写入账号密码、一次性 probe 脚本路径。

## 禁止事项

- 勿将账号密码提交 git
- **勿探测式前提**（生产 Phase D：有历史数据就 skip Setup）
- **调试期**可用 `debug.skip_setup` 复用**本次会话**已构造的 `setup_ctx`；**禁止**用历史账号数据代替 Phase D 主动构造
- **勿在 steps 重复 Setup 已完成的写操作**（购买/登录/绑定）
- **勿用 UI 替代已有 API**（登录、解绑、纯数据断言）
- 勿为纯 API 场景建 Page Object / YAML / BrowserSession
- 勿散落选择器字符串；勿跳过禅道步骤；勿未读用例就生成脚本
- **调试 steps 时禁止连续 3 次全量 curl**（含 PayPal / 注册 Setup）
- **Phase D 默认关闭** `debug.healing.persist`（勿 silently 改 YAML 后交付）
- **勿用自愈替代** Setup 失败排查（注册/PayPal 链问题不是定位问题）
- **勿对** Website 模块 / 纯 API 场景开启 Cloud 自愈
- **勿未 review** 自愈写回的 YAML 直接提交 git
- **禁止 Phase B 未通过即在 Phase C 反复猜 UI 断言**
- **勿在 Phase D 通过前跳过第 8 步沉淀**（可节流 merge/rebuild，不可跳过归类）
- 勿提交 probe 脚本、`page.pause()` 残留、`tmp_*.json` 调试产物
- Dashboard **流量套餐**断言勿用泛化 CSS（`.dashboard-content`）或臆测 `SIM` 文案；以页面真实 marker（`Select All`、`+ Add Card`、`ICCID` 等）为准，见 [examples.md](examples.md#ui-定位--断言)
- Cloud 首页 **My Cloud → Cloud Dashboard** 须 **hover 后**再点下拉项 `a[href="/user/dashboard/"]`；未登录会跳转 `my.reolink.review/login`（非 cloud 站内页）
- Payment History **Invoice 链接**必用 **`expect_popup()`**（新标签页），勿在原 page 上断言 invoice 内容（禅道 156689）
- 186294 invoice：**tax=0 时不校验** seller 地址/税号；seller/税号字段须走 **`get_shop_order` 详情**，勿用订单列表 API（见 [examples.md](examples.md#按类型归类的问题与规避执行后沉淀)）
- 含「已购买付费云套餐」前提的用例（186294 等）**必须**集成 `CloudPurchaseSetupFlow`，勿依赖账号历史订单
- 仅「已绑定 SIM 卡」前提（350422 等）用 **`SimCardBindSetupFlow`**（DB + bind API），勿默认走流量购买 Setup
- **4G 锁卡设备 + 套餐购买页**（245200 等）用 **`LockCardBindSetupFlow`**（insert 设备 + 锁卡 SIM + OAuth），勿用 doorbell 直链或云套餐 Setup
- SIM Card 详情 **ICCID / Show More / eye 图标** 须按 **`sim_code` 设备卡片**作用域定位；脱敏断言仅匹配 **可见** 节点；`click_show_more` 后须等 **Show Less** 出现
- **4G 锁卡套餐购买（245200 等）禁止** `doorbell-subscribe-plan` 直链；入口为 Dashboard Cellular **第一张 `No Plan Active` 卡片** → 设备详情 → Purchase；套餐页断言 **`With cloud storage` / `Without cloud storage` 双卡片**，勿用 `Cellular Data Plan` Tab；套餐卡内操作**只 scroll 勿 click 整卡**（防跳 Cellular Data Service 独立页）；Setup 用 **`LockCardBindSetupFlow`** + `wait_cellular_products_ready()`；见 [examples.md — 245200](examples.md#示例-l混合-ui--4g-锁卡套餐购买页禅道-245200)
- **4G 锁卡套餐切换（252479 等）** Setup 用 **`LockCardPlanPurchaseSetupFlow`**（bind + 下单 + PayPal + **Finish**）；Post-Setup **禁止** 180s 轮询 sim_code（Dashboard 不展示）；入口 **Dashboard Cellular 已有套餐卡** → Manage Your Subscription → Switch Plan（**勿** My Devices 回退）；按 **uid/iccid/plan_title 模糊匹配** 定位设备；步骤操作为 **Choose**（`mode=switch`）；PayPal 成功后须 **`click_finish_if_payment_succeeded()`**；见 [examples.md — 252479](examples.md#示例-m混合-ui--4g-锁卡套餐切换页禅道-252479)
- **云套餐列表 186227**：须 **`register_new_account` + `get_code_type: back`**（JMeter 注册.jmx）；注册邮箱 **`@t.com`**；Setup 顺序 **免费 Basic API → PayPal 付费 → 带图推送 API**（付费后再免费 preview **403**）；带图推送 **禁止 OAuth 绑设备**，用 `create_free_rich_notification_order(associateDevices)`；带图推送识别 **`legacyTag=222`**；PayPal 后 token 优先 **浏览器 Cookie web_session**；见 [examples.md — 186227](examples.md#示例-b混合--云套餐订阅列表api-主断言--ui-抽样) — Setup 索引、RAG、去重、失败决策树、交付物
- [examples.md](examples.md) — 186294 / 280429 等完整示例 + **按类型归类的问题与规避**
- 项目 `src/cloud/README.md`
