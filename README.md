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
- **🧠 记忆系统** - 多层记忆架构，支持长期记忆、上下文压缩、跨会话持久化
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

AgentForge 提供多层记忆架构，支持长期记忆存储和跨会话持久化：

```python
from agentforge import Agent

agent = Agent(model="gpt-4")

# 启用长期记忆存储
agent.enable_memory_store("./memories")

# 预取记忆（加载冻结快照）
agent.prefetch()

# 运行对话
agent.run("记住我的名字是张三")

# 同步到存储
agent.sync()

# 新会话 - 记忆会自动恢复
agent2 = Agent(model="gpt-4")
agent2.enable_memory_store("./memories")
agent2.prefetch()
agent2.run("我叫什么名字？")  # Agent 会回答 "张三"
```

### 自动记忆提取

AgentForge 支持从对话中自动提取值得记忆的信息：

```python
from agentforge import Agent

agent = Agent(model="gpt-4")
agent.enable_memory_store("./memories")

# 启用自动提取（基于规则）
agent._memory_manager.enable_auto_extraction()

agent.prefetch()
agent.run("我叫张三，我喜欢使用 Python")

# 自动提取并存储了：
# - "用户名叫张三"
# - "用户偏好：使用 Python"
```

### 自定义记忆存储

开发者可以继承 `MemoryStoreBase` 实现自定义存储：

```python
from agentforge.memory import MemoryStoreBase

class MultiUserMemoryStore(MemoryStoreBase):
    """多用户记忆存储。"""

    def __init__(self, base_path: str, user_id: str):
        # 用户隔离的存储路径
        ...

    # 实现抽象方法...

# 使用自定义存储
agent = Agent(model="gpt-4")
agent._memory_manager.enable_memory_store(
    store=MultiUserMemoryStore("./memories", user_id="user-123")
)
```

详见 [记忆系统扩展指南](docs/memory-extension-guide.md)。

### 记忆层次结构

```
┌─────────────────────────────────────────────────────────────────┐
│                        MemorySystem                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Layer 3: Persistent Memory（MemoryStore）                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  - MEMORY.md: 事实记忆（有界 2200 chars）                 │    │
│  │  - USER.md: 用户偏好（有界 1375 chars）                  │    │
│  │  - 冻结快照模式（保持 LLM 前缀缓存）                     │    │
│  │  - 安全扫描（检测注入攻击）                              │    │
│  │  - 元数据支持（来源、重要性、过期时间）                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                       │
│  Layer 2: Working Memory（ContextCompressor）                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  - Token 预算驱动压缩                                    │    │
│  │  - LLM 辅助摘要生成                                      │    │
│  │  - 工具结果修剪                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                       │
│  Layer 1: Session Memory（SessionProvider）                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  - 文件存储（JSONL）                                     │    │
│  │  - 消息历史持久化                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
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
│   ├── manager.py        # 记忆管理器（生命周期钩子）
│   ├── memory_store_base.py  # 长期记忆抽象基类
│   ├── memory_store.py   # 长期记忆存储（冻结快照）
│   ├── metadata.py       # 记忆元数据（来源、重要性）
│   ├── extractor.py      # 自动记忆提取器
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

## 上下文管理

Agent 的上下文管理是**完全自动**的，包括消息历史维护和智能压缩。

### 自动上下文维护

每次对话时，Agent 自动维护消息历史：

```python
from agentforge import Agent

agent = Agent(model="gpt-4")

# 第一次对话
response1 = agent.run("你好，我叫张三")  # 自动添加用户消息和 assistant 响应

# 第二次对话 - Agent 会记住之前的对话
response2 = agent.run("我叫什么名字？")  # Agent 会回答 "张三"

# 第三次对话 - 上下文继续累积
response3 = agent.run("我们之前聊了什么？")  # Agent 会回顾整个对话历史
```

### 自动上下文压缩

当上下文 Token 数超过阈值时，Agent 会自动压缩：

```python
from agentforge import Agent, Settings

# 配置压缩参数
settings = Settings(
    compression_max_tokens=100000,  # 触发压缩的阈值
    compression_protect_head=3,     # 保护头部消息数（系统提示等）
    compression_protect_tail=5,     # 保护尾部消息数（最近对话）
)

agent = Agent(model="gpt-4", settings=settings)

# 长对话 - 自动压缩
for i in range(100):
    response = agent.run(f"问题 {i}: ...")
    # 当 Token 超过 100000 时，自动压缩中间消息
```

### 压缩策略

压缩时采用**保护策略**：

```
[系统提示] [消息1] [消息2] ... [消息N-5] [消息N-4] [消息N-3] [消息N-2] [消息N-1] [消息N]
    ↑                                                            ↑
 保护头部                                                      保护尾部
(不会压缩)                                                   (不会压缩)
                    ↑
              压缩中间
            (摘要替换)
```

- **保护头部**：系统提示、初始指令等关键消息不会被压缩
- **保护尾部**：最近的对话保持完整，确保当前上下文准确
- **压缩中间**：中间消息会被摘要替换，保留关键信息

### LLM 辅助压缩

AgentForge 支持 LLM 辅助生成高质量摘要：

```python
from agentforge import Agent, Settings

settings = Settings(
    compression_use_llm=True,  # 启用 LLM 辅助摘要
)

agent = Agent(model="gpt-4", settings=settings)

# 长对话 - 自动使用 LLM 生成摘要
for i in range(100):
    agent.run(f"问题 {i}: ...")
    # 当超过阈值时，调用 LLM 生成结构化摘要
```

LLM 摘要采用结构化模板：

```markdown
## 活动任务
## 目标
## 约束与偏好
## 已完成操作
## 进行中
## 关键决策
## 待处理事项
## 相关上下文
```

### 手动控制

```python
from agentforge import Agent

agent = Agent(model="gpt-4")

# 清空当前会话历史
agent.clear()

# 设置系统提示
agent._message_manager.set_system_prompt("你是一个专业的 Python 开发者")

# 查看当前消息数量
print(f"消息数量: {len(agent._message_manager)}")
```

### 跨会话持久化

默认情况下，消息历史仅在内存中。要持久化到存储：

```python
from agentforge import Agent, InMemoryProvider, MemoryManager

# 创建记忆管理器
memory_manager = MemoryManager()
memory_manager.add_provider("conversation", InMemoryProvider())

# 创建带持久化的 Agent
agent = Agent(model="gpt-4", memory_manager=memory_manager)

# 预取之前的对话历史
agent.prefetch()

# 运行对话
response = agent.run("你好")

# 同步保存到存储
agent.sync()
```

### 上下文流程图

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent 对话流程                          │
└─────────────────────────────────────────────────────────────┘

用户消息 ──→ add_user_message()
                    │
                    ▼
            存储到 _messages
                    │
                    ▼
    调用 run()/stream() ──→ get_context()
                                │
                                ▼
                        检查 Token 数量
                                │
                    ┌───────────┴───────────┐
                    │                       │
              超过阈值                  未超过阈值
                    │                       │
                    ▼                       │
              自动压缩                       │
            (保护头尾)                       │
                    │                       │
                    └───────────┬───────────┘
                                │
                                ▼
                    返回上下文给 Provider
                                │
                                ▼
                    Provider 生成响应
                                │
                                ▼
            add_assistant_message() ←── assistant 响应
                    │
                    ▼
            存储到 _messages
                    │
                    ▼
            等待下一轮对话...
```

## 会话持久化

AgentForge 提供独立的会话管理模块，支持会话持久化和历史查询。

### SessionProvider

`SessionProvider` 是会话存储的抽象基类，提供完整的会话生命周期管理：

```python
from agentforge import InMemorySessionProvider

# 创建会话提供者
provider = InMemorySessionProvider()

# 创建新会话
session_id = provider.create_session(
    session_id="session-001",
    source="cli",
    model="gpt-4",
    system_prompt="你是一个助手",
)

# 追加消息
provider.append_message(session_id, "user", "你好")
provider.append_message(session_id, "assistant", "你好！有什么可以帮你的？")

# 获取会话消息
messages = provider.get_messages(session_id)
for msg in messages:
    print(f"{msg.role}: {msg.content}")

# 设置会话标题
provider.set_session_title(session_id, "初次对话")

# 结束会话
provider.end_session(session_id, end_reason="completed")
```

### 会话信息

```python
from agentforge import SessionInfo, MessageRecord

# 会话信息
session = provider.get_session("session-001")
print(f"会话 ID: {session.id}")
print(f"来源: {session.source}")
print(f"模型: {session.model}")
print(f"消息数: {session.message_count}")
print(f"开始时间: {session.started_at}")
```

### 会话搜索

```python
# 搜索消息
results = provider.search_messages("你好", limit=10)

# 列出所有会话
sessions = provider.list_sessions(source="cli", limit=20)

# 通过标题查找会话
session = provider.get_session_by_title("初次对话")
```

### 压缩链追踪

当上下文压缩发生时，可以追踪压缩链：

```python
# 获取压缩链末端的会话
latest_id = provider.get_compression_tip("session-001")

# 获取会话血统（从根到当前）
lineage = provider.get_session_lineage("session-001")
```

### 自定义 SessionProvider

实现自定义的持久化存储：

```python
from agentforge import SessionProvider, SessionInfo, MessageRecord

class DatabaseSessionProvider(SessionProvider):
    """数据库会话提供者示例。"""

    def __init__(self, db_connection):
        self.db = db_connection

    def create_session(self, session_id: str, source: str, **kwargs) -> str:
        self.db.execute(
            "INSERT INTO sessions (id, source, ...) VALUES (?, ?, ...)",
            (session_id, source, ...)
        )
        return session_id

    def get_session(self, session_id: str) -> SessionInfo | None:
        row = self.db.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
        if row:
            return SessionInfo.from_dict(row)
        return None

    # 实现其他抽象方法...
```

### 与 Agent 集成

> **注意**：当前版本 SessionProvider 是独立模块，需要手动管理会话和消息同步。未来版本将提供与 Agent 的自动集成。

手动集成示例：

```python
from agentforge import Agent, InMemorySessionProvider

session_provider = InMemorySessionProvider()
agent = Agent(model="gpt-4")

# 创建会话
session_id = session_provider.create_session(
    session_id="chat-001",
    source="cli",
)

# 运行对话
user_msg = "你好"
session_provider.append_message(session_id, "user", user_msg)
response = agent.run(user_msg)
session_provider.append_message(session_id, "assistant", response.content)

# 恢复会话历史
messages = session_provider.get_messages(session_id)
for msg in messages:
    if msg.role == "user":
        agent._message_manager.add_user_message(msg.content)
    elif msg.role == "assistant":
        # 需要构建 NormalizedResponse
        pass
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
