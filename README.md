# AgentForge

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个独立、可复用的 Agent 框架库，支持中国大模型，提供便捷的高层 API 和灵活的扩展点。

## 特性

- **🚀 便捷的高层 API** - 快速构建 Agent 应用，几行代码即可开始
- **🔧 灵活的扩展点** - 框架开发者可定制 Provider、Tool、Memory 等组件
- **🇨🇳 中国大模型友好** - 内置支持 Kimi、通义千问、DeepSeek 等国产大模型
- **🏠 本地模型支持** - 完整支持 Ollama 本地部署
- **📡 流式响应** - 支持同步/异步流式响应，实时显示生成内容
- **⚡ 异步 API** - 完整的异步支持，适合 Web 服务和高并发场景
- **🛠️ 工具系统** - 灵活的工具定义和执行，支持并发执行
- **🪝 钩子系统** - 轻量级事件驱动，在关键生命周期点触发处理器
- **🧠 记忆系统** - 可插拔的记忆提供者，支持上下文压缩
- **🔄 委托系统** - 子 Agent 创建和结果聚合，支持并行委托

## 安装

```bash
# 基础安装
pip install agentforge

# 安装 OpenAI 支持
pip install agentforge[openai]

# 安装 Anthropic 支持
pip install agentforge[anthropic]

# 安装开发依赖
pip install agentforge[dev]
```

## 快速开始

### 简单对话

```python
from agentforge import Agent, quick_chat

# 方式一：使用便捷函数
response = quick_chat("你好，请介绍一下你自己", model="gpt-4")
print(response)

# 方式二：创建 Agent 实例
agent = Agent(model="gpt-4", api_key="your-api-key")
response = agent.run("你好")
print(response.content)
```

### 流式响应

```python
from agentforge import Agent

agent = Agent(model="gpt-4")

# 同步流式
for chunk in agent.stream("讲一个故事"):
    if chunk.content:
        print(chunk.content, end="", flush=True)

# 增量流式（Token 级别）
for delta in agent.stream_deltas("讲一个故事"):
    if delta.has_content:
        print(delta.content, end="", flush=True)
```

### 异步 API

```python
import asyncio
from agentforge import Agent

async def main():
    agent = Agent(model="gpt-4")
    
    # 异步运行
    response = await agent.run_async("你好")
    print(response.content)
    
    # 异步流式
    async for chunk in agent.stream_async("继续"):
        print(chunk.content, end="", flush=True)
    
    # 异步增量流式
    async for delta in agent.stream_deltas_async("更多"):
        if delta.has_content:
            print(delta.content, end="", flush=True)

asyncio.run(main())
```

### 添加工具

```python
from agentforge import Agent, tool

@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息。"""
    # 模拟天气查询
    return f"{city} 今天天气晴朗，温度 25°C"

agent = Agent(model="gpt-4", tools=[get_weather])
response = agent.run("北京今天天气怎么样？")
print(response.content)
```

### 使用记忆系统

```python
from agentforge import Agent, InMemoryProvider, MemoryManager

# 创建记忆管理器
memory_manager = MemoryManager()
memory_manager.add_provider("session", InMemoryProvider())

# 创建带记忆的 Agent
agent = Agent(model="gpt-4", memory_manager=memory_manager)

# 预取记忆
agent.prefetch()

# 运行对话（会自动保存到记忆）
response1 = agent.run("我叫张三")
response2 = agent.run("我叫什么名字？")  # Agent 会记住 "张三"

# 同步记忆
agent.sync()
```

## 支持的 Provider

### 国际 Provider

| Provider | 模型示例 | 特性支持 |
|----------|----------|----------|
| OpenAI | gpt-4o, gpt-4-turbo | 工具调用、流式、视觉、推理 |
| Anthropic | claude-3.5-sonnet | 工具调用、流式、视觉、缓存、推理 |
| Ollama | llama3.2, gemma2 | 工具调用、流式、本地部署 |

### 中国 Provider

| Provider | 模型示例 | 特性支持 |
|----------|----------|----------|
| Kimi (Moonshot) | moonshot-v1-128k | 工具调用、流式、长上下文 |
| 通义千问 | qwen-max, qwen-plus | 工具调用、流式、视觉 |
| DeepSeek | deepseek-chat, deepseek-reasoner | 工具调用、流式、推理 |

### 自动 Provider 选择

```python
from agentforge import Agent

# 设置环境变量后自动选择
# export OPENAI_API_KEY=sk-xxx
# export ANTHROPIC_API_KEY=sk-xxx
# export DEEPSEEK_API_KEY=sk-xxx

agent = Agent()  # 自动选择有 API Key 的 Provider
response = agent.run("你好")
```

## 架构概览

```
agentforge/
├── agent.py              # Agent 门面类
├── types/                # 类型定义
│   ├── messages.py       # 消息类型
│   ├── responses.py      # 响应类型（含 StreamDelta）
│   ├── tools.py          # 工具类型
│   └── errors.py         # 错误类型
├── providers/            # Provider 实现
│   ├── base.py           # Provider 基类
│   ├── profile.py        # Provider Profile（声明式配置）
│   ├── registry.py       # Provider 注册表
│   ├── transports/       # Transport 层（协议转换）
│   └── builtins/         # 内置 Provider
│       ├── openai.py
│       ├── anthropic.py
│       ├── ollama.py
│       └── chinese/      # 中国大模型
├── tools/                # 工具系统
│   ├── base.py           # 工具基类
│   ├── executor.py       # 工具执行器（支持并发）
│   ├── guardrails.py     # 工具护栏
│   └── toolsets.py       # 工具集
├── core/                 # 核心功能
│   ├── execution.py      # 执行引擎
│   ├── fallback.py       # 回退链
│   ├── stream_accumulator.py  # 流式累积器
│   └── async_utils.py    # 异步工具
├── events/               # 事件系统
│   ├── types.py          # 事件类型
│   └── emitter.py        # 事件发射器
├── memory/               # 记忆系统
│   ├── base.py           # 记忆提供者基类
│   └── builtins/         # 内置记忆提供者
├── skills/               # 技能系统
│   ├── base.py           # 技能基类
│   └── registry.py       # 技能注册表
├── delegation/           # 委托系统
│   ├── config.py         # 委托配置
│   └── manager.py        # 委托管理器
├── hooks/                # 钩子系统
├── session/              # 会话管理
├── interrupt/            # 中断处理
├── context/              # 上下文管理
│   ├── compressor.py     # 上下文压缩
│   └── prompt_caching.py # Prompt 缓存
└── config/               # 配置
    └── settings.py       # 设置
```

## 核心概念

### Provider

Provider 负责与 LLM API 交互，支持多种后端：

```python
from agentforge import Agent
from agentforge.providers import OpenAIProvider, OllamaProvider

# 使用 OpenAI
provider = OpenAIProvider(api_key="sk-xxx", model="gpt-4o")
agent = Agent(provider=provider)

# 使用 Ollama（本地）
provider = OllamaProvider(model="llama3.2", base_url="http://localhost:11434/v1")
agent = Agent(provider=provider)
```

### Transport

Transport 负责协议转换，将不同 Provider 的响应统一为 `NormalizedResponse`：

```python
from agentforge.providers.transports import ChatCompletionsTransport

transport = ChatCompletionsTransport()
normalized = transport.normalize_response(raw_response)
```

### 工具

支持函数式工具和类式工具：

```python
from agentforge import Agent, tool, FunctionTool

# 方式一：装饰器
@tool
def search(query: str) -> str:
    """搜索网络信息。"""
    return f"搜索结果: {query}"

# 方式二：函数式工具
def calculate(a: int, b: int) -> int:
    """计算两个数的和。"""
    return a + b

calc_tool = FunctionTool.from_function(calculate)

agent = Agent(model="gpt-4", tools=[search, calc_tool])
```

### 事件系统

在 Agent 运行过程中监听事件：

```python
from agentforge import Agent, EventType, EventDispatcher

agent = Agent(model="gpt-4")

# 添加事件监听器
def on_stream_delta(data):
    print(data["content"], end="", flush=True)

agent._event_dispatcher.on(EventType.STREAM_DELTA, on_stream_delta)

agent.run("讲一个故事")
```

### 钩子系统

通过钩子在关键生命周期点执行自定义逻辑：

```python
from agentforge.hooks import emit_hook_async, on_event

@on_event("agent:start")
async def on_agent_start(context):
    print("Agent 开始处理...")

@on_event("tool:generated")
async def on_tool_generated(context):
    print(f"工具调用生成: {context.get('tool_calls')}")
```

## 流式响应处理

### 同步流式

```python
from agentforge import Agent, StreamDelta

agent = Agent(model="gpt-4")

# 方式一：完整响应块
for chunk in agent.stream("讲一个故事"):
    print(chunk.content, end="")

# 方式二：Token 增量
for delta in agent.stream_deltas("讲一个故事"):
    if delta.has_content:
        print(delta.content, end="")
    if delta.has_reasoning:
        print(f"[推理] {delta.reasoning}")
    if delta.is_final:
        print(f"\n完成，使用 {delta.usage.total_tokens} tokens")
```

### 异步流式

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

### 工具调用抑制

当有工具调用时，可以抑制文本流式，避免显示冗余内容：

```python
for delta in agent.stream_deltas("帮我查天气", suppress_tool_text=True):
    # 当有工具调用时，文本增量会被抑制
    if delta.has_content:
        print(delta.content)
```

## 委托系统

创建子 Agent 处理特定任务：

```python
from agentforge import Agent
from agentforge.delegation import DelegationManager, TaskSpec

agent = Agent(model="gpt-4")
delegation_manager = DelegationManager(parent_agent=agent)

# 单任务委托
result = delegation_manager.delegate(
    goal="分析这个文件的结构",
    context="文件路径: /path/to/file.py"
)

# 批量委托
from agentforge.delegation import DelegationStrategy

tasks = [
    TaskSpec(goal="搜索 Python 教程"),
    TaskSpec(goal="搜索 JavaScript 教程"),
]

result = delegation_manager.delegate_batch(
    tasks,
    strategy=DelegationStrategy.PARALLEL,  # 并行执行
)
```

## 错误处理

```python
from agentforge import Agent
from agentforge.types.errors import (
    ProviderError,
    ProviderRateLimitError,
    ToolExecutionError,
)

agent = Agent(model="gpt-4")

try:
    response = agent.run("你好")
except ProviderRateLimitError as e:
    print(f"速率限制，请等待: {e}")
except ProviderError as e:
    print(f"Provider 错误: {e}")
except ToolExecutionError as e:
    print(f"工具执行错误: {e}")
```

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_agent.py -v

# 运行覆盖率测试
pytest tests/ --cov=agentforge
```

## 开发

```bash
# 克隆仓库
git clone https://github.com/agentforge/agentforge.git
cd agentforge

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 致谢

AgentForge 的设计参考了 [hermes-agent](https://github.com/example/hermes-agent) 的成熟架构。
