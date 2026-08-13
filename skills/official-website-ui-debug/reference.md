# official_website_server 调试参考

## 关键路径速查

```
main.py                                          # Flask 入口 :5010（以 main.py 为准）
configs/browser_config.py                        # 官网 headless/viewport
configs/cloud_payment_config.py                  # Cloud 支付/代理/人工介入
configs/payment_config.py                        # 官网支付 fallback 选择器
src/website/core/playwright_base.py              # 官网浏览器封装
src/cloud/browser/session.py                     # Cloud BrowserSession
src/cloud/browser/manual_intervention.py         # 人工介入 + 录制
src/cloud/browser/payment_helpers.py             # 截图 URL 拼装
src/cloud/ui_operations/wait_ops.py              # 重试等待
src/cloud/ui_operations/iframe_ops.py            # iframe 切换
src/cloud/services/steps_logger.py               # steps 记录
src/cloud/services/cloud_payment_service.py      # Cloud 支付编排
src/website/test_case/conftest.py                # pytest fixtures
logs/                                            # 按日日志
error_scn/                                       # Cloud 失败截图
static/screenshots/                              # 官网失败截图
data/cloud/manual_recordings/                    # 人工录制
data/website/temporary_storage/                  # storage state / token
data/website/page_ele/                           # 官网元素 YAML
src/cloud/page_ele/                              # Cloud 元素 YAML
```

## Website 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/uiTest/guest` | 游客主流程 |
| POST | `/uiTest/noVerify` | 非 2FA 登录 |
| POST | `/uiTest/needVerify` | 需 2FA 登录 |
| POST | `/payment/login` | 登录用户支付 |
| POST | `/payment/guest` | 游客支付 |
| POST | `/email/getVerifyCode/` | 邮件验证码 |

## Cloud 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/cloud/status` | 健康检查 |
| POST | `/cloud/payment/login_pay` | 登录 + checkout 支付 |
| GET | `/cloud/email_html/error_scn/list` | 失败截图列表 |
| GET | `/cloud/email_html/error_scn/file?name=` | 查看截图 |
| GET | `/cloud/email_html/` | 邮件模板管理页 |

## Cloud 支付 payload 模板

```json
{
  "pay_url": "https://cloud.reolink.review/checkout/pay/?o_id=...&mode=create&platform=web",
  "account": "auto_test_for_cloud@reolink.com.cn",
  "passwd": "...",
  "email_account": "liuzb@reolink.com.cn",
  "email_passwd": "...",
  "pay_type": "paypal",
  "get_code_type": "back",
  "localhost": "http://127.0.0.1:5010/"
}
```

`pay_type` 可选：`paypal`、`adyen`、`payoneer`、`google pay` 等（见 payment registry）。

`localhost` **必填**（调试截图 URL 用），缺则 `error_screenshot_path` 为空。端口须与 `main.py` 一致（当前 **5010**）。

预设账号见 `CLOUD_LOGIN_PRESET`、`CLOUD_DEBUG_PAY_URL`（`cloud_payment_config.py`）。

## YAML 选择器风格

**Cloud**（`src/cloud/page_ele/front/cloud_google_pay_page.yml`）：

```yaml
gpay_button: "button#gpay-button-online-api-id"
gpay_role_button: 'role=button[name="Buy with GPay"]'
btn_wait_timeout_ms: 20000
btn_load_retries: 3
```

**Website**（`data/website/page_ele/front/login_signup_page.yml`）：

```yaml
login_email_input: '#email'
send_code_button: 'role=button[name="Send Code"]'
```

加载方式：
- Cloud：`load_page_yaml("front", "xxx.yml")`
- Website：`read_data.load_yaml(rel(...))`

## 现象 → 排查对照表

| 现象 | 优先排查 | 关键文件 |
|------|----------|----------|
| 元素找不到 | YAML 选择器、iframe、超时 | `page_ele/`, `iframe_ops.py` |
| 严格模式多元素 | `.first`、父级收窄 | Page Object |
| 失败无截图 | 请求缺 `localhost` | `payment_helpers.py` |
| steps 某步 false | 该步截图 + 日志 | API 响应 `steps[]` |
| 2FA 失败 | IMAP / back token | `verify_code_service.py` |
| Google Pay 无态 | storage 缺失 | `manual_login_google_pay.py` |
| 浏览器被关 | `page.is_closed()` | `cloud_google_pay_page.py` |
| 代理超时 | 10809 是否可用 | `cloud_payment_config.py` |
| checkout 未加载 | reload + 重试 | YAML `btn_load_retries` |
| 支付已完成仍跑 | 提前成功退出 | `PaymentAlreadyComplete` |
| Send Code 限流 | 等 60s | `CLOUD_LOGIN_RATE_LIMIT_WAIT_S` |
| pytest 找不到用例 | testpaths 过期 | `pytest src/website/test_case` |

## Cloud 分层调用链

```
payment_control.py
  → CloudPaymentService.run()
    → StepsLogger（记录 steps）
    → BrowserSession（启动 Chrome）
    → CloudLoginFlow（登录 + 2FA）
    → Payment Strategy（paypal/adyen/payoneer/google_pay）
      → Page Object（ui_pages/front/）
      → wait_ops / iframe_ops
      → manual_intervention（失败时）
    → payment_helpers.cloud_pay_error_screenshot（失败截图）
```

## 官网分层

```
website_bp（control/）
  → UiGuestService / UiLoginService
    → PlaywrightBaseSync
    → ui_flows（guest/normal/common）
    → ui_pages/front/
    → data/website/page_ele/
```

## 配置变量一览

| 变量 | 文件 | 默认/说明 |
|------|------|-----------|
| `BROWSER_HEADLESS` | `browser_config.py` | `True` |
| `PAYMENT_BROWSER_HEADLESS` | `browser_config.py` | 支付专用 |
| `CLOUD_PAYMENT_HEADLESS` | `cloud_payment_config.py` | `False` |
| `CLOUD_BROWSER_PROXY` | `cloud_payment_config.py` | `127.0.0.1:10809` |
| `CLOUD_DEFAULT_TIMEOUT_MS` | `cloud_payment_config.py` | `30000` |
| `CLOUD_MANUAL_INTERVENTION_ENABLED` | `cloud_payment_config.py` | `True` |
| `CLOUD_STUCK_TIMEOUT_S` | `cloud_payment_config.py` | `60` |

## pytest 注意

`pytest.ini` 中 `testpaths = src/testcase` 与实际目录 `src/website/test_case` 不一致。

推荐：

```bash
pytest src/website/test_case -vs -n 0
```

fixtures（`conftest.py`）：
- `guest_page`：session 级 `PlaywrightBaseSync`
- `email`：session 级 `EmailManager`
