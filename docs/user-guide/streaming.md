# 流式响应指南

## 同步流式

```python
from agentforge import Agent

agent = Agent(model="gpt-4")

# 完整响应块
for chunk in agent.stream("讲一个故事"):
    print(chunk.content, end="")

# Token 级增量
for delta in agent.stream_deltas("讲一个故事"):
    if delta.has_content:
        print(delta.content, end="")
    if delta.is_final:
        print(f"\n完成，使用 {delta.usage.total_tokens} tokens")
```

## 异步流式

```python
import asyncio
from agentforge import Agent

async def main():
    agent = Agent(model="gpt-4")
    
    async for delta in agent.stream_deltas_async("讲一个故事"):
        if delta.has_content:
            print(delta.content, end="")

asyncio.run(main())
```

## 工具调用抑制

```python
for delta in agent.stream_deltas("查天气", suppress_tool_text=True):
    # 工具调用时不输出冗余文本
    if delta.has_content:
        print(delta.content)
```
