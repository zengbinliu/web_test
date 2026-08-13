# 工作流示例

## 示例 A：纯 API — 设备解绑（接口为主）

禅道步骤：「登录 Cloud → 解绑指定设备 → 验证解绑成功」

### 选型

| # | 禅道步骤 | 实现方式 |
|---|----------|----------|
| 1 | 登录获取 token | **API** `CloudApiUtils.login` |
| 2 | 解绑设备 | **API** `CloudApiUtils.unbind_devices` |
| 3 | 验证设备列表无该 uid | **API** 查询接口断言 |

**不需要** Playwright、YAML、Page Object。

### 调试

```bash
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
python main.py
```

```bash
curl -X POST http://127.0.0.1:5010/cloud/device/unbind \
  -H "Content-Type: application/json" \
  -d "{\"account\":\"liuzb@reolink.com.cn\",\"passwd\":\"bc123456.\",\"uids\":[\"...\"],\"mfa_trust_token\":\"...\"}"
```

失败时直接读 JSON 响应中的 `error_message` 与 `steps[]`，无需查截图。

---

## 示例 B：混合 — 云套餐订阅列表（API 主断言 + UI 抽样）

禅道用例 `186227`：当前/过期订阅列表数据验证。

**推荐 payload**（新账号 + back 收码，对齐 JMeter `注册.jmx` / `领取免费云套餐-295725.jmx`）：

```json
{
  "register_new_account": true,
  "register_email_domain": "t.com",
  "email_account": "liuzb@reolink.com.cn",
  "get_code_type": "back",
  "passwd": "bc123456.",
  "pay_type": "paypal",
  "paid_product_id": "306219407529494",
  "free_plan_key": "basic_lte_plan_us",
  "rich_notification_product_id": "2031801824314902",
  "device_type": "Reolink Video Doorbell WiFi"
}
```

Setup 顺序：**免费 Basic API → PayPal 付费 → 带图推送 API**（付费后再调免费 preview 会 403）。

### 选型

| # | 禅道步骤 | 实现方式 |
|---|----------|----------|
| 1 | 进入 dashboard 查看当前订阅 | **混合**：监听 `GET /v2/cloud/subscriptions/?status=active`，API 过滤断言 + UI 抽样可见卡片 |
| 2 | 查看过期订阅列表 | **混合**：`status=inactive` API 断言排序与范围 + UI 抽样 |

登录使用 `CloudLoginFlow`（默认 **EmailManager** 收码；可选 `get_code_type: "back"` 走 MailProxy）。

### 项目检索

```bash
rg "subscription" src/cloud/utils src/cloud/ui_flows
rg "dashboard/subscription_list" src/cloud/control
```

参考：`cloud_dashboard_subscription_flow.py`、`subscription_list_validator.py`。

### 调试

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/subscription_list \
  -H "Content-Type: application/json" \
  -d "{\"account\":\"liuzb@reolink.com.cn\",\"passwd\":\"bc123456.\",\"email_account\":\"liuzb@reolink.com.cn\",\"email_passwd\":\"ltlbinQq6.\",\"localhost\":\"http://127.0.0.1:5010/\"}"
```

后台 MailProxy 收码时追加 `\"get_code_type\":\"back\"`。

---

## 示例 B2：混合 — Payment History invoice（禅道 156689）

| # | 禅道步骤 | 实现方式 |
|---|----------|----------|
| 1 | 进入 Payment History-invoice 查看订单 | **混合**：API `GET /v2/shop/orders/` + 详情断言；UI 打开 invoice 页校验展示 |

登录：`CloudLoginFlow`，默认 EmailManager；Invoice 链接 `target="_blank"` 需 `expect_popup()`。

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/payment_history_invoice \
  -H "Content-Type: application/json" \
  -d @data/cloud/payload_dashboard_156689.json
```

参考：`cloud_dashboard_payment_history_flow.py`、`payment_history_invoice_validator.py`。

**历史调试问题**（popup、API 详情、cookie 跳过 2FA）→ [按类型归类 — 156689](examples.md#按类型归类的问题与规避执行后沉淀)

---

## 示例 C：纯 UI — Cloud checkout PayPal 支付

支付类步骤**必须走 UI**，不可用 API 替代第三方收银台交互。

### 选型

| # | 禅道步骤 | 实现方式 |
|---|----------|----------|
| 1 | 打开 checkout 支付页 | **UI** `CloudCheckoutPayPage.wait_paypal_button` |
| 2 | 点击 PayPal 支付 | **UI** `click_paypal_in_iframe` |
| 3 | 完成支付 | **UI** `assert_payment_success` |

### Step 1 — MCP + RAG

```
CallMcpTool zentao_testcase_get { "id": 123456 }
```

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py --case 123456 --full
```

### Step 2 — 项目检索

```bash
rg "paypal" src/cloud/ui_flows --glob "*.py"
rg "login_pay" src/cloud/control
```

判定：扩展 `PayPalStrategy` 或新建 Strategy。

### Step 3 — 调试

```bash
curl -X POST http://127.0.0.1:5010/cloud/payment/login_pay \
  -H "Content-Type: application/json" \
  -d "{\"pay_url\":\"...\",\"account\":\"liuzb@reolink.com.cn\",\"passwd\":\"bc123456.\",\"email_account\":\"liuzb@reolink.com.cn\",\"email_passwd\":\"ltlbinQq6.\",\"pay_type\":\"paypal\",\"localhost\":\"http://127.0.0.1:5010/\"}"
```

默认 EmailManager 收码；需 MailProxy 时加 `\"get_code_type\":\"back\"`。

失败时检查 `data.steps` 最后一步与 `error_screenshot_path`。

---

## 示例 D：纯 API — 邮件模板变量校验

禅道步骤：「校验某邮件模板渲染后变量替换正确」

### 选型

| # | 禅道步骤 | 实现方式 |
|---|----------|----------|
| 1 | 传入 parms 渲染邮件 | **API** `POST /cloud/check_email` |
| 2 | 验证 HTML 中变量已替换 | **API** 响应 body 断言 |

无需浏览器。参考 `EmailTemplateService`。

---

## 示例 E：官网游客 Store（UI — 页面展示 + 支付）

禅道模块含「官网」「store」「未登录」→ `src/website/`。

若步骤仅为「Store 页展示某促销文案」→ **UI**；
若步骤为「下单后订单状态为 paid」且 RAG 有订单查询 API → **API 断言订单**，UI 仅完成加购支付。

1. 参考 `GuestStoreFlow.guest_store_main`
2. 步骤一致 → 仅新增 `uiTestType` 与测试数据 JSON
3. 多步骤差异 → 在 `guest_store_flow.py` 增方法

```bash
curl -X POST http://127.0.0.1:5010/uiTest/guest \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

---

## 示例 F：需向用户提问

用例写「使用代理商账号购买满减商品」，但未给出：

- 代理商账号密码
- 具体 SPU/SKU
- 国家站

**应暂停编码**，用 AskQuestion 询问，或列出假设请用户确认。

---

## 示例 G：元素定位失败迭代（仅 UI 场景）

1. 响应 `steps` 停在「点击 Send Code」
2. 打开 `error_scn/date_MMDD/xxx.png`
3. DevTools 核对选择器 → 改 `login_signup_page.yml`
4. 重跑直至该步 `success: true`

勿先在 Python 里加长 `time.sleep`；优先 `wait_ops.retry_until_selector_visible` 与 YAML 超时配置。

**注意**：若失败步骤本质是「应用 API 返回数据」，应改为 API 断言而非继续调 UI 选择器。

---

## 示例 H：前提条件 Setup — 已购买云套餐后再测 Dashboard

禅道用例前提：`已登录` + `已购买云套餐（含免费或付费）`  
正式步骤：进入 dashboard 查看当前订阅列表。

**关键：每次运行都主动执行购买，禁止先查 subscriptions 有则跳过。**

### 前提条件选型表（必须先做）

| # | 禅道前提 | 数据要求 | 实现方式 | RAG/API | 构造后校验 |
|---|----------|----------|----------|---------|------------|
| P1 | 已登录 | 测试账号 | API 主动 login | `POST /v2/auth/token` | token 非空 |
| P2 | 已购买云套餐 | 按前提指定类型 | API+UI **主动购买** | RAG `/v2/shop` + `login_pay` | active 订阅含本次购买 |

### RAG 检索

**MCP 首选**（`askreolink`）：

- `query="已购买云套餐 API checkout"`, `top=8`, `full=true`
- `query="API 分组 /v2/cloud"`, `top=3`

**Shell fallback**（按用例 ID / retrieve-only）：

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py --case <用例ID> --full
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "已购买云套餐 API checkout" --retrieve-only --top 8
```

### 实现要点

1. Service 内 **Phase 0**：优先 `CloudPurchaseSetupFlow`（付费+PayPal）或 `_fulfill_preconditions`，在 Dashboard Flow **之前**执行。
2. P2：**每次**主动购买；**禁止** `if get_subscriptions(): skip`。
3. 购买完成后断言，将 `plan_ctx` 传入正式步骤。
4. Phase 1 **去重**：steps 若含「登录/购买」，仅 logger + 用 `plan_ctx` 校验，**不重复**写操作。
5. 响应 `steps[]` 顺序：`[Setup] 登录` → `[Setup] 购买云套餐` → `步骤1 查看当前订阅` → …

### 反例（禁止）

```python
# ❌ 探测式 — 有套餐就跳过
if api.get_active_subscriptions(token):
    pass  # 直接进入 dashboard
else:
    purchase_plan(...)

# ❌ 注释式
# 请确保测试账号已购买套餐

# ❌ 不传递 Setup 产出物
verify_subscription_list(token)  # 不知道验证的是哪次购买的数据
```

### 正例

```python
plan_ctx = CloudPurchaseSetupFlow(steps_logger=self._log).purchase_paid_cloud_plan(
    session, page, token, args
)
self._log(f"步骤1: 查看订阅（复用 Setup order_id={plan_ctx['order_id']}）")
self._verify_subscription_list(token, plan_ctx, args)  # 仅断言，不再 purchase
```

---

## 示例 I：混合 — 前提购买 + Payment History invoice（禅道 186294）

禅道用例 **186294**：`dashboard-云套餐-payment history-invoice显示`  
前提：`已购买付费云套餐` + `已登录`  
步骤：进入本次购买订单的 invoice，校验 Invoice date、Reolink Innovation Limited 地址及税号（**tax=0 时不展示地址/税号**）。

### 前提条件选型表

| # | 禅道前提 | 数据要求 | 实现方式 | RAG/API | 构造后校验 |
|---|----------|----------|----------|---------|------------|
| P1 | 已登录 | 测试账号 | UI `CloudLoginFlow` + API token | `POST /v2/auth/token` | token 非空 |
| P2 | 已购买付费云套餐 | 月付付费 plan，salePrice>0 | **API 下单 + UI PayPal** | `/v2/shop/orders/` + pay URL | completed 订单 + active 付费订阅 |

### 步骤选型表

| # | 禅道步骤 | Setup 重叠？ | 实现方式 | 复用点 |
|---|----------|--------------|----------|--------|
| 1 | 进入 Payment History-invoice | 否（P2 已购，本步是导航+展示） | **混合** | `CloudDashboardPaymentHistoryFlow` + `plan_ctx['order_id']` |
| 2 | invoice 信息正确 | 否 | **API 主断言 + UI** | `payment_history_invoice_validator` |

### 购买 Setup 链路（复用 CloudPurchaseSetupFlow，每次主动执行）

```
CloudPurchaseSetupFlow.purchase_paid_cloud_plan
  → CloudPurchaseUtils.create_paid_cloud_plan_order（API 下单）
  → PayPalStrategy（close_browser=False）
  → wait_order_completed + assert_active_paid_subscription
  → 返回 plan_ctx（含 order_id）供 invoice 步骤使用
```

底层 API 步骤详见 `cloud_purchase_utils.py`；**勿在 Service 内复制该链路**。

### Cloud 订单支付页 URL（RAG 知识库 991100010）

API 创建订单后，若 `POST /v2/shop/payment/` 响应 `url` 为空，使用：

```
https://cloud.reolink.review/checkout/pay/?o_id={order_id}&mode=create&platform=web
```

项目封装：`CloudPurchaseUtils.build_checkout_pay_url(order_id)`。

### 项目文件

| 文件 | 职责 |
|------|------|
| `src/cloud/utils/cloud_purchase_utils.py` | API 下单、计税、支付 URL |
| `src/cloud/ui_flows/common/payment/cloud_purchase_setup_flow.py` | Setup：购买 + PayPal |
| `src/cloud/services/cloud_dashboard_payment_history_service.py` | 186294 入口，先 Setup 再 invoice |
| `src/cloud/utils/payment_history_invoice_validator.py` | 186294 UI 断言（tax=0 跳过 seller/税号） |
| `data/cloud/payload_dashboard_186294.json` | 请求体示例 |

### RAG 检索

**MCP**：`askreolink(query="checkout pay o_id pay_url", top=5)`、`askreolink(query="API 分组 /v2/shop", top=3)`

**Shell fallback**（按用例 ID）：

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py --case 186294 --full
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "checkout pay o_id pay_url" --retrieve-only --top 5
```

### 交付物

- 路由：`POST /cloud/dashboard/payment_history_invoice`
- Payload：`data/cloud/payload_dashboard_186294.json`
- **默认 Flask + curl**；本例不生成 pytest

```bash
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
python main.py
```

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/payment_history_invoice \
  -H "Content-Type: application/json" \
  -d @data/cloud/payload_dashboard_186294.json
```

payload 关键字段：`product_id`、`billing_country`、`pay_type: paypal`；**不要**写死 `order_id`（由 Setup 购买产生）。

### invoice 断言要点（186294）

| tax | Invoice date | Reolink 地址 | 税号 |
|-----|--------------|--------------|------|
| > 0 | 必须展示 | 必须展示 | 必须展示（或 VAT 明细） |
| = 0 | 必须展示 | **不要求** | **不要求** |

验证 EU 含税场景时，payload 中 `billing_country` 改为 `FR` / `IT`。

**历史调试问题**（Setup 购买、pay_url、tax=0 seller、product_id）→ [按类型归类 — 186294](examples.md#按类型归类的问题与规避执行后沉淀)

---

## 按类型归类的问题与规避（执行后沉淀）

每次自动化**调试通过后**（skill 工作流第 8 步），将本次遇到的问题追加到下表，并同步提升为 skill/reference 规则。

| 类型 | 现象 | 根因 | 规避规则 | 关联用例 |
|------|------|------|----------|----------|
| **UI 定位 / 断言** | 步骤 4 点击 Cellular Tab 后 timeout ~60s，截图显示列表已加载 | 初版用 `.dashboard-content` 等泛化 CSS + 臆测 `SIM`/`Add SIM` 文案，与实际 DOM 不符 | 流量套餐列表以 **`Select All`** 为根 marker，辅以 `+ Add Card` / `Batch Processing` / `ICCID` / `No Plan Active` 任一可见即通过；**编写前**用 Playwright 探测或读 RAG `991100012` | 280429 |
| **页面导航 / 交互** | 直接 click `My Cloud` 找不到 Dashboard 入口 | 顶部 **My Cloud 为 hover 下拉**，需 `hover()` 后再点 `a[href="/user/dashboard/"]` | 复用 `CloudHomePage.click_my_cloud_dashboard()`；YAML：`nav_hover_wait_ms: 800` | 280429 |
| **页面导航 / 交互** | 未登录进 Dashboard 时期望 cloud 站内登录页 | 未登录点击 Dashboard 会 **跨域跳转** `my.reolink.review/login` | `assert_redirected_to_login_page` 用 `url.*login.*` + `#email` 可见，勿写死 cloud 域名 | 280429 |
| **页面导航 / 交互** | 登录后 landing 页断言失败 | 登录成功回到 **`https://cloud.reolink.review/`**（非 my 站、非 dashboard） | `assert_on_cloud_homepage` 匹配 `^https://cloud\.reolink\.review/?$`；步骤 3 需 **再次**从首页导航进 Dashboard | 280429 |
| **环境与调试** | 修 steps 仍每次全量 PayPal Setup，单用例调试 30+ min | skill 无分阶段协议，失败即全量 curl | **Phase B/C/D**：`debug.setup_only` / `skip_setup` / `from_step`；禁止连续 3 次全量；见 [SKILL.md 分阶段调试](SKILL.md#分阶段调试协议调试期强制) | 通用 |
| **环境与调试** | 改 YAML 后重跑仍报旧选择器错误；或 curl 404 | **5010 端口多 Flask 实例**；或旧进程未加载新路由/代码 | 执行前 `netstat -ano \| findstr :5010`，只保留一个 `python main.py`；改 YAML/路由后 **必须重启 Flask** 再 curl | 280429 |
| **RAG / 知识缺失** | RAG 仅有 `/user/subscribe-plan/sim/list` 路由，无 Dashboard Tab 导航细节 | 站点爬取未覆盖 **Dashboard 内 Tab 切换** 与 My Cloud 下拉交互 | 执行后写入 supplemental `991100012`；编写 Dashboard UI 前先 `askreolink "Dashboard My Cloud Cellular Data Service"` | 280429 |
| **RAG / 知识缺失** | 编写 Setup 时不知历史 JMX 调用了哪些 API；`--case` 查不到接口序列 | JMX 知识在 supplemental **992xxx**，`--case` 只查禅道用例 | 工作流第 2 步 **必做第二轮**：`askreolink "<ID> 接口自动化 jmx"`；API 路径以项目封装为准、JMX 作参考 | 通用 |
| **编写前探测** | 首版选择器全错，迭代 3 次才过 | 未在写 Page Object 前探测真实 DOM | UI 新场景：**先**短脚本 probe 导航/Tab（或读 error 截图），**再**定 YAML；probe 脚本用完即删，勿提交 | 280429 |
| **UI 定位 / 自愈** | Phase C Cloud 步骤 timeout，截图元素可见但选择器失效 | 旧 YAML class/文案变更 | Phase C 开 `debug.healing.enabled`；LLM 推理新选择器写回 `page_ele`；**review** `yaml_backups/` 后合入；Phase D 关 persist | 通用 |
| **环境与调试** | `test_llm_connection` 返回 ok=false | Cursor Spend Limit 不足或 `llm.env` 未配置 | `src/cloud/ui_healing/llm.env` 与 askreolink 保持一致；`REOLINK_RAG_LLM_MODEL=auto` | 通用 |
| **UI 定位 / 断言** | 156689：登录成功、API 校验通过，但 UI invoice 断言失败 | Payment History 的 Invoice 链 **`target="_blank"` 新开标签**，原 page 上下文断言不到 popup 内容 | `click_invoice_for_order` 必须用 **`page.expect_popup()`** 捕获新页再断言；见 `cloud_payment_history_page.py` | 156689 |
| **2FA / 登录** | 156689：反复在 EmailManager 2FA 阶段失败或耗时长 | 每次全走 UI 登录 + IMAP 收码不稳定 | 优先从 `cloud_token_storage.json` 注入 **`web_session_auth_code`**（cloud + my 域）；已登录则 **跳过** `CloudLoginFlow`，失败再 fallback 2FA | 156689 |
| **API 选型** | 156689：只校验 UI 或只查列表 API 字段不全 | invoice 数据以 **`GET /v2/shop/orders/{id}` 详情** 为准；列表项字段少于详情 | **混合**：`assert_api_invoice_fields`（API 主断言）+ `assert_ui_invoice_page`（UI 抽样）；勿仅用 `GET /v2/shop/orders/` 列表字段 | 156689 |
| **Setup / 前提** | 186294：脚本只测 invoice 展示，未执行「购买付费云套餐」 | 初版依赖账号**历史订单**，或只做前提文字说明 | Phase 0 **必须** `CloudPurchaseSetupFlow.purchase_paid_cloud_plan`（每次主动 API 下单 + PayPal）；**禁止** `if subscriptions: skip` | 186294 |
| **UI 定位 / 断言** | 186294：US 订单 tax=0 时断言 seller/税号失败 | 用例要求 **tax=0 不展示** Reolink 地址与税号，初版与 156689 共用同一套 seller 断言 | 186294 专用 **`assert_ui_invoice_page_186294`**：`tax>0` 才校验 `Reolink Innovation Limited` + 地址 + 税号；`tax=0` 仅校验 Invoice date | 186294 |
| **API 选型** | 186294：`pick_completed_order` 从列表取单，seller/税号断言缺字段 | **`GET /v2/shop/orders/` 列表不含 seller**；tax 等仅在详情 API | `prefer_seller_info=True` 时逐单 **`get_shop_order`** 详情；或 payload 指定 **`order_id`**（含税 EU 单） | 186294 |
| **RAG / 知识缺失** | 186294 Setup：`POST /v2/shop/payment/` 返回 **`url` 为空** | PayPal SDK 变更后 payment 响应可能无 pay_url | 回退 **`CloudPurchaseUtils.build_checkout_pay_url(order_id)`** → `checkout/pay/?o_id=`；RAG **`991100010`** | 186294 |
| **Setup / 前提** | 186294 Setup：硬编码 `product_id` 报「未找到 plan」 | payload 中 ID 不在当前 `GET /v2/cloud/products` 可见列表，或 **salePrice=0** | 用 **`_pick_paid_product_id`** 动态选 **salePrice>0** 付费 plan；payload 可传 `product_id` 但需 RAG/接口校验存在 | 186294 |
| **环境与调试** | 156689/186294：改 Service/validator 后重跑仍是旧逻辑 | 与 280429 相同：**5010 多 Flask 实例** 或旧进程 | 同 280429：`netstat` 清理 → 单实例 `python main.py` → 再 curl；PayPal Setup 改代码后必重启 | 156689, 186294 |
| **UI 定位 / 断言** | 350422：步骤 3 通过但步骤 4 找不到 ICCID；或 masked 断言误匹配隐藏 DOM | ① 页面级 `Show More` 与设备卡片内 `Show More` 混淆；② ICCID 收起时 DOM 仍有 `visibility:hidden` 节点 | **Show More/Less、ICCID、eye 图标** 必须限定在 **`sim_code` 设备卡片**内；脱敏断言用 **`_first_visible`**，且 `click_show_more` 后须等 **Show Less** 可见 | 350422 |
| **UI 定位 / 断言** | 350422：按禅道「前6后4」构造 regex 匹配失败 | 测试服实际脱敏为 **`ICCID:26***********031013`**（前 2 + `*` + 后 6） | `build_masked_iccid_pattern` 主模式 + `build_masked_iccid_pattern_alt`（前6后4）双模式；以 **可见文本** 为准 | 350422 |
| **Setup / 前提** | 350422 前提仅「已绑定 SIM」，误用 186239 全量购买 Setup | 用例不要求生效中流量套餐 | 轻量 **`SimCardBindSetupFlow`**：DB 取卡 + `POST /v2/devices/sim-cards/bind`；**勿**默认走 `TrafficPurchaseSetupFlow` | 350422 |
| **页面导航 / 交互** | 245200：误入 `doorbell-subscribe-plan` 或独立 Cellular Data Service 页 | `doorbell-subscribe-plan?ymh=` 为**带图推送套餐**；点击套餐整卡或匹配 `Cellular Data` 文案会误点顶栏导航 | **禁止** doorbell 直链；入口 **Dashboard → Cellular 第一张 `No Plan Active` 卡片 → 设备详情 → Purchase a plan**；套餐区只 `scroll_into_view` **勿 click 整卡** | 245200 |
| **UI 定位 / 断言** | 245200：截图已是双卡片套餐页，仍报找不到 `Cellular Data Plan` Tab | 4G 锁卡套餐页为 **`With cloud storage` / `Without cloud storage` 双卡片**，非旧 Tab 布局；`count()` 在 DE 切换重载后瞬时失败 | `assert_on_plan_page` 用 **`_ensure_lock_card_plan_ready()` 轮询**；主 marker：`Select Plan` + 双卡片标签 + `SIM Data`；Tab 文案仅作兼容兜底 | 245200 |
| **UI 定位 / 断言** | 245200：步骤 2 下拉 timeout，`ul.option_list` 不可见 | 自定义下拉选项在 **`ul.option_list > li`**，误点父级 `ul`；触发器匹配到隐藏节点 | SIM 下拉：可见触发器 + **`ul.option_list:visible li`**；合并卡 SIM 取**最后一个可见**下拉；index=0 已有默认档位可跳过 | 245200 |
| **Setup / 前提** | 245200：绑定后立刻进套餐页列表未就绪 | 固定 sleep 不足，products API 尚未返回设备套餐 | **`wait_cellular_products_ready()`** 轮询 `POST /v2/cloud/products`（最多 90s）；Setup 用 **`LockCardBindSetupFlow`**（insert 设备 + 挪威 SIM + OAuth） | 245200 |
| **API 选型** | 245200 步骤 1 仅 UI 肉眼对套餐 | 用例要求以 **`POST /v2/cloud/products`** 为基准 | **`PlanProductsUtils`** 分类 traffic/merged/cloud；UI 断言双卡片 + Subscribe；纯云套餐 API 有但页面不应展示 | 245200 |
| **环境与调试** | 245200：改断言后仍报 `Cellular Data Plan` / 旧直链逻辑 | 与 280429 相同：**5010 多 Flask 实例** | `netstat` 清理 → 单实例重启 → 再 curl | 245200 |
| **API 选型** | 262413 步骤 1.5：methods 解析全为 false，US 断言失败 | `GET /v2/shop/order/payment/methods` 返回 **`supportPasslessCountries`** + **`style.hideAutoRenew`**，非 `autoRenewal` 字段 | 用 **`AutoRenewPaymentMethodsUtils`**：`status=enable` 且 `hideAutoRenew!=true` 且国家在列表内 → 支持；RAG **`991100017`** | 262413 |
| **Setup / 前提** | 262413：checkout 已勾选 Auto-renewal，订阅 API 仍 `autoRenewal=false` | PayPal 首购未必落库 autoRenew；需 Dashboard 补救或已签约账号 | Setup 传 **`defer_auto_renew_api_assert=true`** + Service **`_ensure_setup_auto_renew_enabled`**（同 258264）；checkout 页显式 **`set_auto_renewal(True)`** | 262413 |
| **2FA / 登录** | 262413 Setup：`sim-cards/bind` 401 | `cloud_token_storage` 过期但 probe 未刷新 | 登录后 **`extract_cloud_access_token_from_page`** 优先用浏览器 localStorage token | 262413 |
| **Setup / 前提** | 252479：Setup 完成后空等 180s，日志卡在 Post-Setup 轮询 | Dashboard Cellular 卡片**不展示 sim_code**，按 sim_code 匹配设备永远失败 | **禁止** Post-Setup 长轮询 sim_code；Setup 后仅 **30s** 等 Dashboard 索引刷新，再用 **uid/iccid/plan_title** 定位已有套餐设备 | 252479 |
| **页面导航 / 交互** | 252479：PayPal 支付成功后卡在 Payment Succeeded，Dashboard 找不到设备 | 支付成功页须点 **Finish** 才回 Dashboard；未 Finish 时后续导航失败 | Setup 支付后调用 **`click_finish_if_payment_succeeded()`**（`payment_finish_button_patterns: ["Finish"]`） | 252479 |
| **UI 定位 / 断言** | 252479：订阅 active 后 Dashboard 仍显示 `No Plan Active`，找不到已有套餐卡片 | `_collect_dashboard_active_plan_cards` 过滤过严；支付后 UI 索引滞后 | 已有套餐设备用 **`_collect_dashboard_cellular_device_cards`** 枚举全部 Cellular 卡；**uid/iccid/plan_title 模糊匹配**（如 `Basic Plan` vs `Basic Plan-SG1`） | 252479 |
| **页面导航 / 交互** | 252479：Dashboard 找不到已有套餐设备（uid 已搜索） | Dashboard 列表设备多、索引滞后；My Devices 有时更快同步 | **优先** Dashboard Cellular + uid 搜索 + iccid/plan_title 匹配；**失败回退** `my_devices`（`require_switch_entry=True`） | 252479 |
| **Setup / 前提** | 252479 前提「已有 traffic/merged 套餐」误用 LockCardBindSetupFlow | 切换页需**已购生效订阅**，仅绑定不够 | Setup 用 **`LockCardPlanPurchaseSetupFlow`**（bind + API 下单 + PayPal/免费 + active 订阅）；payload 传 `setup_plan_kind`（paid_traffic/free_merged 等） | 252479 |
| **API 选型** | 252479 paid_merged：shop preview 400 | 合并套餐 `associateDevices` 缺 **`retentionDays: 0`** | `_build_sim_order_item`：merged 传 `[{uid, retentionDays:0}]`；纯 traffic 可 `associateDevices:[]` | 252479 |
| **Setup / 前提** | 252479 free_*：订单 200 但 subscription 120–180s 超时 | 免费单 deliver 异步，不能立刻查 API 列表 | **`wait_order_subscription_id`** 轮询 order + API/DB；`subscription_wait_timeout_s` 默认 180 | 252479 |
| **2FA / 登录** | 252479 skip_setup：`wait_dashboard_ready` 报 My Dashboard / Current Subscription 不可见 | 2FA 后二次 `goto` 触发 **ERR_ABORTED**；Cellular Tab 下无 Current Subscription | **`_goto_dashboard`** 容错 + Cookie 会话 **`wait_for` 15s** 再 2FA；`wait_dashboard_ready` 认 **Cellular/Cloud Service Tab** | 252479 |
| **页面导航 / 交互** | 252479：PayPal iframe 未就绪时 `fail()` 返回 Flask Response | `prepare_paypal_iframe` 失败直接 `return self.fail()` 污染 Service 返回值 | iframe 未就绪 **走 popup fallback**；`close_browser=False` 时 `raise` 勿 return Response | 252479 |
| **页面导航 / 交互** | 252479 步骤 2/3 第二档位 warning「未找到流量大小选项」 | 页面仅一个 SIM 流量档位时下拉无第二项，属预期 | 第二档位不存在时 **warning 停止**，不 fail；步骤仍判通过（与 245200 一致） | 252479 |
| **Setup / 前提** | 186227：旧账号免费 preview 403；UI app-free-plan Checkout 卡住 | 账号已有 Basic / 860+ 订阅；付费后 **`POST /v2/shop/orders/preview/` 403** | **`register_new_account: true`** + JMeter 注册链（`users.register_with_email` → back 收码 → `/v2/users`）；邮箱域名用 **`@t.com`**（`@reolink.com.cn` 注册后 `account_forbidden`） | 186227 |
| **Setup / 前提** | 186227：Setup 顺序付费→免费失败 | 已有付费订阅后免费 Basic preview 返回 **403** | Setup 顺序固定：**免费 Basic API → PayPal 付费 → 带图推送 API**；禁止付费后再 API 领免费 | 186227 |
| **API 选型** | 186227：带图推送 Setup `oauth2/authorization` 403 | 新账号 **OAuth 设备绑定**不可用；但订单 **`associateDevices`** 可下单 | 带图推送 **勿** `LockCardUtils.request_device_bound_code`；直接 `create_free_rich_notification_order(uid=...)` | 186227 |
| **API 选型** | 186227：带图推送 active 校验失败 | 测试服 `legacyTag=222`，标题无 `rich` 关键字 | `_is_rich_notification_plan` 识别 **`legacyTag` 222** 或门铃标题 | 186227 |
| **2FA / 登录** | 186227：新 `@t.com` 账号 UI 登录卡在 Send Code | 新注册用户 **无 2FA** | `CloudLoginFlow`：`click_login_submit` 后 **5s 内无 Send Code 即视为密码直登成功** | 186227 |
| **UI 定位 / 断言** | 186227 步骤 2：过期列表 UI 标题顺序与 API 不一致 | 取消后 **`expiredAt=0`**，列表 API 与 UI 排序不稳定 | 步骤 2 **API 直查 inactive Setup 订阅为主**；UI 标题 mismatch 降级 warning；`expiredAt=0` 时不强制 UI 顺序 | 186227 |

**新增行格式**：`| 类型 | 现象 | 根因 | 规避规则 | 关联用例 |`

---

## 示例 J：纯 UI — Dashboard 流量套餐 table（禅道 280429）

禅道用例 **280429**：未登录打开 Dashboard-流量套餐 table。

### 前提条件选型表

| # | 禅道前提 | 数据要求 | 实现方式 | 说明 |
|---|----------|----------|----------|------|
| — | 无（步骤 1 即未登录） | 游客态 | 仅注入 `CLOUD_PAY_LOGIN_COOKIES`，**不**注入 session / token | 与「已登录前提」用例不同 |

### 步骤选型表

| # | 禅道步骤 | Setup 重叠？ | 实现方式 | 复用点 |
|---|----------|--------------|----------|--------|
| 1 | 未登录 My Cloud → Cloud Dashboard | 否 | **UI** | `CloudHomePage` hover 导航 → `assert_redirected_to_login_page` |
| 2 | 登录成功 → 首页 | 否 | **UI** | `CloudLoginFlow.login_with_2fa_on_login_page` → `assert_on_cloud_homepage` |
| 3 | 再进 Dashboard 云套餐 table | 否 | **UI** | 复用首页导航 → `assert_cloud_service_table_ready` |
| 4 | 点击 Reolink Cellular Data Service | 否 | **UI** | `click_cellular_data_tab` → `assert_cellular_traffic_list_visible` |

### 关键页面知识（已沉淀 RAG `991100012`）

| 项 | 值 |
|----|-----|
| 入口 | `cloud.reolink.review` 首页 → hover **My Cloud** → **Cloud Dashboard** |
| 未登录跳转 | `my.reolink.review/login`（`#email` + Send Code） |
| 登录后 landing | `https://cloud.reolink.review/` |
| Dashboard URL | `https://cloud.reolink.review/user/dashboard/` |
| 云套餐 Tab | `Reolink Cloud Service` + `Current Subscription` |
| 流量 Tab | `Reolink Cellular Data Service` |
| 列表 marker | `Select All` +（`+ Add Card` \| `Batch Processing` \| `ICCID` \| `No Plan Active`） |

### 项目文件

| 文件 | 职责 |
|------|------|
| `src/cloud/ui_pages/front/home/cloud_home_page.py` | My Cloud hover 导航 |
| `src/cloud/page_ele/front/home/cloud_home_page.yml` | 导航选择器 |
| `src/cloud/ui_flows/common/dashboard/cloud_dashboard_traffic_flow.py` | 四步 Flow |
| `src/cloud/services/cloud_dashboard_traffic_service.py` | Service 入口 |
| `src/cloud/ui_pages/front/dashboard/cloud_dashboard_page.py` | Dashboard Tab + 流量列表断言 |
| `data/cloud/payload_dashboard_280429.json` | 请求体 |

### 交付物

- 路由：`POST /cloud/dashboard/traffic_table`
- Payload：`data/cloud/payload_dashboard_280429.json`

```bash
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
python main.py
```

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/traffic_table \
  -H "Content-Type: application/json" \
  -d @data/cloud/payload_dashboard_280429.json
```

### 本次调试摘要（供第 8 步沉淀参考）

- 前 3 次运行在步骤 4 失败（~65s timeout），第 4 次通过（~5s）
- 修复：流量列表断言从泛化 CSS 改为真实文案 marker；Flask 单实例 + 重启后生效
- 详见上文 [按类型归类的问题与规避](#按类型归类的问题与规避执行后沉淀)

---

## 示例 K：混合 UI — SIM Card 详情卡号/ICCID（禅道 350422）

禅道用例 **350422**：SIM Card详情-SIM卡信息。

### 前提条件选型表

| # | 禅道前提 | 数据要求 | 实现方式 | 说明 |
|---|----------|----------|----------|------|
| 1 | 已登录 | token / cookie / 2FA | **混合** | API token 或 `CloudLoginFlow` + EmailManager |
| 2 | 已绑定 SIM 卡 | 本次绑定 sim_code + iccid | **API** | `SimCardBindSetupFlow`（DB 取未绑定卡 + bind API） |

### 步骤选型表

| # | 禅道步骤 | Setup 重叠？ | 实现方式 | 复用点 |
|---|----------|--------------|----------|--------|
| 1 | 进入 SIM Card 详情 | 否 | **UI** | `CloudDashboardPage.click_cellular_data_tab` → `click_sim_card_in_list(sim_code)` |
| 2 | 展示卡号 | 否 | **UI** | `assert_sim_code_visible(sim_code)` |
| 3 | Show More + 脱敏 ICCID | 否 | **UI** | 设备卡片内 `click_show_more` → `assert_iccid_masked` |
| 4 | eye 图标显隐 | 否 | **UI** | `click_iccid_visibility_toggle` → 完整/脱敏切换 |
| 5 | Show Less 收起 | 否 | **UI** | `click_show_less` → `assert_iccid_section_collapsed` |

### 关键页面知识（RAG `991100014`）

| 项 | 值 |
|----|-----|
| 入口 | Dashboard → **Reolink Cellular Data Service** → 点击列表中 **sim_code** |
| 设备卡片 | 含 sim_code 标题 + **Show More/Less**（展开 SIM Card assigned / ICCID） |
| ICCID 脱敏 | `ICCID:26***********031013`（前 2 + `*` + 后 6）；eye 图标切换完整/脱敏 |
| Setup | 仅 bind，**无需**购买流量套餐（区别于 186239） |

### 项目文件

| 文件 | 职责 |
|------|------|
| `src/cloud/ui_flows/common/dashboard/sim_card_bind_setup_flow.py` | 轻量 Setup |
| `src/cloud/ui_flows/common/dashboard/cloud_dashboard_sim_card_info_flow.py` | 五步 Flow |
| `src/cloud/services/cloud_dashboard_sim_card_info_service.py` | Service 入口 |
| `src/cloud/ui_pages/front/dashboard/cloud_dashboard_sim_card_page.py` | ICCID/Show More 扩展 |
| `data/cloud/payload_dashboard_350422.json` | 请求体 |

### 交付物

- 路由：`POST /cloud/dashboard/sim_card_info`
- Payload：`data/cloud/payload_dashboard_350422.json`

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/sim_card_info \
  -H "Content-Type: application/json" \
  -d @data/cloud/payload_dashboard_350422.json
```

---

## 示例 L：混合 UI — 4G 锁卡套餐购买页（禅道 245200）

禅道用例 **245200**：【4G锁卡版本】4G锁卡设备，套餐购买页面验证。

### 前提条件选型表

| # | 禅道前提 | 数据要求 | 实现方式 | 说明 |
|---|----------|----------|----------|------|
| 1 | 已登录 | token / cookie / 2FA | **混合** | `CloudLoginFlow` + EmailManager；可注入 `web_session_auth_code` |
| 2 | 4G 锁卡设备已绑定 | uid + iccid + sim_code | **API** | `LockCardBindSetupFlow`（insert 设备 + 挪威 SIM + OAuth 绑定） |
| 3 | 套餐数据就绪 | products 含 traffic + merged | **API** | `wait_cellular_products_ready()` 轮询 `POST /v2/cloud/products` |

### 步骤选型表

| # | 禅道步骤 | Setup 重叠？ | 实现方式 | 复用点 |
|---|----------|--------------|----------|--------|
| 1 | 进入套餐购买页，校验列表（US/DE） | 否 | **混合** | Dashboard 第一张 Cellular 卡片 → 详情 → Purchase；`PlanProductsUtils` API 基准 + UI 双卡片断言 |
| 2 | 流量套餐 → 不同流量 → Subscribe → checkout | 否 | **UI** | `Without cloud storage` 卡内下拉 + Subscribe；仅校验 checkout URL |
| 3 | 合并套餐 → 不同流量/存储 → Subscribe → checkout | 否 | **UI** | `With cloud storage` 卡内下拉 + Subscribe；仅校验 checkout URL |

### 关键页面知识（RAG `991100015`）

| 项 | 值 |
|----|-----|
| **禁止入口** | `doorbell-subscribe-plan?ymh=`（带图推送套餐，非 4G 锁卡） |
| **正确入口** | Dashboard → **Reolink Cellular Data Service** → **第一张** `Reolink Go Plus` + `No Plan Active` → 设备详情 → **Purchase a plan** |
| 套餐页布局 | **双卡片**：`With cloud storage`（合并）/ `Without cloud storage`（流量）；标题 `Reolink Cloud Service` + `Select Plan` |
| **非**旧布局 | 无 `Cellular Data Plan` / `Cloud Storage + Cellular Data Plan` Tab |
| 流量下拉 | 自定义 `ul.option_list li`（如 `500MB SIM Data`）；cookie 横幅 `got-it` 需先关闭 |
| API 基准 | `POST /v2/cloud/products`（iccid + uid）；分类 traffic / merged / cloud（cloud 不应在页展示） |
| 导航超时 | `nav_step_timeout_ms: 180000`（单步 3 分钟） |

### 项目文件

| 文件 | 职责 |
|------|------|
| `src/cloud/ui_flows/common/lock_card/lock_card_bind_setup_flow.py` | 4G 锁卡 Setup |
| `src/cloud/utils/lock_card_utils.py` | DB + OAuth + products 轮询 |
| `src/cloud/utils/plan_products_utils.py` | products API 解析与分类 |
| `src/cloud/ui_pages/front/lock_card/cloud_lock_card_plan_page.py` | 导航 + 套餐页断言/操作 |
| `src/cloud/page_ele/front/lock_card/cloud_lock_card_plan_page.yml` | 选择器与超时 |
| `src/cloud/ui_flows/common/lock_card/cloud_lock_card_plan_purchase_flow.py` | 三步 Flow |
| `src/cloud/services/cloud_dashboard_lock_card_plan_service.py` | Service 入口 |
| `data/cloud/payload_dashboard_245200.json` | 请求体 |

### 交付物

- 路由：`POST /cloud/dashboard/lock_card_plan_purchase`
- Payload：`data/cloud/payload_dashboard_245200.json`

```bash
cd D:/web_1151/05测试数据与脚本/自动化/official_website_server
python main.py
```

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/lock_card_plan_purchase \
  -H "Content-Type: application/json" \
  --data-binary @data/cloud/payload_dashboard_245200.json
```

### 本次调试摘要

- 步骤 1 通过后，步骤 2/3 需处理：套餐卡**勿整卡点击**（防跳 Cellular Data Service）、下拉选 **`li` 非 `ul`**、第二档位不存在时 warning 停止
- 详见 [按类型归类 — 245200](examples.md#按类型归类的问题与规避执行后沉淀)

---

## 示例 M：混合 UI — 4G 锁卡套餐切换页（禅道 252479）

禅道用例 **252479**：【4G锁卡版本】4G锁卡设备，套餐切换页面验证。

### 前提条件选型表

| # | 禅道前提 | 数据要求 | 实现方式 | 说明 |
|---|----------|----------|----------|------|
| 1 | 已登录 | token / cookie / 2FA | **混合** | `CloudLoginFlow` + EmailManager |
| 2 | 4G 锁卡设备已绑定且已有套餐 | uid + iccid + active subscription | **混合** | **`LockCardPlanPurchaseSetupFlow`**（bind + API 下单 + PayPal + Finish） |
| 3 | 目标套餐类型 | paid_traffic / free_traffic / paid_merged / free_merged | **API** | payload `setup_plan_kind` 指定；Setup 返回 `plan_title` |

### 步骤选型表

| # | 禅道步骤 | Setup 重叠？ | 实现方式 | 复用点 |
|---|----------|--------------|----------|--------|
| 1 | 进入切换页，校验列表（US/DE） | 否 | **混合** | Dashboard 已有套餐卡片 → Manage Your Subscription → Switch Plan；`PlanProductsUtils` + UI 双卡片 |
| 2 | 流量套餐 → 不同流量 → Choose → checkout | 否 | **UI** | `Without cloud storage` 卡内下拉 + **Choose**（mode=switch） |
| 3 | 合并套餐 → 不同流量/存储 → Choose → checkout | 否 | **UI** | `With cloud storage` 卡内下拉 + Choose |

### 关键页面知识（RAG `991100016`）

| 项 | 值 |
|----|-----|
| **与 245200 区别** | 245200 为**无套餐**购买（Subscribe）；252479 为**已有套餐切换**（Choose，`mode=switch`） |
| **Setup** | `LockCardPlanPurchaseSetupFlow`（非仅 bind）；PayPal 成功后 **Finish** 回 Dashboard |
| **Post-Setup** | **30s** Dashboard 索引等待；**禁止** 180s 轮询 sim_code |
| **入口** | Dashboard → Cellular → **已有套餐设备卡**（uid/iccid/plan_title 匹配）→ Manage Your Subscription → Switch Plan；Dashboard 失败时 **回退 My Devices** |
| **免费 Setup** | 跳过 PayPal；`wait_order_subscription_id` + `wait_subscription_active` |
| **合并下单** | preview/order 须 `associateDevices: [{uid, retentionDays:0}]` |
| **勿用** | doorbell-subscribe-plan 直链 |
| 套餐页布局 | 同 245200：双卡片 + Select Plan；checkout URL 含 `mode=switch&subNew=0` |
| 导航超时 | `nav_step_timeout_ms: 180000` |

### 项目文件

| 文件 | 职责 |
|------|------|
| `src/cloud/ui_flows/common/lock_card/lock_card_plan_purchase_setup_flow.py` | 252479 Setup（购买 + PayPal + Finish） |
| `src/cloud/ui_flows/common/lock_card/cloud_lock_card_plan_switch_flow.py` | 三步 Switch Flow |
| `src/cloud/services/cloud_dashboard_lock_card_plan_switch_service.py` | Service 入口 |
| `src/cloud/ui_pages/front/lock_card/cloud_lock_card_plan_page.py` | 导航/切换页（与 245200 共用） |
| `src/cloud/ui_pages/front/payment/cloud_checkout_pay_page.py` | `click_finish_if_payment_succeeded` |
| `data/cloud/payload_dashboard_252479_paid_traffic.json` 等 4 份 | setup_plan_kind 变体 |

### 交付物

- 路由：`POST /cloud/dashboard/lock_card_plan_switch`
- Payload：`data/cloud/payload_dashboard_252479_<paid\|free>_<traffic\|merged>.json`

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/lock_card_plan_switch \
  -H "Content-Type: application/json" \
  --data-binary @data/cloud/payload_dashboard_252479_paid_traffic.json
```

### 本次调试摘要

- v1–v4 卡在 Post-Setup sim_code 轮询、Dashboard 卡片过滤、merged preview 400
- v5–v6 四变体 **Phase D 全通过**（2026-07-09）：paid_traffic / paid_merged / free_traffic / free_merged
- 关键修复：Finish 回 Dashboard、merged `retentionDays:0`、免费 subscription 轮询、Dashboard/My Devices 双入口、PayPal popup fallback
- 调试协议：`debug.setup_only` / `skip_setup` + `data/cloud/debug_cache/*_setup_ctx.json`
- 详见 [按类型归类 — 252479](examples.md#按类型归类的问题与规避执行后沉淀)

---

## 示例 N：混合 UI/API — 自动续费开关（禅道 262413）

禅道用例 **262413**：自动续费-打开/关闭自动续费，检查自动续费情况。

### 子场景（payload `scenario`）

| scenario | 步骤 | 说明 |
|----------|------|------|
| `close_toggle` | 1.1 | Setup autoRenew ON → Dashboard 关闭 + API false |
| `open_toggle` | 1.2 | 先关后开；已签约 PayPal 直接开启 |
| `serial` | 1.1+1.2 | 默认：同会话关→开 |
| `free_plan` | 1.3 | 云曝光 freePlanTrack → 开开关提示购买 |
| `unsupported_country` | 1.4 | methods 找不支持国 → 隐藏开关 |
| `payment_methods` | 1.5 | 纯 API 多国 methods 解析 |

### 交付物

- 路由：`POST /cloud/dashboard/auto_renew_toggle`
- Payload：`data/cloud/payload_dashboard_auto_renew_toggle_262413.json`

```bash
curl -X POST http://127.0.0.1:5010/cloud/dashboard/auto_renew_toggle \
  -H "Content-Type: application/json" \
  --data-binary @data/cloud/payload_dashboard_auto_renew_toggle_262413_payment_methods.json
```

### 本次调试摘要

- **payment_methods** 已通过（US/CN/DE/FR 解析正确）
- methods 真实字段为 `supportPasslessCountries` + `hideAutoRenew`，非 `autoRenewal`
- UI 子场景需单 Flask + 浏览器 token；PayPal 首购 autoRenew 需 Dashboard 补救（见 258264）
- RAG：**991100017**
