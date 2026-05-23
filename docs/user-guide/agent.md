# Agent 使用指南

## 创建 Agent

### 简单方式

```python
from hai_agent import Agent

# 自动选择 Provider
agent = Agent(model="gpt-4")
```

### 完整方式

```python
from hai_agent import Agent
from hai_agent.providers import OpenAIProvider

provider = OpenAIProvider(
    api_key="sk-xxx",
    model="gpt-4o",
)

agent = Agent(provider=provider)
```

## 运行对话

### 同步运行

```python
response = agent.run("你好")
print(response.content)
```

### 异步运行

```python
import asyncio

async def main():
    response = await agent.run_async("你好")
    print(response.content)

asyncio.run(main())
```

## 上下文管理

Agent 自动维护对话历史：

```python
agent.run("我叫张三")
agent.run("我叫什么名字？")  # 会回答 "张三"

# 清空历史
agent.clear()
```

## 配置

```python
from hai_agent import Agent, Settings

settings = Settings(
    max_iterations=10,
    timeout=60.0,
)

agent = Agent(model="gpt-4", settings=settings)
```
