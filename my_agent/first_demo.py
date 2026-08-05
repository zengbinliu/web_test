# 基本代码
"""

Agently 是什么
Agently 是一个面向 LLM 应用的 Python 框架（Agent 原生）。核心思路不是「拼一段超长 prompt」，而是：

把请求拆成槽位（角色、信息、指令、输入、输出结构）
用 Schema 描述你要什么结构（字典 + 类型 + 描述）
框架负责解析、校验、必要时重试，你拿到的是可用的 Python 数据

和直接调 OpenAI SDK 的区别
直接调 API	用 Agently
自己拼 prompt、自己 json.loads
.input() + .output(schema)
格式错了自己重试
ensure + 校验流水线自动重试
工具/多步要自己写编排
后续可接 Actions、TriggerFlow

"""
from agently import Agently




"""
Agently 等价于帮你做了：

把 schema 翻译成模型能懂的输出说明
解析返回
缺必填字段时按策略重试
所以脚本里你写的是 业务结构，不是 字符串拼接术。

"""
# 全局配置
Agently.set_settings(
    "OpenAICompatible",  # 使用 OpenAI 兼容的 API 接口
    {
        "base_url": "xxxx",
        "api_key": "xxxxxx",
        "model": "xxxxx",
    }
)

# 创建一个 Agent
gpt = Agently.create_agent()

## 开始对话（最基础）
# result = (
#     gpt.input("告诉我软件测试有哪些方法。")  # 提示词
#         .output({
#         "intro": (str, "一句话介绍", True),
#         "test_way": [(str, "测试方式")],
#     })  # 自定义输出结构化
#         .start()  # 开始对话
# )

#  常见槽位（比只写 input 更稳）
result = (
    gpt
    .role("你是资深 Python 代码审查员")   # 角色
    .info("def add(a,b):\n  return a+b") # 背景资料
    .instruct("不要编造未出现的问题") # 硬性规则
    .input("审阅这段代码") # 本轮用户任务
    .output({
        "summary": (str, "一句话总结", True),
        "issues": [{
            "level": (str, "info/warn/error"),
            "msg": (str, "问题描述", True),
        }],
        "score": (int, "0-100"),
    })
    .start()
)


print(result) # 返回dict
