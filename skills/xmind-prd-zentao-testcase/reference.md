# xmind-prd-zentao-testcase — 参考

## 1. 导图 `m:` 到标题三级模块的映射示例

以下为示例，实际以当前导图为准：

| 导图路径（示意） | 标题片段 |
|------------------|----------|
| m:前台 / m:主套餐 / m:购买 | `前台-主套餐-购买` |
| m:前台 / m:主套餐 / m:切换 | `前台-主套餐-切换` |
| m:前台 / m:Checkout页面 / m:Billing地址表单 | `前台-Checkout页面-Billing地址表单` |
| m:前台 / m:订阅流程 / m:选择设备 | `前台-订阅流程-选择设备` |

原则：**离测试点最近的三层 `m`** 作为路径；若同一父 `l` 下有多张 `p` 图，可共用一条「UI 对照」用例上传多附件，或按图拆成多条单点用例。

## 2. 预期写法（避免模糊）

不推荐：

- 「文案正确」「页面正常」「功能可用」「与需求一致」

推荐：

- 列出应出现的 **标签**（如 `Total`、`Auto-renew`、`Additional devices`）。  
- 列出应出现的 **提示语义** 或 **原文关键词**（如含 `declined`、`当前周期不可取消`、`Storage Location: United States (Virginia)`）。  
- 数值规则写清 **公式或区间**（如补差价 `P/3×2`）。

## 3. 附件批量上传（Python 驱动示例）

思路：循环 `(case_id, [png文件名...])`，对每个文件调用 `upload_testcase_via_edit_form.py`。

- 图片目录：解压 XMind 后的 `resources/`。  
- 环境变量：`ZENTAO_URL`、`ZENTAO_ACCOUNT`、`ZENTAO_PASSWORD`；若需绕过登录拦截则加 `ZENTAO_WEB_COOKIE`（从浏览器复制，**用后删除**临时文件）。

伪代码结构：

```python
import os, subprocess, sys
os.environ["ZENTAO_URL"] = "https://pms.reolink.com.cn"
# …设置账号与 COOKIE（勿硬编码进仓库）
PAIRS = [(393691, ["a.png", "b.png"]), ...]
PY = "/path/to/upload_testcase_via_edit_form.py"
BASE = "/path/to/xmind/resources"
for case_id, names in PAIRS:
    for n in names:
        subprocess.run([sys.executable, PY, str(case_id), os.path.join(BASE, n)], check=True)
```

## 4. 与 zentao-mcp 的衔接

| 动作 | MCP 工具 |
|------|-----------|
| 解析用例列表 URL | `zentao_parse_testcase_link` |
| 新建 | `zentao_testcase_create` |
| 改标题/步骤/优先级 | `zentao_testcase_update`（步骤整体覆盖） |
| 取详情核对版本/步骤 id | `zentao_testcase_get` |

创建后若用例落在非预期模块，在禅道界面批量调整模块，或在创建时反复核对 `module` 参数。
