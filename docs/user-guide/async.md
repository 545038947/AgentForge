# 异步 API 指南

## 基础异步

```python
import asyncio
from agentforge import Agent

async def main():
    agent = Agent(model="gpt-4")
    
    # 异步运行
    response = await agent.run_async("你好")
    print(response.content)

asyncio.run(main())
```

## 异步流式

```python
async def stream_example():
    agent = Agent(model="gpt-4")
    
    async for delta in agent.stream_deltas_async("讲故事"):
        if delta.has_content:
            print(delta.content, end="", flush=True)
```

## 异步记忆操作

```python
async def memory_example():
    agent = Agent(model="gpt-4")
    agent.enable_memory_store("./memories")
    
    # 异步预取
    await agent.prefetch_async()
    
    await agent.run_async("你好")
    
    # 异步同步
    await agent.sync_async()
```

## 并发请求

```python
async def concurrent_requests():
    agent = Agent(model="gpt-4")
    
    # 并发执行多个请求
    tasks = [
        agent.run_async(f"问题 {i}")
        for i in range(3)
    ]
    
    results = await asyncio.gather(*tasks)
    for r in results:
        print(r.content)
```
