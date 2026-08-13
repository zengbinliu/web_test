# official_website_server 自动化参考

## 设计原则：接口为主、UI 为辅

| 场景 | 推荐实现 | 说明 |
|------|----------|------|
| 登录获取 access_token | API `CloudApiUtils.login` | 勿用 UI 点登录页代替 |
| 设备解绑 / 批量清理 | API `CloudApiUtils.unbind_devices` | `POST /cloud/device/unbind` |
| 测试设备 uid/suid 查询 | API `DeviceDataService` | `POST /cloud/device/unbound_uid_suid` |
| 套餐价格 / 退款计算 | API `CloudCalculatorService` | `POST /cloud/calculate_utils_*` |
| 邮件模板变量渲染校验 | API `EmailTemplateService` | `POST /cloud/check_email`，无浏览器 |
| 订阅列表**数据**正确性 | API `GET /v2/cloud/subscriptions/` | 主断言在 `subscription_list_validator` |
| 订阅列表**页面展示** | 混合 | API 主断言 + UI 抽样可见卡片 |
| checkout 支付 | UI | Strategy + iframe |
| Store 页面元素 / 文案 | UI | Page Object + YAML |
| 环境认证（review） | UI（必要时） | `environment_verify_flow` |

新增场景前，先查 [接口索引](#接口与工具索引) 与 askreolink RAG，确认是否已有 API 可复用。

## 常见前提条件 → API / 实现映射

编写自动化时，禅道 `precondition` **必须先于 `steps` 主动构造落地**。

**原则：主动构造，禁止探测。** 查询 API 仅用于 Setup **执行后**的校验，不可用于「已有则跳过 Setup」。

下表为常见前提的快速索引；具体路径与请求体以 **askreolink RAG** 检索结果为准。

| 前提条件关键词 | RAG 检索建议 | 必须执行的动作（每次运行） | 构造后校验 |
|----------------|--------------|---------------------------|------------|
| 已登录 | `--case <ID>` + `登录 token API` | **调用** `CloudApiUtils.login` | token 非空 |
| **已购买云套餐** / 有生效订阅 | `已购买云套餐 API checkout 下单` + **`<ID> 接口自动化 jmx`** + `API 分组 /v2/shop` | **调用** RAG 购买链路：创建订单 → 支付（API 或 `login_pay`） | `GET /v2/cloud/subscriptions/?status=active` 有**本次购买**的记录 |
| 已有绑定设备 / 有设备 | `绑定设备 API` + `GET /v2/devices` | **调用**绑设备 API | `GET /v2/devices` 含目标 uid |
| 设备无套餐 | 同上 | **调用**绑设备；**不**购买套餐 | subscriptions 为空 |
| 套餐已过期 | `过期订阅 构造` | **调用** API 构造过期态（购买后改期/等效方式） | `GET /v2/cloud/subscriptions/?status=inactive` |
| 已有订单 / Payment History | `下单 API` + `GET /v2/shop/orders` | **调用**购买/下单链路 | `GET /v2/shop/orders/` 有 paid 订单 |
| 已签约免密支付 | `免密支付 paypal` | **执行**带 auto-renewal 的 PayPal 支付 | checkout 按钮文案 |
| 未登录 / 游客 | — | **跳过**登录 Setup | 无 token |
| 后台开关/国家配置 | 模块名 + `后台配置 API` | **调用**管理端 API | 配置查询或 AskQuestion |

### RAG 补充知识（API 分组）

askreolink 知识库中的 **补充知识 / 测试服站点 / apis.reolink.review** 条目含页面触发的 OpenAPI 清单，前提落地时优先检索：

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "API 分组 /v2/shop" --retrieve-only --top 3
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "API 分组 /v2/cloud" --retrieve-only --top 3
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "API 分组 /v2/devices" --retrieve-only --top 3
```

常见 Cloud 相关接口（来自站点爬取知识，以 RAG 最新结果为准）：

| 接口 | 典型用途 |
|------|----------|
| `POST /v2/auth/token` | 登录前提 |
| `GET /v2/cloud/subscriptions/` | 校验是否有生效/过期套餐 |
| `GET /v2/cloud/products` | 查可购套餐 |
| `GET /v2/shop/orders` | 校验是否有订单 |
| `GET /v2/shop/order/payment/methods` | checkout 支付方式 |
| `GET /v2/devices` | 校验绑定设备 |
| `POST /v2/cloud/device/x-plan/view` | app 免费套餐入口相关 |

### RAG 补充知识（接口自动化 / JMX）

JMeter 历史脚本（`C:\Users\Reolink\Downloads\接口自动化场景`，194 个 `.jmx`）已解析进 supplemental，**不直接读 .jmx 文件**。检索模块：`补充知识 / 接口自动化 / 组合场景|单接口|索引`（case_id `992000001+`）。

**编写前必做**（在 `--case <ID>` 之后追加）：

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<禅道ID> 接口自动化 jmx" --retrieve-only --top 8
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<标题关键词> 接口自动化" --retrieve-only --top 5
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "/v2/shop/orders 在哪些自动化场景" --retrieve-only --top 5
```

| 命中条目 | 可提取信息 | 用途 |
|----------|------------|------|
| `【接口自动化场景】*` | 前置/业务 HTTPSampler 序列、断言、JSON 变量提取 | Setup / steps 的 API 选型与断言字段 |
| `【接口自动化-单接口】*` | 某 METHOD+PATH 被哪些场景引用 | 确认接口是否已有历史用法 |
| `【接口自动化索引】*` | 领域分布、禅道 ID 交叉索引 | 找同领域参考场景 |

**限制**：`--case <禅道ID>` 只查禅道正式用例，**不含** JMX supplemental；JMX 仅能通过关键词 RAG 命中。实现仍以 Flask + 项目封装为准，不复刻 JMeter。

**索引维护**（更新 JMX 目录后）：

```bash
python D:/reolink_knowledge/import_jmx_scenarios.py --merge
python D:/reolink_knowledge/build_rag_index.py --rebuild
```

写入 supplemental 时（站点爬取 / 自动化示例 / JMX）**均需 `--merge`**，避免互相覆盖。

### 已购买云套餐 Setup 参考流程（每次主动执行）

```
1. 解析前提：套餐类型（免费/付费/Basic/带图）、周期、是否绑设备
2. CloudApiUtils.login → access_token
3. RAG/项目：按前提要求选 product_id → 【调用 API 创建 checkout 订单】
4. 【调用 API 或 login_pay 完成支付】— 禁止先查 subscriptions 有则跳过
5. GET /v2/cloud/subscriptions/?status=active → 断言本次购买成功
6. 将 subscription_id / plan_name 等写入 plan_ctx
7. steps_logger("[Setup] 购买云套餐") → 用 plan_ctx 进入禅道 steps
```

支付步骤无法用 API 替代时，**仅支付段走 UI**；下单仍走 API。Setup 产出物（`plan_ctx`）必须传入正式步骤。

**Cloud 订单支付页 URL**（`POST /v2/shop/payment/` 响应 `url` 为空时使用）：

```
https://cloud.reolink.review/checkout/pay/?o_id={order_id}&mode=create&platform=web
```

RAG 补充知识：`991100010`；项目封装：`CloudPurchaseUtils.build_checkout_pay_url`。完整示例见 [examples.md — 示例 I](examples.md#示例-i混合--前提购买--payment-history-invoice禅道-186294)。

**优先复用封装**：见下文 [Setup 封装与通用模式索引](#setup-封装与通用模式索引)，勿在 Service 内重写购买链路。

## Setup 封装与通用模式索引

编写 `_fulfill_preconditions` 前，**先查本表**；有封装则扩展参数，无封装再按 RAG 新建。

### 独立 Setup Flow / Utils（优先复用）

| 封装 | 路径 | 适用前提 | 能力边界 | 典型用例 |
|------|------|----------|----------|----------|
| **`CloudPurchaseSetupFlow`** | `ui_flows/common/payment/cloud_purchase_setup_flow.py` | 已购买**付费**云套餐 | **API 下单 + UI PayPal 支付**；`pay_type` 当前仅 `paypal` | 禅道 **186294** |
| **`CloudPurchaseUtils`** | `utils/cloud_purchase_utils.py` | 同上（Flow 底层） | `create_paid_cloud_plan_order`、`wait_order_completed`、`assert_active_paid_subscription`、`build_checkout_pay_url` | 186294 |
| **`SimCardBindSetupFlow`** | `ui_flows/common/dashboard/sim_card_bind_setup_flow.py` | 已绑定 SIM 卡（无流量套餐要求） | DB 取未绑定卡 + `POST /v2/devices/sim-cards/bind` | 禅道 **350422** |
| **`LockCardBindSetupFlow`** | `ui_flows/common/lock_card/lock_card_bind_setup_flow.py` | 4G **锁卡**设备已绑定 | insert 设备 + 挪威 SIM + OAuth；`wait_cellular_products_ready()` 轮询 products | 禅道 **245200** |
| **`PlanProductsUtils`** | `utils/plan_products_utils.py` | 套餐列表 API 基准 | `POST /v2/cloud/products` 分类 traffic/merged/cloud | 245200 |

**调用示例**：

```python
from src.cloud.ui_flows.common.cloud_purchase_setup_flow import CloudPurchaseSetupFlow

plan_ctx = CloudPurchaseSetupFlow(steps_logger=self._log).purchase_paid_cloud_plan(
    session, page, access_token, args
)
# plan_ctx: order_id, pay_url, pay_amount, completed_order, active_paid_subscription_count, ...
```

**扩展新前提时**：若仅换 `product_id` / billing → 传 `args`；若换支付方式 → 扩展 `CloudPurchaseSetupFlow` 而非复制 Service 逻辑。

### 通用 Setup 模式（无独立 Flow，按模式调用）

| 前提关键词 | 推荐实现 | 入口 / 路由 |
|------------|----------|-------------|
| 已登录（API） | `CloudApiUtils.login` | `POST /v2/auth/token` |
| 已登录（UI + 2FA） | `CloudLoginFlow.login_with_2fa` | 混合 Service 内 |
| 设备解绑 / 清理 | `DeviceDataService` | `POST /cloud/device/unbind`、`clean_*` |
| 查未绑定 uid/suid | `DeviceDataService` | `POST /cloud/device/unbound_uid_suid` |
| 已有绑定设备 | RAG 绑设备 API + 项目封装 | `GET /v2/devices` 校验 |
| 邮件模板就绪 | `EmailTemplateService` | `POST /cloud/check_email` |
| 环境认证（review） | `environment_verify_flow` | UI，必要时 |
| 免费套餐 / 过期态 / 免密签约 | RAG 查构造方式 | **尚无**独立 Flow → 参考 examples，或新建 `*_setup_flow.py` |

## 前提与 steps 去重

与 [SKILL.md — 前提与 steps 去重](SKILL.md#前提与-steps-去重) 配套；编写步骤选型表时增加列 **「Setup 重叠 → 实现」**。

| 禅道 steps desc | precondition 已覆盖？ | steps 实现 |
|-----------------|----------------------|------------|
| 登录 Cloud 账号 | P1 已登录 | `steps_logger("步骤N: 登录（复用 Setup）")` + 断言 token/session，**不**再调 login |
| 购买云套餐 | P2 已购买 | logger 标注 `plan_ctx['order_id']` + **校验/展示**订阅或订单，**不**再 purchase |
| 进入 dashboard 查看订阅 | P1+P2 已满足 | 直接导航 + 用 `plan_ctx` 做 API/UI 断言 |
| 与 Setup 无关的操作 | — | 正常实现（绑设备、点击、支付等） |

**选型表示例**：

| # | 禅道步骤 | Setup 重叠？ | 实现方式 |
|---|----------|--------------|----------|
| 1 | 登录 | 是（P1） | 复用 token，仅 logger + 断言 |
| 2 | 查看 Payment History | 否 | 混合 Flow + `plan_ctx['order_id']` |

```python
# ❌ Setup 已购买，steps 再次购买
plan_ctx = CloudPurchaseSetupFlow(...).purchase_paid_cloud_plan(...)
self._purchase_again(token, args)

# ✅ steps 仅校验本次 Setup 订单
self._log(f"步骤3: 打开 invoice（order_id={plan_ctx['order_id']}）")
self._verify_invoice(plan_ctx["order_id"], ...)
```

## askreolink RAG 调用

**优先 MCP**（`user-flask-mcp-local` → `askreolink`）；失败或需 Shell 专有参数时再 fallback。

| 需求 | MCP `askreolink` | Shell fallback |
|------|------------------|----------------|
| 关键词 / API 检索 | `query`, `top`, `full=true` | `--full` / 省略 `--full` |
| **JMX 接口自动化（必做）** | `query="<ID> 接口自动化 jmx", top=8, full=true` | `"<ID> 接口自动化 jmx" --retrieve-only --top 8` |
| API 反查历史场景 | `query="/v2/... 在哪些自动化场景", top=5` | 同上 Shell 语法 |
| 限定模块 | `module="cloud"` | `--module cloud` |
| 简短结论 | `brief=true` | `--brief` |
| **按用例 ID 直查（仅禅道）** | ❌ 不支持 | `--case <ID> --full` |
| **仅检索不生成** | ❌ 不支持 | `--retrieve-only --top N` |
| 统计 / 重建索引 | ❌ | `--stats` / `--rebuild-index` |

```bash
# Shell：禅道用例（不含 JMX supplemental）
python D:/reolink_knowledge/ask_reolink_testcase_kb.py --case 186294 --full
# Shell：JMX 历史 API 序列（第二步必做）
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "186294 接口自动化 jmx" --retrieve-only --top 8
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "API 分组 /v2/shop" --retrieve-only --top 3
```

用户消息以 `askreolink` 开头：**先 MCP**，再 Shell。

## 分阶段调试协议

与 [SKILL.md — 分阶段调试协议](SKILL.md#分阶段调试协议调试期强制) 配套；编写新 Service 时须实现 `debug` 分支。

### Phase 定义

| Phase | 目的 | payload 关键字段 | 典型耗时 |
|-------|------|------------------|----------|
| **A** | 静态 / 单 API | 无浏览器；直接 `CloudApiUtils` | <30s |
| **B** | 隔离 Setup | `debug.setup_only: true` | 1–15 min |
| **C** | 切片 steps | `debug.skip_setup: true` + `setup_ctx` 或 `setup_ctx_file`；可选 `from_step` | 30s–3 min |
| **D** | 全量回归 | 无 `debug` 或全 false | 同生产 |

### payload `debug` 块

```json
{
  "localhost": "http://127.0.0.1:5010/",
  "debug": {
    "setup_only": false,
    "skip_setup": false,
    "from_step": null,
    "setup_ctx": {},
    "setup_ctx_file": "data/cloud/debug_cache/payload_<场景>_<ID>_setup_ctx.json",
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

| 字段 | Service 行为 |
|------|--------------|
| `setup_only` | 执行 Setup 后 `success_response(run_data={setup_ctx: ...})`，不跑 steps |
| `skip_setup` | 从 `setup_ctx` / `setup_ctx_file` 加载，跳过 Setup 写操作 |
| `from_step` | 仅执行 `>= from_step` 的禅道步骤（logger 仍标注跳过步） |
| `headless` / `slow_mo` | 覆盖 `BrowserSession(headless=..., slow_mo=...)` |
| `pause_on_fail` | 失败时 `page.pause()`（仅本地调试） |
| `trace_on_fail` | `context.tracing` 写入 `error_scn/date_MMDD/trace_<run_id>.zip` |
| `healing.enabled` | 写入 `CLOUD_HEALING_ENABLED=1`；Cloud Page Object 定位失败时调 LLM 推理新选择器 |
| `healing.persist` | 写入 `CLOUD_HEALING_PERSIST`；成功则更新 `page_ele/*.yml`（备份见 `healing_audit/yaml_backups/`） |
| `healing.max_per_run` | 写入 `CLOUD_HEALING_MAX_PER_RUN`，默认 5 |
| `healing.testcase_id` | 写入 `CLOUD_HEALING_TESTCASE_ID`，默认取 `zentao_case_id` |

**setup_ctx 落盘**：Phase B 成功后，将 `run_data.setup_ctx` 存为 `data/cloud/debug_cache/payload_<场景>_<ID>_setup_ctx.json`，Phase C 用 `setup_ctx_file` 引用。

### AI 元素自愈（Cloud）

**详设**：`official_website_server/src/cloud/UI元素自愈设计方案.md`

| 路径 | 说明 |
|------|------|
| `src/cloud/ui_healing/llm.env` | LLM 配置（与 `D:\reolink_knowledge\llm.env` 同变量名） |
| `src/cloud/ui_healing/llm_config.py` | 加载 `llm.env` |
| `src/cloud/ui_healing/llm_client.py` | 推理入口 + `test_llm_connection()` |
| `src/cloud/ui_healing/cloud_base_page.py` | Page Object 基类 `locate()` / `frame_locate()` |
| `data/cloud/healing_audit/` | 审计日志 `healing_YYYYMMDD.jsonl` |
| `data/cloud/healing_audit/yaml_backups/` | 写回 YAML 前自动备份 |

**自检**：

```powershell
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
python -c "import json; from src.cloud.ui_healing.llm_client import test_llm_connection; print(json.dumps(test_llm_connection(), ensure_ascii=False, indent=2))"
```

**Service 注入环境变量**（在 `BrowserSession` 启动前）：

```python
def _apply_healing_env(args: dict) -> None:
    healing = (args.get("debug") or {}).get("healing") or {}
    if not healing.get("enabled"):
        return
    os.environ["CLOUD_HEALING_ENABLED"] = "1"
    os.environ["CLOUD_HEALING_PERSIST"] = "1" if healing.get("persist", True) else "0"
    if healing.get("max_per_run"):
        os.environ["CLOUD_HEALING_MAX_PER_RUN"] = str(healing["max_per_run"])
    case_id = healing.get("testcase_id") or args.get("zentao_case_id")
    if case_id:
        os.environ["CLOUD_HEALING_TESTCASE_ID"] = str(case_id)
```

| 阶段 | 建议 |
|------|------|
| Phase C | `healing.enabled: true`，`skip_setup: true` |
| Phase D | `healing.enabled: false` 或 `persist: false` |
| Phase B Setup 失败 | **勿**开自愈，先修 Setup 链 |

**改 YAML 不生效**：除重启 Flask 外，若开启 `healing.persist`，还须检查 `yaml_backups/` 与 git diff。

### Service 解析模板

```python
def _parse_debug(args: dict) -> dict:
    return dict(args.get("debug") or {})

def _load_setup_ctx(args: dict, debug: dict) -> dict:
    if debug.get("setup_ctx"):
        return dict(debug["setup_ctx"])
    path = (debug.get("setup_ctx_file") or "").strip()
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}
```

在 `run()` 中：`debug = _parse_debug(args)` → Setup 段判断 `setup_only` / `skip_setup` → steps 段判断 `from_step`。

### 调试期登录快路径

| 优先级 | 手段 |
|--------|------|
| 1 | `access_token` / `cloud_access_token` in payload |
| 2 | `cloud_token_storage.json` → `web_session_auth_code` cookie 注入 |
| 3 | `extract_cloud_access_token_from_page`（PayPal 后） |
| 4 | `CloudLoginFlow.login_with_2fa` |

### 重 Setup 场景调试策略

| 用例 | Setup 内容 | 建议 |
|------|-------------|------|
| **186227** | 注册 + 免费 API + PayPal + 带图推送 | Phase B 固化 `setup_ctx`；403 preview 在 B 修顺序，勿带浏览器重跑 |
| **186294** | PayPal 付费 | B 后 C 用 `order_id`；invoice 步骤 `from_step` |
| **252479** | bind + PayPal + Finish | **禁止** 180s sim_code 轮询；B 后 30s 索引等待 |
| **350422** | DB + bind API | Setup 轻，可全量；UI 用 `from_step=3` |
| **280429** | 无重 Setup | 直接 Phase C |
| **245200** | LockCard bind + products 轮询 | B 须 `wait_cellular_products_ready()` 通过后再 C |

### Playwright 调试速查

| 场景 | 命令 / 代码 |
|------|-------------|
| Inspector | `$env:PWDEBUG=1`（PowerShell）+ 运行脚本；或 `page.pause()` |
| Codegen | `playwright codegen https://cloud.reolink.review/user/dashboard` |
| Trace | `context.tracing.start(...)` → `playwright show-trace trace.zip` |
| 高亮定位 | `page.locator(...).highlight()` |

### Flask 与环境

| 项 | 说明 |
|----|------|
| 端口 | `main.py` 当前 **5010**；`localhost` 须一致 |
| 多实例 | `netstat -ano \| findstr :5010`，只保留一个 `python main.py` |
| YAML 缓存 | 改 YAML 后 **重启 Flask** |
| 代理 | 调试慢时可在 payload `debug` 或本地暂时 `CLOUD_BROWSER_PROXY = None` |

可选：`python scripts/dev_run.py`（若项目已添加）直接 `Service(args).run()`，跳过 HTTP 层。

## 失败排查决策树

调试时按序执行；**先判断失败阶段（Setup vs steps）**，再查现象。细节另见 [official-website-ui-debug/reference.md](../official-website-ui-debug/reference.md#现象--排查对照表)。

```
卡步 >2min 或 HTTP 500？
├─ 失败在 Setup（steps[] 中含 [Setup] 或注册/PayPal/bind）
│   ├─ Phase B 单独重跑（debug.setup_only）
│   ├─ API 顺序/403/401 → 对照 RAG + JMX，修 Setup Flow
│   └─ 禁止为修 steps 反复全量 Setup
├─ 失败在 Steps（正式步骤序号）
│   ├─ Phase C：skip_setup + from_step
│   ├─ API 断言 → 先单接口 curl
│   ├─ UI → YAML → iframe_ops → wait_ops；debug.headless=true 加速
│   ├─ UI 定位 timeout → 先 wait/iframe → 再 debug.healing 或改 YAML
│   ├─ 2FA → web_session 注入是否生效
│   └─ 支付 iframe → Strategy / pay_type
├─ success == true 但语义不符
│   └─ 历史数据 vs plan_ctx → 去重 → 断言字段对齐 RAG
└─ 服务未响应 / 404
    ├─ main.py 是否 :5010 → curl POST /cloud/status
    └─ 多实例 / 旧代码 → netstat 清理 → 重启 Flask
```

**响应 JSON 细查**（在阶段判断之后）：

```
响应 JSON
├─ success == false 或 HTTP 非 2xx
│   ├─ 纯 API 路由（无 steps）
│   │   └─ 读 message / error_message → 对照 RAG → 修 Service
│   └─ 含 steps[]
│       ├─ 首个 success: false 的 index
│       ├─ error_screenshot_path / trace（debug.trace_on_fail）
│       └─ 无截图 → localhost 端口是否与 main.py 一致
```

**改 YAML 不生效**：`load_page_yaml` 进程内缓存；必须 **重启 Flask** 后重跑（见 [examples.md — 环境与调试](examples.md#按类型归类的问题与规避执行后沉淀)）。

**日志与截图路径**：

| 类型 | 位置 |
|------|------|
| Cloud UI 失败截图 | `error_scn/date_MMDD/` |
| 官网失败截图 | `static/screenshots/` |
| 步骤日志 | 响应 `data.steps[]` |
| 运行关联 | 响应 `run_id`（若有） |

## 目录结构

```
official_website_server/
├── main.py                          # Flask :5010（以 main.py 为准）
├── data/cloud/debug_cache/          # Phase B 输出的 setup_ctx（勿提交 git）
├── configs/
│   └── config.py                    # 统一配置（UI / API / DB / 自愈 / XXL-JOB）
├── data/
│   ├── website/page_ele/            # 官网元素 YAML（仅 UI 场景）
│   └── website/temporary_storage/   # token / storage state
├── src/
│   ├── cloud/
│   │   ├── page_ele/front/<域>/     # Cloud YAML（login/home/payment/dashboard/lock_card/payment_history）
│   │   ├── ui_healing/              # AI 元素自愈（llm.env / CloudBasePage）
│   │   ├── ui_pages/front/<域>/
│   │   ├── ui_flows/common/<域>|payment/
│   │   ├── services/                # 接口 + UI 编排入口
│   │   ├── control/
│   │   ├── utils/
│   │   │   ├── cloud_api_utils.py   # Cloud OpenAPI 封装（优先复用）
│   │   │   └── subscription_list_validator.py
│   │   └── browser/                 # 仅 UI / 混合场景
│   └── website/
│       ├── ui_pages/front/
│       ├── ui_flows/guest|common/
│       ├── services/
│       ├── control/
│       └── test_case/
├── error_scn/
└── static/screenshots/
```

## 默认测试账号

| 用途 | 账号 | 密码 |
|------|------|------|
| Cloud / 官网测试账号 | `liuzb@reolink.com.cn` | `bc123456.` |
| 邮箱（IMAP / 2FA 收码） | `liuzb@reolink.com.cn` | `ltlbinQq6.` |

Cloud UI 登录 2FA 收码见 [Cloud UI 登录与 2FA 收码](#cloud-ui-登录与-2fa-收码)。

环境认证（review）：`env_verify_password` 常为 `bc-reolink-2023`，host 如 `r1.reolink.review`。

## Cloud UI 登录与 2FA 收码

与 `POST /cloud/payment/login_pay` 共用 `CloudLoginFlow` + `verify_code_providers.py`。

| `get_code_type` | 实现 | 说明 |
|-----------------|------|------|
| **不传 / 空 / `email` / `imap` / `EmailManager`** | **EmailManager**（**默认**） | IMAP 读 `email_account` 邮箱 |
| `back` / `get_verify_code_by_back` / `mailproxy` | `get_verify_code_by_back` | 后台 MailProxy，依赖 `cloud_token_storage.json` → `admin_access_token` |

**编写新路由时**：请求体透传 `get_code_type` 至 `CloudLoginFlow.login_with_2fa(session, args)`；步骤日志输出 `验证码获取方式: EmailManager` 或 `get_verify_code_by_back`。

必填字段（UI 登录场景）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `account` | 是 | Cloud 登录账号 |
| `passwd` | 是 | Cloud 登录密码 |
| `email_account` | 是* | IMAP 邮箱；`get_code_type` 为 back 系时可忽略 |
| `email_passwd` | 是* | IMAP 密码；back 系时可忽略 |
| `get_code_type` | 否 | 见上表；**默认 EmailManager** |
| `localhost` | 否 | 错误截图 URL 前缀 |


## 分层职责

| 层 | 接口场景 | UI / 混合场景 |
|----|----------|---------------|
| HTTP | `control/` 薄路由 | 同左 |
| 编排 | `services/*_service.py` + `StepsLogger` | 同左，内调 Flow 或 ApiUtils |
| 业务 | `utils/cloud_api_utils.py`、`requests` | `ui_flows` → `ui_pages` → YAML |
| 浏览器 | 不需要 | `browser/session.py` |

**步骤日志**（接口与 UI 统一）：
- Cloud：`StepsLogger` → 响应 `data.steps`
- Website：`UiGuestService.steps_logger` → 同上结构

## 接口与工具索引

### Cloud OpenAPI（`CloudApiUtils`）

配置：`configs/config.py`

| 方法 | 路径 | 用途 |
|------|------|------|
| `login(account, passwd, mfa_trust_token)` | `POST /v2/auth/token` | 获取 access_token |
| `unbind_device(uid, token)` | `DELETE /v2/devices/{uid}` | 单设备解绑 |
| `unbind_devices(uids, token)` | 批量解绑 | |

扩展新 OpenAPI 时，优先在 `cloud_api_utils.py` 增加静态方法，再由 `services/` 编排。

### Flask 纯 API 路由（无 UI）

| 方法 | 路径 | Service | 说明 |
|------|------|---------|------|
| POST | `/cloud/calculate_utils_cloud` | `CloudCalculatorService` | 云套餐计算 |
| POST | `/cloud/calculate_utils_traffic` | 流量计算 | |
| POST | `/cloud/check_email` | `EmailTemplateService` | 邮件 HTML 变量校验 |
| POST | `/cloud/device/unbind` | `DeviceDataService` | 设备解绑 |
| POST | `/cloud/device/clean_4g` | `DeviceDataService` | 4G 设备清理 |
| POST | `/cloud/device/clean_normal` | `DeviceDataService` | 普通设备清理 |
| POST | `/cloud/device/unbound_uid_suid` | `DeviceDataService` | 查询未绑定设备 |

### Flask UI / 混合路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/cloud/payment/login_pay` | 登录 + checkout **支付**（UI） |
| POST | `/cloud/dashboard/subscription_list` | 订阅列表（**混合**：API 主断言 + UI 抽样） |
| POST | `/cloud/dashboard/payment_history_invoice` | Payment History invoice（**混合**，禅道 156689 / **186294**） |

### Website

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/uiTest/guest` | 游客流程（**UI**） |
| POST | `/uiTest/noVerify` | 非 2FA 登录用户（**UI**） |
| POST | `/uiTest/needVerify` | 2FA 登录用户（**UI**） |
| POST | `/payment/login` | 登录用户**支付**（**UI**） |
| POST | `/payment/guest` | 游客**支付**（**UI**） |

## 主要 API 请求示例

### Cloud 支付 / UI 登录（默认 EmailManager 收码）

```json
{
  "pay_url": "https://cloud.reolink.review/checkout/pay/?o_id=...",
  "account": "liuzb@reolink.com.cn",
  "passwd": "bc123456.",
  "email_account": "liuzb@reolink.com.cn",
  "email_passwd": "ltlbinQq6.",
  "pay_type": "paypal",
  "localhost": "http://127.0.0.1:5010/"
}
```

调试副本可追加 `"debug": { "setup_only": true }` 等，见 [payload debug 块](#payload-debug-块)。

改用后台 MailProxy 收码时追加 `"get_code_type": "back"`（或 `get_verify_code_by_back` / `mailproxy`）。

`pay_type`：`paypal`、`adyen`、`CB`、`payoneer`、`google pay`（子串匹配，见 `registry.py`）。

### Cloud Dashboard 混合用例（登录字段同上）

```json
{
  "account": "liuzb@reolink.com.cn",
  "passwd": "bc123456.",
  "email_account": "liuzb@reolink.com.cn",
  "email_passwd": "ltlbinQq6.",
  "localhost": "http://127.0.0.1:5010/"
}
```

可选：`get_code_type`（见上）、`order_id`（Payment History 指定订单）、`ui_sample_size`（订阅列表 UI 抽样数）、`debug`（调试期，见上文）。

### Cloud 设备解绑（API 优先）

```json
{
  "account": "liuzb@reolink.com.cn",
  "passwd": "bc123456.",
  "uids": ["uid1", "uid2"],
  "mfa_trust_token": "..."
}
```

### Website 游客（UI）

```json
{
  "uiTestType": "guest_store_main",
  "env_certification": {
    "host": "r1.reolink.review",
    "password": "bc-reolink-2023"
  },
  "test_data": { }
}
```

已有 `uiTestType` 见 `ui_test_control.py` / `UiGuestService.guest_main` 分支。

## 新增场景产出物 Checklist

**默认交付**（除非用户明确要求 pytest）：Flask 路由 + payload JSON + curl 可执行。

### payload 命名与位置

| 模块 | 路径模式 | 示例 |
|------|----------|------|
| Cloud / 混合 | `data/cloud/payload_<场景>_<用例ID>.json` | `payload_dashboard_186294.json` |
| Website UI | `data/website/payload_<场景>_<用例ID>.json` | `payload_guest_store_123456.json` |

payload 含：账号凭证（勿提交 git）、`localhost`（Cloud UI 必填，端口与 `main.py` 一致）、场景参数（`product_id`、`order_id`、`pay_type` 等）。调试期另建 `payload_*_debug.json` 或内嵌 `debug` 块；`debug_cache/` 勿提交 git。

### 纯 API 场景（推荐路径）

1. `utils/cloud_api_utils.py` 新方法（若需新 OpenAPI）
2. `services/cloud_xxx_service.py`（编排 + Setup + `StepsLogger` + 断言）
3. `control/xxx_control.py` + `control/__init__.py` 注册路由
4. `data/cloud/payload_<场景>_<用例ID>.json`
5. **不需要** YAML / Page Object / BrowserSession

### Cloud — checkout 新支付方式（UI 必须）

1. `src/cloud/page_ele/front/payment/cloud_xxx_page.yml`
2. `src/cloud/ui_pages/front/payment/cloud_xxx_page.py`
3. `src/cloud/ui_flows/payment/strategies/xxx.py`
4. `registry.py` 注册 `pay_type`

### Cloud — 页面展示校验（UI 或混合）

1. 若含前提：复用 [Setup 封装索引](#setup-封装与通用模式索引) 或新增 `*_setup_flow.py`
2. 若含数据断言：先在 `utils/` 或 `services/` 写 API 校验逻辑
3. YAML + Page Object（仅展示相关元素；路径按业务域：`login` / `home` / `payment` / `dashboard` / `lock_card` / `payment_history`）
4. `ui_flows/common/<域>/cloud_xxx_flow.py`
5. `services/cloud_xxx_service.py`（Setup → steps 去重）
6. `control/xxx_control.py` 注册路由
7. `data/cloud/payload_<场景>_<用例ID>.json`

### Website — 新游客/登录场景（UI）

1. `data/website/page_ele/front/xxx.yml`（如需新元素）
2. `ui_pages/front/`（如需）
3. `ui_flows/` 新方法
4. `UiGuestService` 或 `UiLoginService` 新分支 + `uiTestType`
5. `data/website/payload_<场景>_<用例ID>.json`
6. **pytest**（`src/website/test_case/`）：仅当用户明确要求或模块已有 pytest 惯例

## YAML 示例（仅 UI 场景）

```yaml
# Cloud: src/cloud/page_ele/front/login/login_signup_page.yml 风格
login_email_input: "#email"
send_code_button: 'role=button[name="Send Code"]'
btn_wait_timeout_ms: 20000
btn_load_retries: 3
```

超时、重试、默认测试数据放 YAML；业务凭证放请求体。

## 可复用能力索引

### Setup（前提构造）

| 文件 | 能力 |
|------|------|
| `cloud_purchase_setup_flow.py` | **付费云套餐 Setup**（API 下单 + PayPal UI），禅道 186294 |
| `cloud_purchase_utils.py` | 购买 API：`create_paid_cloud_plan_order`、`wait_order_completed`、`assert_active_paid_subscription` |
| `cloud_api_utils.py` | 登录、解绑（通用 Setup） |
| `device_data_service.py` | 设备查询、解绑、清理 Setup |

### API / 纯逻辑

| 文件 | 能力 |
|------|------|
| `cloud_api_utils.py` | Cloud OpenAPI：登录、解绑 |
| `subscription_list_validator.py` | 订阅列表 API 数据过滤与 UI 对照 |
| `count_price.py` | 价格计算请求 |
| `verify_code_providers.py` | 2FA 收码策略：`EmailManager`（默认）/ `get_verify_code_by_back` |
| `verify_code_service.py` | 后台 MailProxy 取 MFA 码（`get_code_type` 为 back 系时） |
| `device_data_service.py` | 设备查询、解绑编排 |
| `email_template_service.py` | 邮件模板校验 |

### UI（支付 / 页面展示）

| 文件 | 能力 |
|------|------|
| `cloud_login_flow.py` | Cloud 登录 + 邮箱 2FA（透传 `get_code_type`，默认 EmailManager） |
| `cloud_home_page.py` / `cloud_home_page.yml` | cloud 首页 **My Cloud hover → Cloud Dashboard**（禅道 280429） |
| `cloud_dashboard_traffic_flow.py` | Dashboard 未登录导航 + 流量套餐 Tab（禅道 280429） |
| `cloud_dashboard_subscription_flow.py` | 订阅列表（混合模式参考） |
| `cloud_dashboard_payment_history_flow.py` | Payment History invoice（混合模式参考） |
| `payment/strategies/*.py` | PayPal、Adyen、Payoneer、GPay |
| `environment_verify_flow.py` | review 环境认证 |
| `guest_main_flow.py` | 游客加购下单支付 |
| `guest_store_flow.py` | Store 主流程 |
| `guest_promotions_flow.py` | Coupon 下单 |
| `login_flow.py` | 官网登录 storage |

## 配置调试用

| 变量 | 文件 | 说明 |
|------|------|------|
| `CLOUD_PAYMENT_HEADLESS` | `configs/config.py` | 生产默认 `False`；**调试期** payload `debug.headless: true` 覆盖 |
| `CLOUD_BROWSER_SLOW_MO` | `configs/config.py` | 生产 `50`；调试期 `debug.slow_mo: 0` |
| `CLOUD_BROWSER_PROXY` | `configs/config.py` | 不需要时设 `None`（可显著缩短调试） |
| `CLOUD_DEFAULT_TIMEOUT_MS` | `configs/config.py` | 默认 30000；定位器稳定后可不改 |
| payload `debug.*` | 请求体 | 优先于配置文件，仅调试生效 |

## pytest

```bash
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
pytest src/website/test_case -vs -n 0
```

fixtures：`src/website/test_case/conftest.py`（`guest_page`、`email`）。

## 执行后沉淀（第 8 步）

Phase D 通过后 **强制** 执行。完整流程见 [SKILL.md — 执行后沉淀](SKILL.md#6-执行后沉淀强制可节流)。

**节流**：同类问题第 2 次才写 supplemental；多条 merge 后 **一次** rebuild。

| 动作 | 路径 / 命令 |
|------|-------------|
| 问题归类表 | `examples.md` 追加行 |
| skill 规则提升 | `SKILL.md` 禁止事项 / 分阶段调试 |
| RAG 补充知识 | `D:/reolink_knowledge/data/supplemental_cases.json`（`--merge`） |
| 重建索引 | `python D:/reolink_knowledge/build_rag_index.py --rebuild`（批量） |

**RAG case_id 约定**：

| 区间 | 来源 | module_path_text 示例 |
|------|------|------------------------|
| `991000001+` | 站点爬取 | `补充知识 / 测试服站点 / ...` |
| `991100011+` | 自动化示例沉淀（第 8 步） | `补充知识 / 自动化示例` |
| `992000001+` | JMX 导入（`import_jmx_scenarios.py`） | `补充知识 / 接口自动化 / ...` |

勿与禅道真实 case_id 混淆；写入 supplemental **必须 merge**，勿覆盖其他区间。
