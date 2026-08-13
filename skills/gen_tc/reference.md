# gen_tc — 参考

## Excel 列定义

与 `02流程规范/测试用例编写规范.md` 对齐，**Sheet 名**：`测试用例`。

| 列序 | 列名 | 必填 | 说明 |
|------|------|------|------|
| A | 用例编号 | 否 | `TC-001` 起递增；导入禅道后可留空由系统生成 |
| B | 所属项目 | 否 | 如 Cloud、国际官网、ERP |
| C | 所属模块 | 否 | `一级-二级-三级`，与需求模块一致 |
| D | 用例名称 | ✅ | 含版本标签时：`【版本】模块路径，测试点` |
| E | 前置条件 | ✅ | 关键状态；勿引用「执行用例 X」 |
| F | 优先级 | ✅ | P1 / P2 / P3 / P4 |
| G | 操作步骤 | ✅ | 多行，每行 `1）…` `2）…` |
| H | 预期结果 | ✅ | 多行，与步骤一一对应：`1）…` `2）…` |
| I | 用例类型 | 否 | 功能测试 / 接口测试 / UI 测试 等 |
| J | 备注 | 否 | 入口、DB 字段、Mock 方法、RAG 引用 |
| K | 需求来源 | 否 | 需求章节/段落编号，便于追溯 |

**步骤编号**：必须使用 **`1）` `2）` `3）`**，禁止 `1、`。

**步骤颗粒度**：建议 ≤7 步（§3.1）；硬上限 10 步（§4.1），超过须拆分用例。

## JSON 结构

中间产物与 `write_testcases_excel.py` 输入格式：

```json
{
  "meta": {
    "project": "Cloud",
    "version_tag": "【Cloud 3.2】",
    "source_prd": "D:/docs/cloud_sim_prd.pdf",
    "sheet_name": "测试用例"
  },
  "cases": [
    {
      "id": "TC-001",
      "module": "前台-Dashboard-Cellular Data Service",
      "title": "验证已购流量套餐用户进入 Cellular Tab 可见套餐列表",
      "precondition": "测试账号已登录；账号下已有生效中的付费流量套餐",
      "priority": "P1",
      "steps": [
        "进入 Cloud Dashboard 首页",
        "点击 My Cloud 下拉，选择 Cellular Data Service",
        "等待 Cellular Tab 内容加载完成"
      ],
      "expects": [
        "Dashboard 首页加载完成，My Dashboard 区域可见",
        "进入 Cellular Data Service 页面，Tab 为选中态",
        "列表区域可见 Select All 或 ICCID 列或 No Plan Active 等列表 marker"
      ],
      "type": "功能测试",
      "remark": "RAG: Dashboard Tab 导航",
      "requirement_ref": "§3.2 流量套餐列表"
    }
  ]
}
```

- `steps` 与 `expects` **数组长度必须相等**
- 脚本会自动加 `1）` 前缀（若原文未带编号）

完整样例见 [samples/auto_renew_cases.sample.json](samples/auto_renew_cases.sample.json)。

## 覆盖矩阵

展开用例前必须产出 `coverage.md`（或 `coverage.json`），用于需求追溯与漏测检查。

### Markdown 模板

```markdown
# 测试点覆盖矩阵

| 需求来源 | 需求描述 | 测试点 ID | 测试点简述 | 设计方法 | 优先级 | 状态 |
|----------|----------|-----------|------------|----------|--------|------|
| §3.2 | 有套餐时展示 ICCID 列表 | TP-001 | 有生效套餐时列表展示 ICCID | 场景法 | P1 | 已覆盖 |
| §4.1 | 无套餐空态 | TP-002 | 无套餐时展示 No Plan Active | 等价类 | P2 | 已覆盖 |
| §5.0 | 重复购买规则未写明上限 | — | 待产品确认并发购买次数 | — | — | 待确认 |
```

### JSON 结构（可选）

```json
{
  "source_prd": "D:/docs/cloud_cellular_prd.pdf",
  "items": [
    {
      "requirement_ref": "§3.2",
      "description": "有套餐时展示 ICCID 列表",
      "test_point_id": "TP-001",
      "test_point": "有生效套餐时列表展示 ICCID",
      "method": "场景法",
      "priority": "P1",
      "case_id": "TC-001",
      "status": "covered"
    }
  ],
  "pending_confirmation": [
    {
      "requirement_ref": "§5.0",
      "question": "并发购买次数上限未定义"
    }
  ]
}
```

`status` 取值：`covered` / `pending_confirmation` / `out_of_scope`。

## parse_prd.py 输出结构

```json
{
  "source": "D:/docs/prd.pdf",
  "format": "pdf",
  "char_count": 12000,
  "line_count": 450,
  "parse_warnings": [],
  "structure": {
    "modules": ["Dashboard", "Cellular Data Service"],
    "rules": ["同一账号仅允许一个生效主套餐"],
    "boundaries": ["单次购买数量不超过 10"],
    "exceptions": ["购买失败时提示 declined"],
    "open_questions": ["多设备绑定上限？"]
  },
  "text": "...(全文，--no-text 可省略)"
}
```

依赖：

| 格式 | 包 |
|------|-----|
| `.docx` | `pip install python-docx` |
| `.pdf` | `pip install pdfplumber` 或 `pip install pymupdf` |

## validate_cases.py 规则

| 级别 | 检查项 |
|------|--------|
| ERROR | 必填字段缺失；steps/expects 数量不等；步骤 `1、` 编号；步骤 >10 |
| WARNING | 模糊预期（「文案正确」「页面正常」等）；步骤 >7；标题疑似多测试点；单模块 P1 >5 |

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\validate_cases.py --input cases.json
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\validate_cases.py --input cases.json --strict
```

## askreolink RAG 查询清单

按需求解析出的模块，**至少 4 轮**检索（MCP 或 Shell，多模块可并行）：

| 轮次 | 目的 | 示例 query |
|------|------|------------|
| 1 | 模块主流程 | `"<模块名> 主流程 购买 订阅"` |
| 2 | 业务规则/计算 | `"coupon 满减 计算规则"`、`"DIY 折扣 精度"` |
| 3 | 历史缺陷/易错点 | `"<模块> 缺陷 边界 案例"` |
| 4 | 接口/API | `"API 分组 /v2/cloud"`、`"checkout pay o_id"` |

补充检索：

| 目的 | 示例 query |
|------|------------|
| 支付/订单状态 | `"PayPal 支付成功 订单状态"` |
| 页面/UI 断言 | `"Dashboard My Cloud Tab 文案"` |

**Shell 常用参数**：

```bash
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<query>" --retrieve-only --top 8
python D:/reolink_knowledge/ask_reolink_testcase_kb.py "<query>" --module cloud --full --top 5
```

**MCP**（`user-flask-mcp-local` 可用时；失败先 `mcp_auth` 再重试）：

- `askreolink(query="...", top=8, full=true)`
- `askreolink(query="...", module="cloud", top=5)`

## 用例设计方法速查

| 方法 | 触发条件 |
|------|----------|
| 等价类 | 输入分类、枚举状态 |
| 边界值 | 数量、金额、长度、日期范围 |
| 场景法 | 用户端到端路径 |
| 判定表 | 多条件组合（国家×支付方式×用户类型） |
| 错误推测 | RAG 历史缺陷、团队缺陷案例库关键词 |

## 脚本命令汇总

**解析需求**：

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\parse_prd.py ^
  --input D:/docs/prd.pdf ^
  --output D:/docs/prd_parsed.json
```

**校验用例**：

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\validate_cases.py --input cases.json
```

**写入 Excel**（默认先校验；`--no-validate` 跳过；`--strict` 警告也阻断）：

```bash
python C:\Users\Reolink\.cursor\skills\gen_tc\scripts\write_testcases_excel.py ^
  --input cases.json ^
  --output D:/web_1151/05测试数据与脚本/测试用例/cloud_sim_测试用例_20260709.xlsx
```

依赖：`openpyxl`（`pip install openpyxl`）。

## 优先级分布参考

| 优先级 | 占比参考 | 说明 |
|--------|----------|------|
| P1 | 10%~15% | 冒烟、主流程 |
| P2 | 20%~35% | 重要功能 |
| P3 | 20%~35% | 异常、一般场景 |
| P4 | 10%~15% | 边缘、纯展示 |
