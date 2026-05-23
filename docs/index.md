# AgentForge

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个独立、可复用的 Agent 框架库，支持中国大模型，提供便捷的高层 API 和灵活的扩展点。

## 特性

- **便捷的高层 API** - 快速构建 Agent 应用
- **灵活的扩展点** - 可定制 Provider、Tool、Memory 等组件
- **中国大模型友好** - 内置支持 Kimi、通义千问、DeepSeek
- **流式响应** - 同步/异步流式支持
- **多层记忆系统** - 支持长期记忆、上下文压缩

## 快速开始

```python
from hai_agent import Agent

agent = Agent(model="gpt-4")
response = agent.run("你好")
print(response.content)
```

## 文档

- [快速开始](getting-started.md)
- [用户指南](user-guide/agent.md)
- [API 参考](api-reference/agent.md)
