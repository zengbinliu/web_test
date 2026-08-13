# gen_tc — 示例

## 示例 A：Cloud 流量套餐需求 PDF → Excel

**用户输入**：

> 根据 `D:/docs/cloud_cellular_prd.pdf` 生成测试用例，项目 Cloud，版本标签【Cellular v1】，输出到同目录。

**Agent 执行摘要**：

1. **parse_prd.py** → `prd_parsed.json`：Dashboard 入口、Cellular Tab、套餐购买、ICCID 绑定、Batch Processing
2. **RAG（4 轮）**：
   - `askreolink(query="Dashboard Cellular Data Service Tab", top=5, full=true)`
   - `python D:/reolink_knowledge/ask_reolink_testcase_kb.py "流量套餐 购买 主流程" --retrieve-only --top 8`
   - `python D:/reolink_knowledge/ask_reolink_testcase_kb.py "流量套餐 缺陷 边界" --retrieve-only --top 5`
   - `askreolink(query="cellular API /v2/cloud", top=5)`
3. **coverage.md**（节选）：

| 需求来源 | 测试点 | 优先级 | 状态 |
|----------|--------|--------|------|
| §4.1 | 无套餐空态 No Plan Active | P2 | 已覆盖 |
| §3.2 | 有套餐展示 ICCID / Select All | P1 | 已覆盖 |
| §5.3 | 购买补充包后列表刷新 | P1 | 已覆盖 |

4. **cases.json** → `validate_cases.py`（无 ERROR）→ `write_testcases_excel.py`
5. 交付：`cloud_cellular_prd_测试用例_20260709.xlsx` + 同目录 `cases.json` + `coverage.md`

**单条用例（JSON 片段）**：

```json
{
  "id": "TC-003",
  "module": "前台-Dashboard-Cellular Data Service",
  "title": "验证无生效流量套餐时 Cellular 列表展示空态",
  "precondition": "测试账号已登录；账号下无生效中的流量套餐",
  "priority": "P2",
  "steps": [
    "进入 Cloud Dashboard",
    "打开 Cellular Data Service Tab"
  ],
  "expects": [
    "Dashboard 加载完成，My Dashboard 区域可见",
    "列表区域展示 No Plan Active 或等效空态文案；无 ICCID 数据行"
  ],
  "type": "功能测试",
  "requirement_ref": "§4.1 空态展示"
}
```

## 示例 B：Markdown 需求片段 + RAG 补业务规则

**需求片段**（用户粘贴）：

> 同一账号仅允许一个生效的主云套餐；第二次购买应失败并提示不可重复购买。

**流程**：手工需求摘要 → RAG `askreolink(query="主套餐 重复购买 提示", top=5, full=true)` → coverage 两条测试点 → cases.json

| 标题 | 优先级 |
|------|--------|
| …主套餐-购买，验证首次购买主套餐成功 | P1 |
| …主套餐-购买，验证已有生效主套餐时再次购买失败并提示 | P1 |

## 示例 C：校验拦截模糊预期

`validate_cases.py` 输出：

```
[WARNING] TC-005 :: expects :: vague expectation; add concrete keywords or rules: 页面显示正确
```

修复：将预期改为「展示 Subscribe 按钮；套餐状态为 Active」后重新校验。

## 示例 D：仅检索 RAG（用户消息以 askreolink 开头）

用户：`askreolink 国际官网 coupon 代理商 可用范围`

→ 先 MCP `askreolink`；失败则 Shell。结果用于 gen_tc 步骤 2，不跳过 RAG 直接写用例。

## 反例（避免）

| 反例 | 正确做法 |
|------|----------|
| 跳过 coverage 直接写 50 条用例 | 先产出覆盖矩阵，再按 TP 展开 |
| 一条用例标题「验证购买与取消全流程」 | 拆成购买成功、取消成功等各一条 |
| 预期「页面显示正确」 | 列出按钮 Subscribe、状态 Active、提示含 declined |
| 步骤 `1、打开页面` | 改为 `1）打开页面`；validate 会报 ERROR |
| 只给 Markdown 不给 xlsx | 必须运行 `write_testcases_excel.py` 产出 Excel |
| 步骤 12 步不拆分 | >10 步 validate ERROR；>7 步 WARNING，应拆分 |

## 样例文件

- [samples/auto_renew_cases.sample.json](samples/auto_renew_cases.sample.json) — Cloud Auto-renew 完整 JSON（可参考模块路径与前置条件写法）
