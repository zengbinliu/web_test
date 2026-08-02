# Dynamic Database SQL Agent

这是一个由真实数据库结构驱动的智能 SQL 工具。`build_table_graph.py` 读取当前数据库的元数据并生成关系图，Flask SQL Agent 自动加载这份图谱，将自然语言需求转换为受限制、可预览和可确认的 SQL 或分层数据计划。

项目不内置任何业务表结构。切换数据库时只需修改根目录 `.env`、重新生成图谱并重启 Flask，不需要修改 Agent 代码或提示词。

## 工作流程

```text
ai_database_mock/.env
   ├── build_table_graph.py ──> table_graph.json + table_relations.html
   └── smart-sql-agent ───────> 读取同一图谱和同一数据库
                                      ↓
                      自然语言 -> 选表 -> 补齐关联路径
                                      ↓
                    生成 SQL / 数据计划 -> 解析校验
                                      ↓
                    查询执行 / 依赖补齐 / 写操作预览与确认
```

多表操作会优先使用数据库声明的外键，其次使用 `.env` 配置的关系提示，最后才考虑按命名推断的关系。缺少关系时，Agent 不会臆造 JOIN 条件。

## Agent 内部逻辑

一次自然语言生成 SQL 的请求按以下步骤处理：

1. `NewSQLAgent` 检查 `table_graph.json` 的修改时间，有变化时自动重新加载。
2. 第一次模型调用只做请求路由：根据精简表目录返回 `task_type` 和直接相关表名。
3. 程序拒绝图谱之外的表，并在多表请求中按关系权重寻找最短路径，自动加入必要的中间表。
4. 程序将目标数据库方言、相关表字段和允许使用的关联关系注入任务提示词。
5. 第二次模型调用生成 SQL；明确涉及多种业务对象的 INSERT 则生成紧凑的分层 JSON 数据计划。
6. SQLGlot 校验普通 SQL；数据计划校验实体数量、真实表字段、显式外键、层级方向和最大总行数。
7. 新增数据缺少常见语义字段时，共享生成器根据字段名、字段类型和元数据生成具体测试值；用户明确值始终优先。
8. 普通 INSERT 可以复用或补齐静态外键依赖；分层计划在事务执行时读取数据库实际生成的父主键并回填子表。
9. SELECT 由服务端限制返回行数；所有写操作先返回最终 SQL 预览和限时确认令牌，确认后才在事务中执行。

模型在这里负责理解语义和提出 SQL，图谱、解析器和事务代码负责决定 SQL 是否可以执行。即使模型输出了越权表名、DDL、无 WHERE 的更新或删除，程序也会拒绝执行。

## 目录

```text
ai_database_mock/
├── .env                       # 唯一运行配置，不提交版本库
├── .env.example               # 配置模板
├── database_config.py         # 建图与 Agent 共用的数据库配置
├── build_table_graph.py       # 跨数据库元数据读取和关系图生成
├── table_graph.json           # 动态生成，不提交版本库
├── table_relations.html       # 动态生成，不提交版本库
├── Prompt/prompt.md           # 需求编写指南
└── smart-sql-agent/
    ├── backend/               # Flask API、字段语义、SQL 生成和安全执行
    ├── frontend/              # 浏览器界面
    └── tests/                 # 自动化测试
```

## 支持的数据库

数据库访问统一使用 SQLAlchemy，SQL 解析和方言转换使用 SQLGlot。常用数据库包括：

- MySQL / MariaDB
- PostgreSQL
- SQLite
- SQL Server
- Oracle
- DuckDB、Snowflake、BigQuery 等具有 SQLAlchemy 驱动和 SQLGlot 方言的数据库

不同数据库需要安装对应驱动。`requirements.txt` 默认包含 MySQL 驱动；其他常用驱动示例：

```powershell
# PostgreSQL
python -m pip install "psycopg[binary]"

# SQL Server，需要系统已安装 ODBC Driver
python -m pip install pyodbc

# Oracle
python -m pip install oracledb
```

某些数据库或驱动对元数据接口支持不完整，使用前应在测试库验证字段、主键和外键是否能够被正确读取。

## 安装

最低支持 Python 3.9。`requirements.txt` 使用环境标记为 Python 3.9 选择兼容版本，例如 NetworkX 3.2.x、mysql-connector-python 8.x、python-dotenv 1.0/1.1 和 Requests 2.31/2.32；Python 3.10 及以上继续使用较新的兼容版本。

Python 3.9 已结束官方安全维护，项目保留兼容主要用于旧环境；新部署建议使用 Python 3.11 或 3.12。

在 `demo` 根目录执行：

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

确认解释器版本：

```powershell
python --version
# Python 3.9.x
```

如果已有 `.env`，不要覆盖，只需补充新增配置。

## 唯一配置文件

建图工具和 SQL Agent 都只读取 `demo\.env`。推荐配置 `DATABASE_URL`：

```dotenv
# MySQL
DATABASE_URL=mysql+mysqlconnector://user:password@127.0.0.1:3306/database_name

# PostgreSQL
DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/database_name

# SQLite，相对路径基于 ai_database_mock 目录
DATABASE_URL=sqlite:///./data/example.db

# SQL Server
DATABASE_URL=mssql+pyodbc://user:password@server/database?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

连接信息包含 `@`、`:`、`/` 等特殊字符时需要进行 URL 编码。MySQL 也可以继续使用旧配置方式：

```dotenv
DATABASE_URL=
DB_DIALECT=mysql+mysqlconnector
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=your_database
DB_SCHEMA=
```

同时配置 GPT-5.6、自定义 OpenAI 兼容接口和应用参数：

```dotenv
LLM_API_KEY=your_api_key
LLM_API_URL=https://your-api-host.example/v1
LLM_MODEL=gpt-5.6
LLM_REASONING_EFFORT=none
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3
LLM_TEMPERATURE=
TABLE_GRAPH_PATH=table_graph.json
AUTO_DEPENDENCY_MAX_ROWS=100
DATA_PLAN_MAX_ENTITIES=20
DATA_PLAN_MAX_PER_PARENT=1000
DATA_PLAN_MAX_ROWS=2000
CONFIRMATION_SECRET=replace-with-a-long-random-secret
```

`LLM_API_URL` 可以填写以 `/v1` 结尾的 API 根地址，也可以填写以
`/chat/completions` 结尾的完整端点。使用根地址时，程序会自动补充
`/chat/completions`。接口需兼容 OpenAI Chat Completions 的请求和响应格式。
如果接口返回 HTML、空正文或其他非 JSON 内容，错误信息会显示 HTTP 状态、
Content-Type、响应摘要和最终请求地址，便于排查代理地址与路由配置。
GPT-5.6 默认不发送 `temperature`；只有明确配置 `LLM_TEMPERATURE` 时才发送。
`LLM_REASONING_EFFORT` 可按接口支持情况设置，留空时不发送该参数。

为避免已有部署立即失效，旧的 `DEEP_API_KEY`、`DEEPSEEK_API_URL` 和
`DEEPSEEK_MODEL` 仍可作为回退配置；新部署应统一使用 `LLM_*`。

`DB_SCHEMA` 用于 PostgreSQL、SQL Server 等具有 schema 概念的数据库。留空时使用驱动报告的默认 schema。

## 生成动态表关系图

修改 `.env` 后运行：

```powershell
python .\build_table_graph.py
```

可选参数：

```powershell
python .\build_table_graph.py --schema public --include-views
python .\build_table_graph.py --no-html
python .\build_table_graph.py --output-dir .\output
```

SQL Agent 默认读取根目录 `table_graph.json`。如果使用其他输出目录，需要同步设置 `TABLE_GRAPH_PATH`。

图谱记录：

- 数据库方言、数据库名、schema 和生成时间。
- 表或视图名称、字段名、字段类型、长度、精度、可空性、默认值和注释。
- 自增、identity、computed、枚举值、唯一约束和检查约束元数据。
- 普通主键和复合主键。
- 显式外键 `explicit_fk`，置信度 1.0。
- 手动关系 `inferred_hint`，置信度 0.95。
- 命名推断 `inferred_naming`，置信度 0.85。

非标准字段关系可以在 `.env` 中配置：

```dotenv
RELATION_HINTS_JSON={"audit.created_by":"account.id","employee.dept_code":"department.code"}
```

## 启动 SQL Agent

在 `demo` 根目录执行：

```powershell
python .\smart-sql-agent\backend\main.py
```

浏览器访问 <http://127.0.0.1:8000>。

Agent 在每次请求前检查图谱修改时间。同一个数据库结构变化后，重新运行建图脚本即可热加载新图谱；如果修改了 `.env` 或切换数据库连接，需要重启 Flask。

## 分层多表测试数据

同时创建存在父子关系的多种对象时，需求会走分层数据计划，而不是让模型猜测数据库生成的主键。通用请求格式：

```text
精确创建[根数量]个[根对象]，每个[根对象]创建[一级数量]个[一级子对象]，
每个[一级子对象]至少创建[二级数量]个[二级子对象]。
只使用数据库真实显式外键，展示每层数量、总行数、分层计划和全部具体SQL。
```

只要当前图谱存在对应的真实显式外键，预览会按层级计算：

```text
根层总数 = 根数量
一级总数 = 根数量 × 一级数量
二级总数 = 根数量 × 一级数量 × 二级数量
总写入行数 = 各层总数之和
```

浏览器会分层展示两份相互对应的结果：

1. **分层数据计划**：展示实体、父子关系、每层数量、固定值、通用字段生成器和用于生成唯一值的种子。
2. **具体 SQL**：按当前数据库方言将计划完整展开为每一条 `INSERT`，不是只有数量摘要。MySQL 使用 `LAST_INSERT_ID()` 和会话变量展示父主键如何传给子表；其他数据库使用主键回填占位符，实际值由 SQLAlchemy 执行器传递。

```text
INSERT INTO <真实根表> (<真实字段...>) VALUES (<具体值...>);
读取数据库生成的 <根主键>；
INSERT INTO <真实子表> (<根外键>, <真实字段...>) VALUES (<根主键>, <具体值...>);
读取数据库生成的 <子主键>；
INSERT INTO <真实孙表> (<子外键>, <真实字段...>) VALUES (<子主键>, <具体值...>);
```

计划生成后会根据元数据检查非空且没有默认值的普通字段。缺失的常见语义字段可由共享生成器补齐；其余必填字段缺失，或被填写为不允许的 `NULL`、空文本、空对象或空数组时，Agent 会把校验错误反馈给模型并自动重新生成一次。状态流转、跨字段公式、比例分布和其他项目业务规则仍必须来自字段注释、数据库约束或用户请求。

常见行号、序号、排序号或位置字段在未明确指定时默认对每个父记录从 1 递增。任意数值字段需要其他起点、步长或作用域时，可在计划中使用通用 `sequence` 生成器，并选择对每个父记录重新计数或在整个实体内连续计数。单列唯一字段由固定种子稳定生成，因此同一份计划的 SQL 预览不会随机漂移。

确认后程序按以下方式执行：

1. 插入一条父记录并通过 SQLAlchemy 获取数据库实际生成的主键。
2. 将主键通过图谱中的 `explicit_fk` 回填到每条直属子记录。
3. 对更深层子记录重复此过程，不预先猜测或分配自增 ID。
4. 逐层统计实际完成数量，必须与预览中的各层数量一致。
5. 全部分层记录共用一个事务；任何唯一约束、检查约束、触发器或外键失败都会整体回滚。

计划中的表、字段、父子方向和外键约束都会重新对照当前图谱。确认令牌绑定规范化后的完整计划；图谱或计划内容变化时必须重新预览。页面上的具体 SQL 用于人工检查；真正执行仍通过 SQLAlchemy 参数绑定写入，不直接执行页面中拼接的展示文本。

默认限制为最多 20 个实体层级、每个父记录最多 1000 个直属子记录、计划总计最多 2000 行，分别由 `DATA_PLAN_MAX_ENTITIES`、`DATA_PLAN_MAX_PER_PARENT` 和 `DATA_PLAN_MAX_ROWS` 调整。提高限制会增加事务时间、模型处理量和数据库压力，应先在测试库验证。

## 缺省字段语义推断

用户未在请求或 SQL 中提供值时，Agent 会在字段类型兼容的前提下识别有限的通用名称。支持英文下划线、驼峰命名和常见中文同义词，不依赖任何固定表名或项目：

| 字段语义 | 常见名称示例 | 缺省测试值 |
| --- | --- | --- |
| 邮箱 | `email`、`mail`、`contact_email`、邮箱 | 符合字段长度的测试邮箱，长度允许时使用 `example.test` 域名 |
| 密码、哈希、盐值 | `password`、`passwd`、`pwd`、`password_hash`、`salt`、密码哈希 | 测试密码、SHA-256 十六进制哈希或独立盐值 |
| 金额、价格、数量 | `amount`、`price`、`cost`、`fee`、`balance`、`quantity`、`qty` | 精度范围内的正数 |
| 材料、快照 | `material`、`ingredient`、`snapshot`、材料、物料、快照 | JSON 字段使用非空对象或数组，文本字段使用可辨识测试文本 |
| 行号和顺序 | `line_no`、`row_number`、`seq`、`sort_order`、`position`、行号、序号 | 普通 INSERT 按当前表行序递增；分层计划按每个父记录递增 |
| 其他通用值 | 电话、URL、IP、编码、名称及其常见英文名称 | 类型和长度兼容的专用测试值 |

值来源的固定优先级如下：

```text
用户或计划中的明确值/生成规则
  > 根据字段注释、枚举和检查约束形成的明确值
  > 有限的通用字段名语义
  > 数据库默认值或必填字段的类型兜底
```

用户明确给出的 `NULL`、空文本、空 JSON、数值 `0` 或其他值不会被推断逻辑覆盖；若这些值违反非空或数据库约束，系统会拒绝计划或由数据库事务回滚。枚举候选值优先于字段名推断。无法与字段类型兼容或长度不足时会失败关闭，不会生成不可解析的数据。

该规则同时用于：

1. 普通 `INSERT ... VALUES`：预览阶段给遗漏的通用字段补值，返回 `planned_sql`，页面自动展示并使用这份最终具体 SQL 进行确认。
2. 分层数据计划：展开每一层时生成具体值，预览中列出 `inferred_fields` 并展示全部具体 SQL。
3. 自动依赖记录：创建缺失父记录时，除引用键和必填字段外，也会为识别出的邮箱、密码哈希等可选字段生成同类值。

这些值只用于测试数据。自动生成的密码和哈希不具备生产凭据的安全策略；真实密码算法、状态机、跨字段计算、行业编码和其他业务规则必须在请求、字段注释或数据库约束中明确。

## 自动补齐缺失依赖数据

INSERT 预览不只展示模型生成的原始语句，还会构建一份可执行的完整写入计划：

1. 解析每一行 `INSERT ... VALUES`，校验表名、字段名和静态外键值。
2. 只沿数据库声明的 `explicit_fk` 检查父记录，不使用人工提示或命名推断自动写库。
3. 外键已经填写时，先检查当前批次，再查询数据库中是否存在对应父记录。
4. 必填外键没有填写时，优先复用数据库中的已有父记录；没有可复用记录时生成父键和父记录。
5. 父记录本身还有显式外键时继续递归检查和补齐。
6. 根据外键方向进行拓扑排序，确保父表 INSERT 位于子表之前。
7. 浏览器用补齐依赖并填充通用缺省字段后的 `planned_sql` 替换原 SQL，确认令牌绑定这份完整 SQL。
8. 确认执行时重新验证依赖状态；状态变化会要求重新预览，不会静默改变已确认计划。

自动父记录会填写引用键、没有默认值的必填字段，以及能够从通用字段语义安全识别的可选字段。邮箱、密码、哈希、金额、材料、快照和行号等值与普通 INSERT、分层计划共用同一个生成器；程序同时遵守字段类型、长度、精度和枚举元数据。生成记录会在预览中标记为“自动补齐依赖”。所有语句在同一个事务内执行，任何唯一约束、检查约束、触发器或外键错误都会导致整体回滚。

以下情况会失败关闭并返回明确错误，不会猜测写入：

- 关系只有 `inferred_hint` 或 `inferred_naming`，没有真实外键。
- 外键值使用函数、子查询等非静态表达式。
- 复合外键只提供了部分字段。
- 缺失父键是 identity/computed 等禁止显式赋值的字段。
- 必填字段类型无法安全生成，或依赖关系形成不可执行的循环。
- 自动补齐数量超过 `AUTO_DEPENDENCY_MAX_ROWS`。

普通 SQL 自动补齐适用于静态外键值。涉及“每个父对象创建 N 个子对象”且父键由数据库生成时，应使用自然语言生成的分层数据计划。

升级到此版本后必须重新运行 `python .\build_table_graph.py`，生成 graph version 3 元数据；旧图谱缺少 identity、枚举和复合外键分组信息，不能提供同等级别的保护。

## SQL 安全边界

- 只允许 SELECT、INSERT ... VALUES、单表 UPDATE 和单表 DELETE。
- SQL 只能引用动态图谱中登记的表。
- UPDATE 和 DELETE 必须包含 WHERE。
- SELECT 返回数量由服务端限制，默认上限为 100。
- 所有写操作必须先预览；确认令牌与 SQL 或规范化数据计划绑定并具有有效期。
- 自动补齐依赖或缺省字段后的完整 SQL 必须重新展示，并由该完整 SQL 的确认令牌授权。
- 多条写语句和分层计划均在单个数据库事务中执行，任一步失败时整体回滚。
- DDL、INSERT ... SELECT、多表 UPDATE/DELETE 和未知表会被拒绝。

这些校验不能替代数据库权限控制。建议使用专用账号，并仅授予目标 schema 所需的最小权限；不要让应用账号拥有建库、删库、授权或系统表权限。

表结构目录和自然语言需求会发送给配置的模型接口，用于选表及生成 SQL。敏感字段名或表注释不适合发送到外部模型时，应使用私有模型服务或停止使用生成接口。

## 编写需求

通用的单表、多表、测试数据、校验和清理需求模板见 `Prompt/prompt.md`。需求中应描述不能由通用字段名可靠判断的业务规则，不需要粘贴 DDL；Agent 会从最新图谱注入真实结构。

## 测试

测试使用临时 SQLite 数据库和临时图谱，不连接 `.env` 中的真实数据库，也不调用真实模型接口。测试套件还会以 Python 3.9 语法规则解析项目中的全部 Python 源码，防止重新引入 3.10+ 专用语法：

```powershell
Set-Location .\smart-sql-agent
python -m unittest discover -s tests -v
```

## 迁移到其他数据库

1. 安装目标数据库的 SQLAlchemy 驱动。
2. 修改根目录 `.env` 中的 `DATABASE_URL` 和可选 `DB_SCHEMA`。
3. 运行 `python .\build_table_graph.py`，检查生成的 graph version 3 JSON 和 HTML 关系图。
4. 对缺失的非标准关系配置 `RELATION_HINTS_JSON`，重新生成图谱。
5. 使用目标库的低权限测试账号启动 Flask。
6. 先执行只读查询和写操作预览，确认方言与影响范围后再允许写入。
