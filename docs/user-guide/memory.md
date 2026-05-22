# 记忆系统指南

## 启用记忆

```python
from agentforge import Agent

agent = Agent(model="gpt-4")
agent.enable_memory_store("./memories")
```

## 生命周期

```python
# 预取记忆
agent.prefetch()

# 运行对话
agent.run("我叫张三")

# 同步到存储
agent.sync()
```

## 自动记忆提取

```python
# 启用自动提取
agent._memory_manager.enable_auto_extraction()

agent.run("我喜欢 Python")
# 自动提取并存储偏好
```

## 跨会话持久化

```python
# 第一个会话
agent1 = Agent(model="gpt-4")
agent1.enable_memory_store("./memories")
agent1.prefetch()
agent1.run("我叫张三")
agent1.sync()

# 第二个会话
agent2 = Agent(model="gpt-4")
agent2.enable_memory_store("./memories")
agent2.prefetch()
agent2.run("我叫什么？")  # 会回答 "张三"
```
