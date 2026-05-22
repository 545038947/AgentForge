# MkDocs API 文档系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用 MkDocs + mkdocstrings 创建完整的 API 参考文档系统

**Architecture:** 采用 MkDocs Material 主题，通过 mkdocstrings 自动从 Python docstrings 生成 API 参考。文档分为用户指南、API 参考和进阶指南三部分。

**Tech Stack:** MkDocs, mkdocs-material, mkdocstrings[python]

---

## 文件结构

```
docs/
├── index.md                    # 首页
├── getting-started.md          # 快速开始
├── user-guide/                 # 用户指南（手写）
│   ├── agent.md
│   ├── tools.md
│   ├── memory.md
│   ├── streaming.md
│   └── async.md
├── api-reference/              # API 参考（自动生成）
│   ├── agent.md
│   ├── memory.md
│   ├── tools.md
│   ├── providers.md
│   ├── session.md
│   ├── types.md
│   ├── events.md
│   └── core.md
├── guides/                     # 进阶指南
│   └── memory-extension.md     # 已存在，需移动
└── changelog.md

mkdocs.yml                      # MkDocs 配置
```

---

### Task 1: 添加文档依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 docs 可选依赖**

在 `pyproject.toml` 的 `[project.optional-dependencies]` 中添加：

```toml
docs = [
    "mkdocs>=1.5",
    "mkdocs-material>=9.0",
    "mkdocstrings[python]>=0.24",
    "pymdown-extensions>=10.0",
]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -e ".[docs]"`

Expected: 成功安装 mkdocs, mkdocs-material, mkdocstrings

- [ ] **Step 3: 验证安装**

Run: `mkdocs --version`

Expected: 输出 mkdocs 版本号

---

### Task 2: 创建 MkDocs 配置文件

**Files:**
- Create: `mkdocs.yml`

- [ ] **Step 1: 创建 mkdocs.yml**

```yaml
site_name: AgentForge
site_description: 可复用的 Agent 框架库，支持中国大模型
site_author: AgentForge Team
repo_url: https://github.com/agentforge/agentforge
repo_name: agentforge/agentforge

theme:
  name: material
  language: zh
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.top
    - content.code.copy
    - content.code.annotate
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      toggle:
        icon: material/brightness-7
        name: 切换到深色模式
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      toggle:
        icon: material/brightness-4
        name: 切换到浅色模式

nav:
  - 首页: index.md
  - 快速开始: getting-started.md
  - 用户指南:
      - user-guide/agent.md
      - user-guide/tools.md
      - user-guide/memory.md
      - user-guide/streaming.md
      - user-guide/async.md
  - API 参考:
      - api-reference/agent.md
      - api-reference/memory.md
      - api-reference/tools.md
      - api-reference/providers.md
      - api-reference/session.md
      - api-reference/types.md
      - api-reference/events.md
      - api-reference/core.md
  - 进阶指南:
      - guides/memory-extension.md
  - 更新日志: changelog.md

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: false
            show_root_heading: true
            show_root_toc_entry: true
            show_root_full_path: true
            merge_init_into_class: true
            docstring_style: google
            heading_level: 1

markdown_extensions:
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - admonition
  - toc:
      permalink: true
```

---

### Task 3: 创建首页和快速开始

**Files:**
- Create: `docs/index.md`
- Create: `docs/getting-started.md`

- [ ] **Step 1: 创建 docs/index.md**

```markdown
# AgentForge

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个独立、可复用的 Agent 框架库，支持中国大模型，提供便捷的高层 API 和灵活的扩展点。

## 特性

- **🚀 便捷的高层 API** - 快速构建 Agent 应用
- **🔧 灵活的扩展点** - 可定制 Provider、Tool、Memory 等组件
- **🇨🇳 中国大模型友好** - 内置支持 Kimi、通义千问、DeepSeek
- **📡 流式响应** - 同步/异步流式支持
- **🧠 多层记忆系统** - 支持长期记忆、上下文压缩

## 快速开始

```python
from agentforge import Agent

agent = Agent(model="gpt-4")
response = agent.run("你好")
print(response.content)
```

## 文档

- [快速开始](getting-started.md)
- [用户指南](user-guide/agent.md)
- [API 参考](api-reference/agent.md)
```

- [ ] **Step 2: 创建 docs/getting-started.md**

```markdown
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
```

---

### Task 4: 创建 API 参考页面

**Files:**
- Create: `docs/api-reference/agent.md`
- Create: `docs/api-reference/memory.md`
- Create: `docs/api-reference/tools.md`
- Create: `docs/api-reference/providers.md`
- Create: `docs/api-reference/session.md`
- Create: `docs/api-reference/types.md`
- Create: `docs/api-reference/events.md`
- Create: `docs/api-reference/core.md`

- [ ] **Step 1: 创建 docs/api-reference/agent.md**

```markdown
# Agent API

::: agentforge.agent.Agent
    options:
      show_source: false
      members:
        - __init__
        - run
        - run_async
        - stream
        - stream_async
        - stream_deltas
        - stream_deltas_async
        - enable_memory_store
        - add_memory_entry
        - prefetch
        - sync
        - clear
        - add_tool
        - add_skill
```

- [ ] **Step 2: 创建 docs/api-reference/memory.md**

```markdown
# Memory API

## MemoryManager

::: agentforge.memory.MemoryManager
    options:
      show_source: false

## MemoryStoreBase

::: agentforge.memory.MemoryStoreBase
    options:
      show_source: false

## MemoryStore

::: agentforge.memory.MemoryStore
    options:
      show_source: false

## MemoryMetadata

::: agentforge.memory.MemoryMetadata
    options:
      show_source: false

## MemoryExtractor

::: agentforge.memory.MemoryExtractor
    options:
      show_source: false

::: agentforge.memory.RuleBasedExtractor
    options:
      show_source: false

::: agentforge.memory.create_extractor
```

- [ ] **Step 3: 创建 docs/api-reference/tools.md**

```markdown
# Tools API

## Tool 基类

::: agentforge.tools.Tool
    options:
      show_source: false

::: agentforge.tools.FunctionTool
    options:
      show_source: false

## 工具装饰器

::: agentforge.tools.tool

## 工具执行器

::: agentforge.tools.executor.ToolExecutor
    options:
      show_source: false

## 工具集

::: agentforge.tools.toolsets.ToolsetDefinition
    options:
      show_source: false

::: agentforge.tools.toolsets.ToolsetRegistry
    options:
      show_source: false
```

- [ ] **Step 4: 创建 docs/api-reference/providers.md**

```markdown
# Providers API

## Provider 基类

::: agentforge.providers.Provider
    options:
      show_source: false

## Provider Profile

::: agentforge.providers.profile.ProviderProfile
    options:
      show_source: false

## Transport

::: agentforge.providers.transports.Transport
    options:
      show_source: false

## 内置 Provider

::: agentforge.providers.builtins.openai.OpenAIProvider
    options:
      show_source: false

::: agentforge.providers.builtins.anthropic.AnthropicProvider
    options:
      show_source: false

::: agentforge.providers.builtins.ollama.OllamaProvider
    options:
      show_source: false
```

- [ ] **Step 5: 创建 docs/api-reference/session.md**

```markdown
# Session API

## SessionProvider

::: agentforge.session.SessionProvider
    options:
      show_source: false

## SessionInfo

::: agentforge.session.SessionInfo
    options:
      show_source: false

## MessageRecord

::: agentforge.session.MessageRecord
    options:
      show_source: false

## 内置实现

::: agentforge.session.InMemorySessionProvider
    options:
      show_source: false

::: agentforge.session.FileBasedSessionProvider
    options:
      show_source: false
```

- [ ] **Step 6: 创建 docs/api-reference/types.md**

```markdown
# Types API

## 消息类型

::: agentforge.types.Message
    options:
      show_source: false

::: agentforge.types.TextContent
    options:
      show_source: false

::: agentforge.types.ImageContent
    options:
      show_source: false

::: agentforge.types.ToolUseContent
    options:
      show_source: false

::: agentforge.types.ToolResultContent
    options:
      show_source: false

## 响应类型

::: agentforge.types.NormalizedResponse
    options:
      show_source: false

::: agentforge.types.StreamDelta
    options:
      show_source: false

## 工具类型

::: agentforge.types.ToolCall
    options:
      show_source: false

::: agentforge.types.ToolResult
    options:
      show_source: false

## 使用量

::: agentforge.types.Usage
    options:
      show_source: false
```

- [ ] **Step 7: 创建 docs/api-reference/events.md**

```markdown
# Events API

## EventType

::: agentforge.events.EventType
    options:
      show_source: false

## Event

::: agentforge.events.Event
    options:
      show_source: false

## EventDispatcher

::: agentforge.events.EventDispatcher
    options:
      show_source: false

## 钩子装饰器

::: agentforge.events.on_event
```

- [ ] **Step 8: 创建 docs/api-reference/core.md**

```markdown
# Core API

## 执行引擎

::: agentforge.core.ExecutionEngine
    options:
      show_source: false

::: agentforge.core.ExecutionConfig
    options:
      show_source: false

::: agentforge.core.ExecutionResult
    options:
      show_source: false

## 回退链

::: agentforge.core.FallbackChain
    options:
      show_source: false

## 重试策略

::: agentforge.core.RetryPolicy
    options:
      show_source: false

::: agentforge.core.jittered_backoff

## 流式累积器

::: agentforge.core.StreamAccumulator
    options:
      show_source: false

## 模型能力

::: agentforge.core.ModelCapabilities
    options:
      show_source: false
```

---

### Task 5: 创建用户指南页面

**Files:**
- Create: `docs/user-guide/agent.md`
- Create: `docs/user-guide/tools.md`
- Create: `docs/user-guide/memory.md`
- Create: `docs/user-guide/streaming.md`
- Create: `docs/user-guide/async.md`

- [ ] **Step 1: 创建 docs/user-guide/agent.md**

```markdown
# Agent 使用指南

## 创建 Agent

### 简单方式

```python
from agentforge import Agent

# 自动选择 Provider
agent = Agent(model="gpt-4")
```

### 完整方式

```python
from agentforge import Agent
from agentforge.providers import OpenAIProvider

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
from agentforge import Agent, Settings

settings = Settings(
    max_iterations=10,
    timeout=60.0,
)

agent = Agent(model="gpt-4", settings=settings)
```
```

- [ ] **Step 2: 创建 docs/user-guide/tools.md**

```markdown
# 工具系统指南

## 定义工具

### 函数式工具

```python
from agentforge import tool

@tool
def search(query: str) -> str:
    """搜索网络信息。
    
    Args:
        query: 搜索关键词
    
    Returns:
        搜索结果
    """
    return f"搜索结果: {query}"
```

### 类式工具

```python
from agentforge import FunctionTool

class Calculator(FunctionTool):
    name = "calculator"
    description = "执行数学计算"
    
    def execute(self, expression: str) -> float:
        return eval(expression)
```

## 使用工具

```python
from agentforge import Agent

agent = Agent(model="gpt-4", tools=[search, Calculator()])
response = agent.run("搜索 Python 教程")
```

## 工具护栏

```python
from agentforge.tools import ToolCallGuardrailController

guardrail = ToolCallGuardrailController(
    allowed_tools=["search", "read"],
    max_calls_per_turn=5,
)

agent = Agent(model="gpt-4", tools=[...], guardrails=[guardrail])
```
```

- [ ] **Step 3: 创建 docs/user-guide/memory.md**

```markdown
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
```

- [ ] **Step 4: 创建 docs/user-guide/streaming.md**

```markdown
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
```

- [ ] **Step 5: 创建 docs/user-guide/async.md**

```markdown
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
```

---

### Task 6: 移动现有文档并创建更新日志

**Files:**
- Move: `docs/memory-extension-guide.md` → `docs/guides/memory-extension.md`
- Create: `docs/changelog.md`

- [ ] **Step 1: 移动 memory-extension-guide.md**

Run: `mv docs/memory-extension-guide.md docs/guides/memory-extension.md`

- [ ] **Step 2: 创建 docs/changelog.md**

```markdown
# 更新日志

## 0.1.0 (2025-05)

### 新增

- 核心 Agent 框架
- 多 Provider 支持（OpenAI、Anthropic、Ollama、国产大模型）
- 工具系统（函数式、类式工具）
- 多层记忆系统
  - MemoryStore 长期记忆
  - MemoryMetadata 元数据
  - 自动记忆提取
- 会话持久化
- 流式响应（同步/异步）
- 事件和钩子系统
- 委托系统
```

---

### Task 7: 验证构建

- [ ] **Step 1: 构建 HTML 文档**

Run: `mkdocs build`

Expected: 成功构建，生成 `site/` 目录

- [ ] **Step 2: 本地预览**

Run: `mkdocs serve`

Expected: 在 http://127.0.0.1:8000 可访问文档

- [ ] **Step 3: 检查 API 页面**

打开浏览器访问 http://127.0.0.1:8000/api-reference/agent/

Expected: 显示 Agent 类的完整 API 文档

- [ ] **Step 4: 停止服务**

按 Ctrl+C 停止 mkdocs serve

---

### Task 8: 提交

- [ ] **Step 1: 暂存文件**

```bash
git add mkdocs.yml docs/ pyproject.toml
```

- [ ] **Step 2: 提交**

```bash
git commit -m "$(cat <<'EOF'
docs: 使用 MkDocs 创建 API 文档系统

- 添加 mkdocs-material 和 mkdocstrings 依赖
- 创建完整的目录结构（用户指南、API 参考、进阶指南）
- API 参考自动从 docstrings 生成
- 支持中英文切换和深色模式

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```
