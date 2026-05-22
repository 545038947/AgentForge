# 快速开始

## 安装

```bash
# 基础安装
pip install agentforge

# 安装特定 Provider 支持
pip install agentforge[openai]
pip install agentforge[anthropic]
```

## 简单对话

```python
from agentforge import Agent

agent = Agent(model="gpt-4")
response = agent.run("你好，请介绍一下你自己")
print(response.content)
```

## 流式响应

```python
from agentforge import Agent

agent = Agent(model="gpt-4")

for chunk in agent.stream("讲一个故事"):
    if chunk.content:
        print(chunk.content, end="", flush=True)
```

## 添加工具

```python
from agentforge import Agent, tool

@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气。"""
    return f"{city} 今天天气晴朗"

agent = Agent(model="gpt-4", tools=[get_weather])
response = agent.run("北京天气怎么样？")
```

## 使用记忆

```python
from agentforge import Agent

agent = Agent(model="gpt-4")
agent.enable_memory_store("./memories")
agent.prefetch()

agent.run("我叫张三")
agent.run("我叫什么名字？")  # 会回答 "张三"

agent.sync()
```

## 下一步

- [用户指南](user-guide/agent.md) - 了解 Agent 的完整功能
- [API 参考](api-reference/agent.md) - 查看详细 API 文档
