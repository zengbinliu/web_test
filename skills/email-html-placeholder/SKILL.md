---
name: email-html-placeholder
description: >-
  将 Reolink 邮件 example.html 中的动态变量替换为 {占位符}，并生成同名 JSON 映射。
  适用于：邮件 HTML 模板化、email_html 占位符替换、example.html 转模板、批量 SIM/云套餐邮件变量抽取。
---

# 邮件 HTML → 占位符模板

把 `email_html/<场景>/example.html` 里的动态值换成 `{placeholder}`，输出同目录下的模板 HTML + JSON。除占位符外，其余内容必须与 example **逐字节一致**。

## 输入

用户通常提供：

1. **目标目录**（含 `example.html`），例如 `...\email_html\过期云套餐`
2. **参考目录**（已有模板的同类场景），例如 `...\email_html\取消免费云套餐`

若未给参考目录：在 `email_html` 下找同类型已有 `.html`+`.json`（云套餐 / SIM / 取消 / 续费等）。

## 工作流

```
- [ ] 1. 读 example.html + 参考目录的 .html/.json
- [ ] 2. 列出动态字段（Account、套餐、时间、价格、链接 ID、多卡块等）
- [ ] 3. 按参考命名替换为 {占位符}；多块同名字段加 _1/_2
- [ ] 4. 写出 <邮件标题或 h1>.html 与同名 .json
- [ ] 5. 还原占位符后必须与 example 完全相等
```

### 1. 对齐参考模板

- 读参考 JSON：字段名 → 占位符约定
- 读参考 HTML：确认占位符出现位置（正文 / `href` 查询参数）
- **只替换 example 里真实存在的动态值**；参考有但本邮件没有的字段（如 `Cameras Assigned`）不要硬加进 HTML

### 2. 识别动态值（常见）

| 类型 | example 表现 | 占位符（优先与参考一致） |
|------|----------------|--------------------------|
| 账号 | `Account: xxx@...` | `{o_email}` |
| SIM 号 | SIM Card Number 后的值 | `{sim_code}` / `{sim_code_1}` |
| 套餐名 | Current Plan 后的值 | `{email_name}` |
| 到期时间 | Valid until 后的值 | `{email_endingformattedTime}` |
| 录像天数 | `60 days` 等 | `{email_retentionDays}`（整段替换，含 days） |
| 续费/价格数字 | `10.00`（可夹在 `USD` 与 `/month` 或 HTML 注释中） | `{cloud_plan_price}` |
| 订阅/计划 ID | `ps_id=` / `p_id=` / `invoice/` | `{subscription_id}` / `{plan_id}` / `{order_id}` |
| 设备数 | `n/1` | `{associateDevices_len}`（仅 `/` 前数字时按参考） |

字面量通常**不替换**：`Auto-renewal: on/off`、固定文案、静态 CDN/商店链接、`source=Email--%3E...` 等非业务 ID 的 query。

### 3. 多块数据（如下标）

同一邮件出现多张 SIM / 多段相同字段时：

- 第 1 块：`{sim_code_1}`、`{email_name_1}`、`{email_endingformattedTime_1}`、`{cloud_plan_price_1}` …
- 第 2 块：`_2`，以此类推
- JSON key 同步加后缀：`sim_card_1`、`Current_plan_1` …

账号、`order_id` 等全局字段不加块后缀。

### 4. 链接处理

- **只替换会变的 ID**，保留 path、mode、`source=` 等与 example 相同的部分  
  - ✅ `.../invoice/{order_id}?source=Email--%3EOthers`  
  - ✅ `.../checkout?mode=renew&amp;ps_id={subscription_id}&amp;p_id={plan_id}&amp;source=Email--%3EPlan+Expired`  
  - ❌ 不要擅自改成参考里的另一种 `source`，除非用户要求对齐参考
- HTML 实体保持原样（`&amp;` 不要改成 `&`）

### 5. 输出文件

| 文件 | 命名 |
|------|------|
| 模板 HTML | 优先用邮件主标题 / `<h1>` 文案，如 `Your Subscription Plan Has Expired.html` |
| JSON | 与 HTML **同名** `.json` |
| example.html | **保留不删** |

JSON 格式（tab/空格与参考目录风格接近即可）：

```json
{
  "Account": "{o_email}",
  "Current_plan": "{email_name}",
  "Valid until": "{email_endingformattedTime}",
  "Video History": "{email_retentionDays}",
  "cloud_price": "{cloud_plan_price}",
  "subscription_id": "{subscription_id}",
  "plan_id": "{plan_id}"
}
```

仅包含本邮件实际用到的占位符。

### 6. 校验（必须）

1. 每个占位符在 HTML 中出现次数符合预期（通常各 1 次；多块则各块 1 次）
2. 用 example 原值还原所有占位符后：`restored == example` 为 **True**
3. 若不相等：先修非占位符差异，再交付

## 场景参考目录（email_html）

| 场景 | 可参考 |
|------|--------|
| 取消免费云 / 过期云 | `取消免费云套餐` |
| 取消流量 / 批量 SIM | `取消流量套餐`、`付费流量套餐购买`、`批量处理sim卡` |
| 购买/续费 | 同目录下已有 `Thanks for Subscribing*.json` |

根目录通常为：`C:\Users\Reolink\PycharmProjects\my_own_project\email_html`

## 交付说明

简短告知：

- 生成的 HTML / JSON 路径
- 占位符列表（及多块下标说明）
- 已通过「还原后与 example 一致」校验
