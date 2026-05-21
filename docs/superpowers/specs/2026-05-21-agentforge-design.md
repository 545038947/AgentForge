---
title: AgentForge 框架设计文档
version: 1.0.0
date: 2026-05-21
status: draft
---

# AgentForge 框架设计文档

## 1. 概述

### 1.1 目标

AgentForge 是一个独立、可复用的 Agent 框架库，从 hermes-agent 的成熟架构中提取并重构，为其他应用提供：

- **便捷的高层 API**：应用开发者可快速构建 Agent 应用
- **灵活的扩展点**：框架开发者可定制 Provider、Tool、Memory 等组件
- **中国大模型友好**：内置支持 Kimi、通义千问、DeepSeek 等国产大模型
- **跨平台兼容**：支持 Windows、Linux、macOS

### 1.2 设计原则

1. **组件化架构**：各组件通过明确接口协作，可独立扩展和替换
2. **Transport 分离**：协议转换与 Provider 逻辑分离，支持多种 API 格式
3. **流式优先**：所有 Provider 必须实现流式调用，非流式为流式的消费者
4. **协作式中断**：线程安全的中断传播机制，支持跨子 Agent 和工具执行
5. **配置验证**：使用 Pydantic 进行配置验证，敏感信息自动脱敏

### 1.3 目标用户

| 用户类型 | 需求 | API 层级 |
|---------|------|---------|
| 应用开发者 | 快速构建 Agent 应用 | `agentforge` |
| 框架开发者 | 扩展 Provider、Tool 等 | `agentforge.ext` |

### 1.4 技术选型

- **语言**：Python 3.9+
- **并发模型**：同步 + ThreadPoolExecutor
- **配置验证**：Pydantic
- **类型系统**：dataclass + Union 类型
- **分发**：PyPI 单包 `pip install agentforge`

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent (门面)                          │
├─────────────────────────────────────────────────────────────┤
│  MessageManager │ ToolOrchestrator │ DelegationManager       │
│  EventDispatcher │ InterruptHandler                           │
├─────────────────────────────────────────────────────────────┤
│                        Provider                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Transport                         │    │
│  │  convert_messages │ convert_tools │ build_kwargs     │    │
│  │  normalize_response                                 │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  ToolExecutor │ ApprovalCallback │ ContextCompressor        │
├─────────────────────────────────────────────────────────────┤
│  MemoryProvider │ Skill │ EventEmitter                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
agentforge/
├── __init__.py              # 应用开发者 API
├── agent.py                 # Agent 核心类
├── types/
│   ├── __init__.py
│   ├── messages.py          # Message, ContentBlock 类型
│   ├── responses.py         # NormalizedResponse, ToolCall
│   ├── tools.py             # ToolSpec, ToolResult
│   └── errors.py            # 异常层次
├── providers/
│   ├── __init__.py
│   ├── base.py              # Provider 抽象基类
│   ├── capabilities.py      # ProviderCapabilities
│   ├── registry.py          # Provider 注册与发现
│   ├── transports/
│   │   ├── __init__.py
│   │   ├── base.py          # Transport ABC
│   │   ├── types.py         # NormalizedResponse 等
│   │   ├── chat_completions.py
│   │   ├── anthropic.py
│   │   └── adapters/        # Provider 特定适配
│   │       ├── __init__.py
│   │       ├── moonshot.py
│   │       ├── qwen.py
│   │       └── deepseek.py
│   └── builtins/
│       ├── __init__.py
│       ├── openai.py
│       ├── anthropic.py
│       └── chinese/
│           ├── __init__.py
│           ├── moonshot.py
│           ├── qwen.py
│           └── deepseek.py
├── tools/
│   ├── __init__.py
│   ├── base.py              # Tool 基类
│   ├── executor.py          # 并发执行器
│   ├── approval.py          # 审批系统
│   ├── toolsets.py          # 工具集定义
│   └── builtins/
│       ├── __init__.py
│       ├── delegate.py
│       ├── shell.py
│       └── ...
├── delegation/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── isolation.py
│   ├── limits.py
│   └── config.py
├── context/
│   ├── __init__.py
│   ├── compressor.py
│   ├── estimator.py
│   └── protection.py
├── memory/
│   ├── __init__.py
│   ├── base.py
│   └── builtins/
│       ├── __init__.py
│       ├── in_memory.py
│       └── file_based.py
├── skills/
│   ├── __init__.py
│   ├── base.py
│   ├── loader.py
│   └── registry.py
├── events/
│   ├── __init__.py
│   ├── types.py
│   └── emitter.py
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── secrets.py
├── interrupt/
│   ├── __init__.py
│   └── cooperative.py
├── ext/                     # 框架开发者 API
│   └── __init__.py
└── utils/
    ├── __init__.py
    ├── platform.py
    └── logging.py
```

## 3. 公共 API

### 3.1 应用开发者 API

```python
# agentforge/__init__.py

# 核心
from agentforge.agent import Agent
from agentforge.types import (
    Message, ContentBlock, TextContent, ImageContent,
    ToolUseContent, ToolResultContent,
    NormalizedResponse, ToolCall, Usage,
    ToolSpec, ToolResult,
)
from agentforge.errors import (
    AgentForgeError,
    ConfigurationError,
    ProviderError,
    ToolError,
    DelegationError,
    ContextError,
)

# 工具
from agentforge.tools import tool, ToolExecutor

# 配置
from agentforge.config import Settings

# 事件
from agentforge.events import on_event, Event

# 中断
from agentforge.interrupt import InterruptToken

# 便捷函数
from agentforge.agent import create_agent, quick_chat
```

### 3.2 框架开发者 API

```python
# agentforge/ext/__init__.py

# Provider 扩展
from agentforge.providers import Provider, ProviderCapabilities
from agentforge.providers.registry import register_provider, get_provider, list_providers

# Transport 扩展
from agentforge.providers.transports import Transport
from agentforge.providers.transports.types import NormalizedResponse, ToolCall

# Tool 扩展
from agentforge.tools import Tool, ApprovalCallback, ApprovalDecision

# Memory 扩展
from agentforge.memory import MemoryProvider

# Skill 扩展
from agentforge.skills import Skill
from agentforge.skills.registry import register_skill, get_skill

# 事件扩展
from agentforge.events import EventEmitter, EventType
```

### 3.3 使用示例

#### 快速创建 Agent

```python
from agentforge import Agent

agent = Agent(model="gpt-4", api_key="...")
response = agent.run("你好，请帮我分析这段代码")
```

#### 带工具的 Agent

```python
from agentforge import Agent, tool

@tool
def search_web(query: str) -> str:
    """搜索网络获取信息"""
    ...

agent = Agent(model="gpt-4", tools=[search_web])
response = agent.run("今天天气怎么样？")
```

#### 带子 Agent 委托

```python
from agentforge import Agent
from agentforge.tools.builtins import DelegateTool

code_reviewer = Agent(
    model="gpt-4",
    system_prompt="你是一个代码审查专家",
    name="code_reviewer",
)

agent = Agent(
    model="gpt-4",
    tools=[DelegateTool(agents=[code_reviewer])],
)

response = agent.run("请审查这段代码")
```

#### 自定义 Provider

```python
from agentforge.ext import Provider, ProviderCapabilities, register_provider
from agentforge.providers.transports import ChatCompletionsTransport

class MyProvider(Provider):
    name = "my_provider"
    capabilities = ProviderCapabilities(
        supports_tools=True,
        supports_streaming=True,
    )
    
    def _default_transport(self):
        return ChatCompletionsTransport()
    
    def _do_stream(self, messages, tools, **kwargs):
        # 实现流式调用
        ...

register_provider("my_provider", MyProvider)
```

## 4. 核心组件

### 4.1 Agent

Agent 作为门面类，协调各管理器完成对话循环：

```python
class Agent:
    """Agent 门面类，协调各管理器完成对话循环。
    
    职责边界：
    - 对外：提供简洁的公共 API
    - 对内：协调各 Manager 的工作流程
    - 不负责：具体业务逻辑（由 Manager 处理）
    
    Manager 边界：
    - MessageManager：消息历史管理、格式转换
    - ToolOrchestrator：工具执行编排、并发控制
    - DelegationManager：子 Agent 委托、隔离管理
    - EventDispatcher：事件分发、监听器管理
    - InterruptHandler：中断传播、令牌管理
    """
    
    def __init__(
        self,
        model: str,
        api_key: str = None,
        settings: Settings = None,
        tools: List[Union[Tool, Callable]] = None,
        skills: List[Skill] = None,
        memory: MemoryProvider = None,
        **kwargs,
    ):
        self.settings = settings or Settings(model=model, api_key=api_key, **kwargs)
        
        # 初始化各管理器（职责分离）
        self._message_manager = MessageManager(self.settings, memory)
        self._tool_orchestrator = ToolOrchestrator(self.settings)
        self._delegation_manager = DelegationManager(
            self.settings,
            parent_agent=self,
        )
        self._event_dispatcher = EventDispatcher()
        self._interrupt_handler = InterruptHandler()
        self._provider = self._create_provider()
        
        # 注册工具
        self._tools: Dict[str, Tool] = {}
        for t in (tools or []):
            self.add_tool(t)
        
        # 激活技能
        for skill in (skills or []):
            skill.activate(self)
    
    def run(
        self,
        message: Union[str, Message],
        interrupt_token: InterruptToken = None,
    ) -> NormalizedResponse:
        """执行对话循环。
        
        流程：
        1. 添加用户消息到历史
        2. 检查中断
        3. 调用 Provider 获取响应
        4. 处理工具调用（如有）
        5. 返回最终响应
        """
        # 创建中断令牌（如未提供）
        if interrupt_token is None:
            interrupt_token = self._interrupt_handler.create_token()
        
        # 添加用户消息
        if isinstance(message, str):
            message = Message(role="user", content=message)
        self._message_manager.add_message(message)
        
        # 主循环
        while True:
            # 检查中断
            if interrupt_token.is_interrupted:
                raise InterruptException(interrupt_token.reason)
            
            # 获取上下文（可能压缩）
            context = self._message_manager.get_context()
            
            # 调用 Provider
            self._event_dispatcher.emit(Event(
                type=EventType.PROVIDER_REQUEST,
                data={"message_count": len(context)},
            ))
            
            response = self._provider.complete(
                messages=context,
                tools=list(self._tools.values()),
            )
            
            self._event_dispatcher.emit(Event(
                type=EventType.PROVIDER_RESPONSE,
                data={"finish_reason": response.finish_reason},
            ))
            
            # 处理工具调用
            if response.tool_calls:
                # 添加 assistant 消息
                self._message_manager.add_assistant_message(response)
                
                # 执行工具
                tool_results = self._tool_orchestrator.execute(
                    tool_calls=response.tool_calls,
                    tools=self._tools,
                    interrupt_token=interrupt_token,
                )
                
                # 添加工具结果
                self._message_manager.add_tool_results(tool_results)
                
                # 继续循环，获取下一轮响应
                continue
            
            # 无工具调用，返回最终响应
            self._message_manager.add_assistant_message(response)
            return response
    
    def add_tool(self, tool: Union[Tool, Callable]) -> None:
        """添加工具。"""
        if callable(tool) and not isinstance(tool, Tool):
            # 函数装饰器创建的工具
            tool = FunctionTool(tool)
        self._tools[tool.name] = tool
    
    def on(self, event_type: str, callback: Callable, priority: int = 0) -> None:
        """注册事件监听器。"""
        self._event_dispatcher.on(event_type, callback, priority)
    
    def get_interrupt_token(self) -> InterruptToken:
        """获取中断令牌。"""
        return self._interrupt_handler.create_token()
    
    def delegate(
        self,
        task: str,
        agent_name: str = None,
    ) -> DelegationResult:
        """委托任务给子 Agent。"""
        return self._delegation_manager.delegate(task, agent_name)


class MessageManager:
    """消息管理器，负责消息历史和上下文管理。
    
    职责：
    - 维护消息历史
    - 执行上下文压缩
    - 格式转换（Message <-> Provider 格式）
    
    不负责：
    - 消息内容解析（由 Provider/Transport 处理）
    - 工具执行（由 ToolOrchestrator 处理）
    """
    
    def __init__(self, settings: Settings, memory: MemoryProvider = None):
        self._settings = settings
        self._messages: List[Message] = []
        self._compressor = ContextCompressor(settings.compression)
        self._memory = memory
    
    def add_message(self, message: Message) -> None:
        """添加消息到历史。"""
        self._messages.append(message)
        if self._memory:
            self._memory.save(f"msg_{len(self._messages)}", message)
    
    def add_assistant_message(self, response: NormalizedResponse) -> None:
        """添加 assistant 消息。"""
        content = []
        if response.content:
            content.append(TextContent(text=response.content))
        if response.tool_calls:
            for tc in response.tool_calls:
                content.append(ToolUseContent(
                    id=tc.id,
                    name=tc.name,
                    input=json.loads(tc.arguments),
                ))
        self.add_message(Message(role="assistant", content=content))
    
    def add_tool_results(self, results: List[ToolResult]) -> None:
        """添加工具结果消息。"""
        for result in results:
            self.add_message(Message(
                role="user",
                content=[ToolResultContent(
                    tool_use_id=result.tool_call_id,
                    content=result.content,
                    is_error=result.is_error,
                )],
            ))
    
    def get_context(self) -> List[Message]:
        """获取当前上下文（可能压缩）。"""
        if self._compressor.should_compress(self._messages):
            self._messages = self._compressor.compress(self._messages)
        return self._messages.copy()


class ToolOrchestrator:
    """工具编排器，负责工具执行的并发控制。
    
    职责：
    - 管理工具执行器生命周期
    - 编排并发工具调用
    - 处理审批流程
    
    不负责：
    - 工具具体实现（由 Tool 类处理）
    - 消息历史（由 MessageManager 处理）
    """
    
    def __init__(
        self,
        settings: Settings,
        approval_callback: ApprovalCallback = None,
    ):
        self._settings = settings
        self._approval_callback = approval_callback
        self._executor: Optional[ToolExecutor] = None
    
    def execute(
        self,
        tool_calls: List[ToolCall],
        tools: Dict[str, Tool],
        interrupt_token: InterruptToken,
    ) -> List[ToolResult]:
        """执行工具调用。"""
        # 懒加载执行器
        if self._executor is None:
            self._executor = ToolExecutor(
                config=self._settings.executor,
                approval_callback=self._approval_callback,
            )
        
        # 创建执行上下文
        context = ToolExecutionContext(interrupt_token=interrupt_token)
        
        return self._executor.execute(tool_calls, tools, context)
    
    def shutdown(self) -> None:
        """关闭执行器。"""
        if self._executor:
            self._executor.shutdown()
            self._executor = None
```

Provider 负责与 LLM API 交互，持有 Transport 实例：

```python
class Provider(ABC):
    name: str
    capabilities: ProviderCapabilities
    
    def __init__(self, api_key, base_url=None, transport=None):
        self.transport = transport or self._default_transport()
    
    @abstractmethod
    def _default_transport(self) -> Transport:
        ...
    
    @abstractmethod
    def _do_stream(self, messages, tools, **kwargs) -> Iterator:
        ...
    
    def stream(self, messages, tools=None, **kwargs) -> Iterator[NormalizedResponse]:
        converted = self.transport.convert_messages(messages)
        kwargs = self.transport.build_kwargs(...)
        for raw in self._do_stream(converted, **kwargs):
            yield self.transport.normalize_response(raw)
    
    def complete(self, messages, tools=None, **kwargs) -> NormalizedResponse:
        final = None
        for response in self.stream(messages, tools, **kwargs):
            final = response
        return final
```

### 4.3 Transport

Transport 负责协议转换和响应标准化，采用策略模式支持多种 API 格式：

```python
class Transport(ABC):
    """Transport 抽象基类，定义协议转换接口。
    
    Transport 层采用策略模式：
    - Provider 持有 Transport 实例（可替换）
    - Transport 负责特定 API 格式的转换
    - 不同 Provider 可共享相同 Transport
    
    例如：
    - OpenAI Provider 使用 ChatCompletionsTransport
    - Moonshot Provider 使用 ChatCompletionsTransport + MoonshotAdapter
    - Anthropic Provider 使用 AnthropicTransport
    """
    
    @property
    @abstractmethod
    def api_mode(self) -> str:
        """返回 API 模式标识（如 'chat_completions', 'anthropic_messages'）。"""
        ...
    
    @abstractmethod
    def convert_messages(self, messages, **kwargs) -> Any:
        """转换消息格式。
        
        输入：OpenAI 格式的消息列表
        输出：Provider 原生格式
        """
        ...
    
    @abstractmethod
    def convert_tools(self, tools) -> Any:
        """转换工具定义格式。
        
        输入：OpenAI 格式的工具定义
        输出：Provider 原生格式
        """
        ...
    
    @abstractmethod
    def build_kwargs(self, model, messages, tools, **params) -> Dict:
        """构建 API 调用参数。
        
        整合消息、工具、模型参数等，返回完整的 kwargs。
        """
        ...
    
    @abstractmethod
    def normalize_response(self, response, **kwargs) -> NormalizedResponse:
        """标准化响应。
        
        输入：Provider 原生响应对象
        输出：NormalizedResponse 统一格式
        """
        ...
    
    # 可选方法
    def validate_response(self, response) -> bool:
        """验证响应结构是否有效。"""
        return True
    
    def extract_cache_stats(self, response) -> Optional[Dict[str, int]]:
        """提取缓存命中统计。"""
        return None


class ChatCompletionsTransport(Transport):
    """OpenAI Chat Completions API 格式 Transport。
    
    大多数 Provider（OpenAI、Moonshot、DeepSeek、Qwen）使用此格式。
    中国大模型通过 Adapter 扩展特定参数。
    """
    
    @property
    def api_mode(self) -> str:
        return "chat_completions"
    
    def convert_messages(self, messages, **kwargs) -> List[Dict]:
        """Chat Completions 格式无需转换，直接返回。"""
        return self._prepare_messages(messages)
    
    def convert_tools(self, tools) -> List[Dict]:
        """转换工具定义为 OpenAI function 格式。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            }
            for t in tools
        ]
    
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict],
        tools: List[Dict] = None,
        **params,
    ) -> Dict[str, Any]:
        """构建 Chat Completions API 参数。"""
        kwargs = {
            "model": model,
            "messages": messages,
        }
        
        if tools:
            kwargs["tools"] = tools
        
        # 标准参数
        if "max_tokens" in params:
            kwargs["max_tokens"] = params["max_tokens"]
        if "temperature" in params:
            kwargs["temperature"] = params["temperature"]
        if "stream" in params:
            kwargs["stream"] = params["stream"]
        
        return kwargs
    
    def normalize_response(self, response, **kwargs) -> NormalizedResponse:
        """标准化 Chat Completions 响应。"""
        choice = response.choices[0]
        
        content = None
        tool_calls = None
        
        if choice.message.content:
            content = choice.message.content
        
        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in choice.message.tool_calls
            ]
        
        usage = None
        if response.usage:
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
        
        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            model=response.model,
        )
    
    def _prepare_messages(self, messages: List[Message]) -> List[Dict]:
        """准备消息列表，处理多模态内容。"""
        result = []
        for msg in messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
            else:
                # 多模态内容
                content_parts = []
                for block in msg.content:
                    if block.type == "text":
                        content_parts.append({"type": "text", "text": block.text})
                    elif block.type == "image":
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": block.url},
                        })
                result.append({"role": msg.role, "content": content_parts})
        return result


class TransportAdapter:
    """Transport 适配器，用于扩展特定 Provider 的参数。
    
    中国大模型通常有额外参数（如 reasoning_effort、thinking_config），
    通过 Adapter 扩展基础 Transport。
    """
    
    def __init__(self, base_transport: Transport):
        self._base = base_transport
    
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict],
        tools: List[Dict] = None,
        **params,
    ) -> Dict[str, Any]:
        """扩展 build_kwargs，添加 Provider 特定参数。"""
        kwargs = self._base.build_kwargs(model, messages, tools, **params)
        # 子类添加额外参数
        return kwargs


class MoonshotAdapter(TransportAdapter):
    """Moonshot (Kimi) API 适配器。
    
    支持 reasoning_effort 参数控制推理深度。
    """
    
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict],
        tools: List[Dict] = None,
        **params,
    ) -> Dict[str, Any]:
        kwargs = super().build_kwargs(model, messages, tools, **params)
        
        # Moonshot 特定参数
        if "reasoning_effort" in params:
            kwargs["reasoning_effort"] = params["reasoning_effort"]
        
        return kwargs
```

### 4.4 Tool

Tool 定义工具接口：

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        ...
    
    @property
    @abstractmethod
    def parameters(self) -> Dict:
        ...
    
    @abstractmethod
    def execute(self, tool_call_id, **kwargs) -> ToolResult:
        ...
    
    # 可选
    timeout: float = 300.0
    requires_approval: bool = False
    
    def validate_args(self, **kwargs) -> Optional[str]:
        return None
    
    def should_approve(self, args) -> bool:
        return self.requires_approval
```

### 4.5 ToolExecutor

ToolExecutor 负责并发执行工具，具有完整的生命周期管理：

```python
class ToolExecutor:
    """并发工具执行器，支持生命周期管理和中断传播。
    
    生命周期：
    - 创建时初始化 ThreadPoolExecutor
    - execute() 执行工具调用
    - shutdown() 或上下文管理器退出时清理线程池
    
    中断传播：
    - 通过 InterruptToken 检查中断状态
    - 中断时立即停止提交新任务
    - 已提交任务通过 ContextVars 获取中断状态
    """
    
    def __init__(
        self,
        config: ExecutorConfig = None,
        approval_callback: ApprovalCallback = None,
        interrupt_token: InterruptToken = None,
    ):
        self._config = config or ExecutorConfig()
        self._approval_callback = approval_callback
        self._interrupt_token = interrupt_token
        self._executor: Optional[ThreadPoolExecutor] = None
        self._worker_threads: Dict[int, threading.Thread] = {}
        self._lock = threading.Lock()
    
    def _ensure_executor(self) -> ThreadPoolExecutor:
        """懒加载初始化线程池。"""
        if self._executor is None:
            max_workers = min(self._config.max_workers, _MAX_TOOL_WORKERS)
            self._executor = ThreadPoolExecutor(max_workers=max_workers)
        return self._executor
    
    def execute(
        self,
        tool_calls: List[ToolCall],
        tools: Dict[str, Tool],
        context: ToolExecutionContext = None,
    ) -> List[ToolResult]:
        """并发执行工具调用。
        
        中断检查：每次提交前检查 interrupt_token
        ContextVars 传播：worker 线程继承当前上下文
        """
        executor = self._ensure_executor()
        futures = []
        ctx = contextvars.copy_context()  # 捕获当前上下文
        
        for tc in tool_calls:
            # 中断检查
            if self._interrupt_token and self._interrupt_token.is_interrupted:
                break
            
            tool = tools.get(tc.name)
            if not tool:
                continue
            
            # 审批检查
            if tool.requires_approval and self._approval_callback:
                decision = self._approval_callback.check(tc.name, tc.arguments)
                if not decision.approved:
                    continue
            
            # 提交到线程池，传播 ContextVars
            future = executor.submit(
                ctx.run,
                self._execute_tool,
                tool,
                tc,
                context,
            )
            futures.append((tc, future))
        
        # 收集结果
        results = []
        for tc, future in futures:
            try:
                result = future.result(timeout=tool.timeout)
                results.append(result)
            except TimeoutError:
                results.append(ToolResult(
                    tool_call_id=tc.id,
                    content="工具执行超时",
                    is_error=True,
                ))
        
        return results
    
    def _execute_tool(
        self,
        tool: Tool,
        tc: ToolCall,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """在 worker 线程中执行单个工具。"""
        # 注册 worker 线程（用于中断传播）
        thread_id = threading.current_thread().ident
        with self._lock:
            self._worker_threads[thread_id] = threading.current_thread()
        
        try:
            # 检查中断
            if context and context.is_interrupted():
                return ToolResult(
                    tool_call_id=tc.id,
                    content="执行被中断",
                    is_error=True,
                )
            
            return tool.execute(tool_call_id=tc.id, **json.loads(tc.arguments))
        finally:
            with self._lock:
                self._worker_threads.pop(thread_id, None)
    
    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        """关闭线程池，释放资源。"""
        if self._executor:
            self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            self._executor = None
    
    def __enter__(self) -> "ToolExecutor":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown(wait=True)


class ToolExecutionContext:
    """工具执行上下文，传递给工具以支持中断检查。"""
    
    def __init__(self, interrupt_token: InterruptToken = None):
        self._interrupt_token = interrupt_token
        self._agent_state: Dict[str, Any] = {}
    
    def is_interrupted(self) -> bool:
        """检查是否收到中断请求。"""
        return self._interrupt_token and self._interrupt_token.is_interrupted
    
    def get_agent_state(self, key: str) -> Optional[Any]:
        """获取 Agent 共享状态。"""
        return self._agent_state.get(key)


# 常量：最大并发工具数
_MAX_TOOL_WORKERS = 10
```

### 4.6 ApprovalCallback

ApprovalCallback 负责工具调用审批：

```python
@dataclass
class ApprovalDecision:
    approved: bool
    modified_args: Optional[Dict] = None
    constraints: Optional[Dict] = None
    reason: Optional[str] = None

class ApprovalCallback(ABC):
    @abstractmethod
    def check(self, tool_name, args) -> ApprovalDecision:
        ...
```

### 4.7 MemoryProvider

MemoryProvider 定义存储接口：

```python
class MemoryProvider(ABC):
    @abstractmethod
    def save(self, key: str, value: Any) -> None:
        ...
    
    @abstractmethod
    def load(self, key: str) -> Optional[Any]:
        ...
    
    @abstractmethod
    def delete(self, key: str) -> None:
        ...
    
    @abstractmethod
    def list_keys(self) -> List[str]:
        ...
```

### 4.8 Skill

Skill 定义技能接口：

```python
class Skill(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...
    
    @abstractmethod
    def activate(self, agent) -> None:
        ...
    
    @abstractmethod
    def deactivate(self, agent) -> None:
        ...
    
    def get_tools(self) -> Optional[List[Tool]]:
        return None
    
    def get_system_prompt_extension(self) -> Optional[str]:
        return None
```

### 4.9 EventEmitter

EventEmitter 负责事件分发：

```python
class EventEmitter:
    def on(
        self,
        event_type: str,
        callback: Callable,
        priority: int = 0,
        filter_func: Callable = None,
    ) -> None:
        ...
    
    def emit(self, event: Event) -> None:
        for listener in self._listeners.get(event.type, []):
            if listener.filter_func and not listener.filter_func(event):
                continue
            listener.callback(event)
```

### 4.10 InterruptToken

InterruptToken 负责中断控制，支持跨线程安全传播：

```python
@dataclass
class InterruptToken:
    """线程安全的中断令牌，支持协作式中断。
    
    中断传播机制：
    1. Agent 持有主 InterruptToken
    2. 子 Agent 继承父 Agent 的 token 或创建子 token
    3. ToolExecutor worker 线程通过 ContextVars 获取 token
    4. 中断时设置标志，所有检查点立即响应
    
    使用模式：
    - agent.run() 返回前创建 token
    - 用户中断时调用 token.interrupt()
    - Agent 循环、子 Agent、工具执行检查 is_interrupted
    """
    _interrupted: bool = field(default=False, init=False)
    _reason: Optional[str] = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _parent: Optional["InterruptToken"] = field(default=None, init=False)
    
    def interrupt(self, reason: str = None) -> None:
        """请求中断。线程安全。"""
        with self._lock:
            self._interrupted = True
            self._reason = reason
    
    @property
    def is_interrupted(self) -> bool:
        """检查是否已中断。线程安全。"""
        with self._lock:
            return self._interrupted
    
    @property
    def reason(self) -> Optional[str]:
        """获取中断原因。"""
        with self._lock:
            return self._reason
    
    def create_child(self) -> "InterruptToken":
        """创建子 token，共享中断状态。"""
        child = InterruptToken()
        child._parent = self
        return child
    
    def check(self) -> bool:
        """检查自身或父链是否中断。"""
        with self._lock:
            if self._interrupted:
                return True
        if self._parent:
            return self._parent.check()
        return False


class InterruptHandler:
    """Agent 的中断处理器，管理中断令牌和传播。"""
    
    def __init__(self):
        self._main_token: Optional[InterruptToken] = None
        self._child_tokens: List[InterruptToken] = []
        self._lock = threading.Lock()
    
    def create_token(self) -> InterruptToken:
        """创建新的中断令牌。"""
        token = InterruptToken()
        with self._lock:
            if self._main_token is None:
                self._main_token = token
        return token
    
    def register_child(self, token: InterruptToken) -> None:
        """注册子 Agent 的中断令牌。"""
        with self._lock:
            self._child_tokens.append(token)
    
    def propagate_interrupt(self, reason: str = None) -> None:
        """向所有子令牌传播中断。"""
        with self._lock:
            if self._main_token:
                self._main_token.interrupt(reason)
            for child in self._child_tokens:
                child.interrupt(reason)
            self._child_tokens.clear()
```

### 4.11 Settings

Settings 使用 Pydantic 进行配置验证：

```python
class Settings(BaseModel):
    model: str
    max_tokens: int = Field(default=4096, gt=0)
    temperature: float = Field(default=1.0, ge=0, le=2)
    
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    compression: CompressionSettings = Field(default_factory=CompressionSettings)
    delegation: DelegationSettings = Field(default_factory=DelegationSettings)
    
    @classmethod
    def from_file(cls, path: Path) -> "Settings":
        ...
    
    @classmethod
    def from_env(cls, prefix: str = "AGENTFORGE_") -> "Settings":
        ...
```

## 5. 委托系统

### 5.1 委托概述

委托系统允许 Agent 将任务委派给专门的子 Agent 执行，支持并行委托、深度限制和工具隔离。

### 5.2 委托配置

```python
@dataclass
class DelegationConfig:
    """委托配置。"""
    max_depth: int = 1  # 最大委托深度
    timeout: float = 300.0  # 单次委托超时
    heartbeat_interval: float = 30.0  # 心跳间隔
    
    # 隔离配置
    blocked_tools: FrozenSet[str] = frozenset([
        "delegate_task",
        "clarify",
        "memory",
        "send_message",
        "execute_code",
    ])
    inherit_tools: bool = True  # 是否继承父 Agent 工具
    inherit_memory: bool = False  # 是否继承父 Agent 记忆
    
    # 失败处理
    retry_count: int = 0  # 失败重试次数
    fallback_to_parent: bool = True  # 失败时回退到父 Agent


@dataclass
class IsolationConfig:
    """子 Agent 隔离配置。
    
    定义子 Agent 与父 Agent 之间的边界：
    - 工具边界：哪些工具不可用
    - 状态边界：是否共享记忆/上下文
    - 权限边界：审批回调如何处理
    """
    blocked_tools: FrozenSet[str] = frozenset()
    allow_shell: bool = False
    allow_network: bool = True
    allow_file_access: bool = True
    shared_memory: bool = False
    shared_context: bool = True
    auto_approve_safe_tools: bool = True
```

### 5.3 委托结果

```python
@dataclass
class DelegationResult:
    """委托执行结果。"""
    success: bool
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    error: Optional[Exception] = None
    duration: float = 0.0
    child_agent_id: str = ""
    
    # 失败处理信息
    retry_count: int = 0
    fallback_used: bool = False
    fallback_content: Optional[str] = None


class DelegationStrategy(Enum):
    """委托策略。"""
    SEQUENTIAL = "sequential"  # 顺序执行
    PARALLEL = "parallel"  # 并行执行
    FIRST_SUCCESS = "first_success"  # 首个成功即返回
    ALL_RESULTS = "all_results"  # 收集所有结果
```

### 5.4 DelegationManager

```python
class DelegationManager:
    """委托管理器，负责子 Agent 的创建、执行和监控。"""
    
    def __init__(
        self,
        config: DelegationConfig,
        parent_agent: "Agent",
        interrupt_handler: InterruptHandler,
    ):
        self._config = config
        self._parent = parent_agent
        self._interrupt_handler = interrupt_handler
        self._active_children: Dict[str, "Agent"] = {}
        self._depth = 0
    
    def delegate(
        self,
        task: str,
        agent_name: str = None,
        agent_config: Dict = None,
        strategy: DelegationStrategy = DelegationStrategy.SEQUENTIAL,
    ) -> DelegationResult:
        """委托任务给子 Agent。
        
        失败处理：
        1. 超时：返回 DelegationResult(success=False, error=TimeoutError)
        2. 中断：返回 DelegationResult(success=False, error=InterruptException)
        3. 子 Agent 异常：根据 retry_count 重试
        4. 重试耗尽：根据 fallback_to_parent 决定是否回退
        """
        # 深度检查
        if self._depth >= self._config.max_depth:
            return DelegationResult(
                success=False,
                content="",
                error=DelegationDepthExceededError(
                    f"委托深度 {self._depth} 超过最大值 {self._config.max_depth}"
                ),
            )
        
        # 创建子 Agent
        child = self._build_child_agent(agent_name, agent_config)
        child_id = str(uuid.uuid4())
        self._active_children[child_id] = child
        
        # 创建子中断令牌
        child_interrupt_token = self._interrupt_handler.create_token()
        self._interrupt_handler.register_child(child_interrupt_token)
        
        try:
            self._depth += 1
            result = self._run_child(
                child=child,
                task=task,
                interrupt_token=child_interrupt_token,
            )
            return result
        except Exception as e:
            # 失败处理
            return self._handle_delegation_failure(child, task, e)
        finally:
            self._depth -= 1
            self._active_children.pop(child_id, None)
    
    def _build_child_agent(
        self,
        name: str = None,
        config: Dict = None,
    ) -> "Agent":
        """构建子 Agent，应用隔离配置。"""
        # 继承父 Agent 配置
        child_settings = self._parent.settings.copy()
        
        # 应用隔离
        isolation = IsolationConfig(
            blocked_tools=self._config.blocked_tools,
            shared_memory=self._config.inherit_memory,
        )
        
        # 过滤被阻止的工具
        inherited_tools = []
        if self._config.inherit_tools:
            inherited_tools = [
                t for t in self._parent.tools
                if t.name not in isolation.blocked_tools
            ]
        
        # 创建子 Agent
        child = Agent(
            settings=child_settings,
            tools=inherited_tools,
            name=name or f"child_{self._depth}",
        )
        
        # 设置子 Agent 审批回调（自动批准安全工具）
        if isolation.auto_approve_safe_tools:
            child.set_approval_callback(
                ChildAgentApprovalCallback(
                    parent_callback=self._parent._approval_callback,
                    safe_tools=self._get_safe_tools(),
                )
            )
        
        return child
    
    def _run_child(
        self,
        child: "Agent",
        task: str,
        interrupt_token: InterruptToken,
    ) -> DelegationResult:
        """执行子 Agent，支持超时和心跳。"""
        start_time = time.time()
        last_heartbeat = start_time
        
        def heartbeat_check():
            """心跳检查，防止长时间无响应。"""
            nonlocal last_heartbeat
            while not interrupt_token.is_interrupted:
                time.sleep(self._config.heartbeat_interval)
                if time.time() - last_heartbeat > self._config.heartbeat_interval * 2:
                    interrupt_token.interrupt("心跳超时")
                    break
        
        # 启动心跳线程
        heartbeat_thread = threading.Thread(target=heartbeat_check, daemon=True)
        heartbeat_thread.start()
        
        try:
            response = child.run(task, interrupt_token=interrupt_token)
            last_heartbeat = time.time()
            
            return DelegationResult(
                success=True,
                content=response.content or "",
                tool_calls=response.tool_calls or [],
                duration=time.time() - start_time,
                child_agent_id=child.name,
            )
        finally:
            interrupt_token.interrupt()  # 停止心跳线程
    
    def _handle_delegation_failure(
        self,
        child: "Agent",
        task: str,
        error: Exception,
    ) -> DelegationResult:
        """处理委托失败。"""
        retry_count = 0
        
        # 重试逻辑
        while retry_count < self._config.retry_count:
            retry_count += 1
            try:
                response = child.run(task)
                return DelegationResult(
                    success=True,
                    content=response.content or "",
                    retry_count=retry_count,
                )
            except Exception:
                continue
        
        # 回退到父 Agent
        if self._config.fallback_to_parent:
            try:
                response = self._parent.run(task)
                return DelegationResult(
                    success=True,
                    content=response.content or "",
                    fallback_used=True,
                    fallback_content=response.content,
                )
            except Exception as fallback_error:
                error = fallback_error
        
        return DelegationResult(
            success=False,
            content="",
            error=error,
            retry_count=retry_count,
        )
    
    def cancel_all(self) -> None:
        """取消所有活动子 Agent。"""
        for child_id, child in self._active_children.items():
            child.get_interrupt_token().interrupt("父 Agent 取消")
        self._active_children.clear()


class ChildAgentApprovalCallback(ApprovalCallback):
    """子 Agent 审批回调，自动批准安全工具。"""
    
    def __init__(
        self,
        parent_callback: ApprovalCallback,
        safe_tools: FrozenSet[str],
    ):
        self._parent_callback = parent_callback
        self._safe_tools = safe_tools
    
    def check(self, tool_name: str, args: Dict) -> ApprovalDecision:
        """检查工具调用审批。"""
        if tool_name in self._safe_tools:
            return ApprovalDecision(approved=True, reason="安全工具自动批准")
        
        if self._parent_callback:
            return self._parent_callback.check(tool_name, args)
        
        return ApprovalDecision(approved=False, reason="子 Agent 无权限")
```

### 5.5 DelegateTool

```python
class DelegateTool(Tool):
    """委托工具，允许 Agent 将任务委派给子 Agent。"""
    
    name = "delegate_task"
    description = "将任务委托给专门的子 Agent 执行"
    
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "要委托的任务描述",
                },
                "agent_name": {
                    "type": "string",
                    "description": "目标子 Agent 名称（可选）",
                },
            },
            "required": ["task"],
        }
    
    def __init__(
        self,
        agents: List["Agent"] = None,
        config: DelegationConfig = None,
    ):
        self._agents = {a.name: a for a in (agents or [])}
        self._config = config or DelegationConfig()
    
    def execute(
        self,
        tool_call_id: str,
        task: str,
        agent_name: str = None,
        **kwargs,
    ) -> ToolResult:
        """执行委托。"""
        # 选择子 Agent
        if agent_name and agent_name in self._agents:
            child = self._agents[agent_name]
        else:
            # 自动选择或创建
            child = self._select_or_create_agent(task)
        
        # 执行委托
        result = self._delegation_manager.delegate(
            task=task,
            agent_name=agent_name,
        )
        
        if result.success:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=result.content,
            )
        else:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"委托失败: {result.error}",
                is_error=True,
            )
```

## 6. 扩展点

### 6.1 扩展点汇总

| 组件 | 必须实现 | 可选实现 |
|------|---------|---------|
| Provider | `_default_transport`, `_do_stream` | `_customize_kwargs`, `_handle_error` |
| Transport | `api_mode`, `convert_messages`, `convert_tools`, `build_kwargs`, `normalize_response` | `validate_response`, `extract_cache_stats` |
| Tool | `name`, `description`, `parameters`, `execute` | `timeout`, `requires_approval`, `validate_args` |
| MemoryProvider | `save`, `load`, `delete`, `list_keys` | `clear`, `exists` |
| Skill | `name`, `description`, `activate`, `deactivate` | `get_tools`, `get_system_prompt_extension` |
| ApprovalCallback | `check` | `prompt_user` |
| ContextCompressor | `estimate_tokens`, `compress` | `should_compress` |

### 6.2 注册机制

```python
# Provider 注册
from agentforge.ext import register_provider
register_provider("my_provider", MyProvider)

# Skill 注册
from agentforge.ext import register_skill
register_skill("my_skill", MySkill)

# Entry Points 发现（第三方插件）
# setup.py:
entry_points={
    "agentforge.providers": [
        "my_provider = my_package:MyProvider",
    ],
}
```

### 6.3 Provider 注册表

```python
class ProviderRegistry:
    """Provider 注册表，支持动态注册和发现。"""
    
    _providers: Dict[str, Type[Provider]] = {}
    _lock = threading.Lock()
    
    @classmethod
    def register(cls, name: str, provider_class: Type[Provider]) -> None:
        """注册 Provider。"""
        with cls._lock:
            if name in cls._providers:
                raise ConfigurationError(f"Provider '{name}' 已注册")
            cls._providers[name] = provider_class
    
    @classmethod
    def get(cls, name: str) -> Type[Provider]:
        """获取 Provider 类。"""
        with cls._lock:
            if name not in cls._providers:
                # 尝试通过 Entry Points 发现
                cls._discover_from_entry_points()
            
            if name not in cls._providers:
                raise ConfigurationError(f"Provider '{name}' 未找到")
            
            return cls._providers[name]
    
    @classmethod
    def list(cls) -> List[str]:
        """列出所有已注册 Provider。"""
        with cls._lock:
            cls._discover_from_entry_points()
            return list(cls._providers.keys())
    
    @classmethod
    def _discover_from_entry_points(cls) -> None:
        """从 Entry Points 发现第三方 Provider。"""
        import importlib.metadata
        
        try:
            eps = importlib.metadata.entry_points()
            if hasattr(eps, 'select'):
                provider_eps = eps.select(group="agentforge.providers")
            else:
                provider_eps = eps.get("agentforge.providers", [])
            
            for ep in provider_eps:
                if ep.name not in cls._providers:
                    provider_class = ep.load()
                    cls._providers[ep.name] = provider_class
        except Exception:
            pass  # Entry Points 发现失败不影响已注册的 Provider
    
    @classmethod
    def create(
        cls,
        name: str,
        api_key: str = None,
        base_url: str = None,
        **kwargs,
    ) -> Provider:
        """创建 Provider 实例。"""
        provider_class = cls.get(name)
        return provider_class(
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )


# 注册装饰器
def register_provider(name: str):
    """Provider 注册装饰器。"""
    def decorator(cls: Type[Provider]) -> Type[Provider]:
        ProviderRegistry.register(name, cls)
        return cls
    return decorator


# 使用示例
@register_provider("moonshot")
class MoonshotProvider(Provider):
    name = "moonshot"
    capabilities = ProviderCapabilities(
        supports_tools=True,
        supports_streaming=True,
        supports_reasoning=True,
    )
    
    def _default_transport(self) -> Transport:
        return MoonshotAdapter(ChatCompletionsTransport())
    
    def _do_stream(self, messages, tools, **kwargs) -> Iterator:
        # 使用 Moonshot SDK
        ...
```

### 6.4 Skill 注册表

```python
class SkillRegistry:
    """Skill 注册表，支持动态加载和发现。"""
    
    _skills: Dict[str, Type[Skill]] = {}
    _skill_dirs: List[Path] = []
    
    @classmethod
    def register(cls, name: str, skill_class: Type[Skill]) -> None:
        """注册 Skill。"""
        cls._skills[name] = skill_class
    
    @classmethod
    def get(cls, name: str) -> Skill:
        """获取 Skill 实例。"""
        if name not in cls._skills:
            cls._discover_from_dirs()
        
        if name not in cls._skills:
            raise ConfigurationError(f"Skill '{name}' 未找到")
        
        return cls._skills[name]()
    
    @classmethod
    def add_skill_dir(cls, path: Path) -> None:
        """添加 Skill 搜索目录。"""
        cls._skill_dirs.append(path)
    
    @classmethod
    def _discover_from_dirs(cls) -> None:
        """从目录发现 Skill。"""
        for skill_dir in cls._skill_dirs:
            if not skill_dir.exists():
                continue
            
            for skill_file in skill_dir.glob("**/*.py"):
                if skill_file.name.startswith("_"):
                    continue
                
                skill_name = skill_file.stem
                if skill_name in cls._skills:
                    continue
                
                # 动态加载
                try:
                    module = importlib.import_module(
                        f"{skill_dir.name}.{skill_name}"
                    )
                    if hasattr(module, "Skill"):
                        cls._skills[skill_name] = module.Skill
                except Exception:
                    pass
```

## 7. 类型系统

### 7.1 消息类型

```python
@dataclass
class TextContent:
    type: str = "text"
    text: str

@dataclass
class ImageContent:
    type: str = "image"
    url: str
    media_type: Optional[str] = None

@dataclass
class ToolUseContent:
    type: str = "tool_use"
    id: str
    name: str
    input: dict

@dataclass
class ToolResultContent:
    type: str = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False

ContentBlock = Union[TextContent, ImageContent, ToolUseContent, ToolResultContent]

@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: Union[str, List[ContentBlock]]
    name: Optional[str] = None
```

### 7.2 响应类型

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string

@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

@dataclass
class NormalizedResponse:
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"
    reasoning: Optional[str] = None
    usage: Optional[Usage] = None
    provider_data: Optional[dict] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: Optional[str] = None
    created: int = field(default_factory=lambda: int(time.time()))
```

### 7.3 错误类型

```python
AgentForgeError (基类)
├── ConfigurationError
├── ProviderError
│   ├── ProviderConnectionError
│   ├── ProviderRateLimitError
│   └── ProviderResponseError
├── ToolError
│   ├── ToolExecutionError
│   ├── ToolApprovalDeniedError
│   └── ToolTimeoutError
├── DelegationError
│   └── DelegationDepthExceededError
├── ContextError
│   └── ContextCompressionError
└── InterruptException
```

## 8. 事件系统

### 8.1 事件类型

```python
class EventType:
    # Agent 生命周期
    AGENT_START = "agent.start"
    AGENT_END = "agent.end"
    AGENT_INTERRUPT = "agent.interrupt"
    
    # 工具执行
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    TOOL_ERROR = "tool.error"
    TOOL_APPROVAL_REQUIRED = "tool.approval_required"
    
    # Provider 调用
    PROVIDER_REQUEST = "provider.request"
    PROVIDER_RESPONSE = "provider.response"
    PROVIDER_ERROR = "provider.error"
    
    # 上下文压缩
    COMPRESSION_START = "compression.start"
    COMPRESSION_END = "compression.end"
    
    # 委托
    DELEGATION_START = "delegation.start"
    DELEGATION_END = "delegation.end"
```

### 8.2 事件结构

```python
@dataclass
class Event:
    id: str                    # 事件唯一 ID
    type: str                  # 事件类型
    timestamp: float           # Unix 时间戳
    trace_id: str              # 追踪 ID
    span_id: str               # 当前 span ID
    parent_span_id: str = None # 父 span ID
    data: dict = None          # 事件数据
```

## 9. 配置系统

### 9.1 配置结构

```python
class Settings(BaseModel):
    model: str
    max_tokens: int = 4096
    temperature: float = 1.0
    
    provider: ProviderSettings
    compression: CompressionSettings
    delegation: DelegationSettings
    executor: ExecutorSettings
    
    system_prompt: Optional[str] = None
    debug: bool = False

class ProviderSettings(BaseModel):
    api_key: Optional[SecretStr] = None
    base_url: Optional[str] = None
    timeout: float = 300.0
    max_retries: int = 3

class CompressionSettings(BaseModel):
    enabled: bool = True
    max_tokens: int = 128000
    head_protect_ratio: float = 0.1
    tail_protect_ratio: float = 0.3
    strategy: str = "summarize"

class DelegationSettings(BaseModel):
    max_depth: int = 3
    inherit_tools: bool = True
    inherit_memory: bool = False
    blocked_tools: List[str] = ["delegate"]
    timeout: float = 300.0

class ExecutorSettings(BaseModel):
    max_workers: int = 10
    queue_size: int = 100
    default_timeout: float = 300.0
```

### 9.2 配置加载

```python
# 从文件
settings = Settings.from_file("config.yaml")

# 从环境变量
settings = Settings.from_env()

# 混合配置
settings = Settings(
    model="gpt-4",
    provider=ProviderSettings(
        api_key="${OPENAI_API_KEY}",  # 支持环境变量引用
    ),
)
```

## 10. 中国大模型支持

### 10.1 内置 Provider

| Provider | 模型 | 特性 |
|---------|------|------|
| MoonshotProvider | Kimi | reasoning_effort, 长上下文 |
| QwenProvider | 通义千问 | thinking_config, 多模态 |
| DeepSeekProvider | DeepSeek | reasoning, 代码优化 |

### 10.2 Transport 适配器

```python
# Moonshot 适配器
class MoonshotTransport(ChatCompletionsTransport):
    def build_kwargs(self, model, messages, tools, **params):
        kwargs = super().build_kwargs(model, messages, tools, **params)
        if params.get("reasoning_effort"):
            kwargs["reasoning_effort"] = params["reasoning_effort"]
        return kwargs

# DeepSeek 适配器
class DeepSeekTransport(ChatCompletionsTransport):
    def build_kwargs(self, model, messages, tools, **params):
        kwargs = super().build_kwargs(model, messages, tools, **params)
        # DeepSeek 特定处理
        return kwargs
```

## 11. 上下文压缩

### 11.1 Token 估算

```python
class TokenEstimator:
    """Token 估算器，用于上下文压缩决策。"""
    
    # 估算常量（基于 hermes-agent 实现）
    CHARS_PER_TOKEN = 4  # 平均每 Token 约 4 字符
    IMAGE_TOKEN_ESTIMATE = 1600  # 单张图片约 1600 Token
    
    def estimate_tokens(self, content: Union[str, List[ContentBlock]]) -> int:
        """估算内容的 Token 数量。
        
        支持多模态内容：
        - 文本：字符数 / CHARS_PER_TOKEN
        - 图片：固定 IMAGE_TOKEN_ESTIMATE
        - 工具调用/结果：JSON 长度估算
        """
        if isinstance(content, str):
            return len(content) // self.CHARS_PER_TOKEN
        
        total = 0
        for block in content:
            if block.type == "text":
                total += len(block.text) // self.CHARS_PER_TOKEN
            elif block.type == "image":
                total += self.IMAGE_TOKEN_ESTIMATE
            elif block.type == "tool_use":
                total += self._estimate_tool_use(block)
            elif block.type == "tool_result":
                total += self._estimate_tool_result(block)
        
        return total
    
    def _estimate_tool_use(self, block: ToolUseContent) -> int:
        """估算工具调用 Token。"""
        # id + name + input JSON
        return (
            len(block.id) // self.CHARS_PER_TOKEN +
            len(block.name) // self.CHARS_PER_TOKEN +
            len(json.dumps(block.input)) // self.CHARS_PER_TOKEN
        )
    
    def _estimate_tool_result(self, block: ToolResultContent) -> int:
        """估算工具结果 Token。"""
        return len(block.content) // self.CHARS_PER_TOKEN
```

### 11.2 ContextCompressor

```python
class ContextCompressor:
    """上下文压缩器，在 Token 限制接近时压缩历史消息。
    
    压缩策略：
    1. 保护头部消息（系统提示、初始对话）
    2. 保护尾部消息（最近对话）
    3. 压缩中间部分（摘要或删除）
    4. 优先删除工具输出（通常较长）
    """
    
    def __init__(
        self,
        estimator: TokenEstimator,
        config: CompressionSettings,
        llm_provider: Provider = None,  # 用于生成摘要
    ):
        self._estimator = estimator
        self._config = config
        self._llm = llm_provider
    
    def should_compress(self, messages: List[Message]) -> bool:
        """判断是否需要压缩。"""
        total_tokens = sum(
            self._estimator.estimate_tokens(m.content) for m in messages
        )
        return total_tokens > self._config.max_tokens
    
    def compress(
        self,
        messages: List[Message],
        preserve_system: bool = True,
    ) -> List[Message]:
        """压缩消息列表。
        
        步骤：
        1. 计算总 Token 数
        2. 确定保护区域（头部 + 尾部）
        3. 计算可压缩区域预算
        4. 优先删除工具输出
        5. 对剩余内容生成摘要（如果启用）
        """
        if not self.should_compress(messages):
            return messages
        
        # 计算保护区域
        head_count = max(1, int(len(messages) * self._config.head_protect_ratio))
        tail_count = max(1, int(len(messages) * self._config.tail_protect_ratio))
        
        # 分区
        head = messages[:head_count]
        middle = messages[head_count:-tail_count] if tail_count > 0 else messages[head_count:]
        tail = messages[-tail_count:] if tail_count > 0 else []
        
        # 计算预算
        head_tokens = sum(self._estimator.estimate_tokens(m.content) for m in head)
        tail_tokens = sum(self._estimator.estimate_tokens(m.content) for m in tail)
        budget = self._config.max_tokens - head_tokens - tail_tokens
        
        # 压缩中间部分
        compressed_middle = self._compress_middle(middle, budget)
        
        return head + compressed_middle + tail
    
    def _compress_middle(
        self,
        messages: List[Message],
        budget: int,
    ) -> List[Message]:
        """压缩中间消息。"""
        if self._config.strategy == "prune":
            # 简单删除策略
            return self._prune_messages(messages, budget)
        elif self._config.strategy == "summarize":
            # 摘要策略
            return self._summarize_messages(messages, budget)
        else:
            return messages
    
    def _prune_messages(
        self,
        messages: List[Message],
        budget: int,
    ) -> List[Message]:
        """删除消息以满足预算。
        
        优先删除：
        1. 工具结果（通常最长）
        2. 旧的 assistant 消息
        """
        # 先尝试删除工具结果
        pruned = self._prune_tool_results(messages, budget)
        if self._estimate_total(pruned) <= budget:
            return pruned
        
        # 继续删除旧消息
        while messages and self._estimate_total(messages) > budget:
            # 删除第一个非系统消息
            for i, m in enumerate(messages):
                if m.role != "system":
                    messages = messages[:i] + messages[i+1:]
                    break
        
        return messages
    
    def _prune_tool_results(
        self,
        messages: List[Message],
        budget: int,
    ) -> List[Message]:
        """删除工具结果。"""
        result = []
        for m in messages:
            if isinstance(m.content, list):
                # 过滤掉工具结果
                filtered = [
                    b for b in m.content
                    if b.type != "tool_result"
                ]
                if filtered:
                    result.append(Message(role=m.role, content=filtered))
            else:
                result.append(m)
        return result
    
    def _summarize_messages(
        self,
        messages: List[Message],
        budget: int,
    ) -> List[Message]:
        """使用 LLM 生成摘要。"""
        if not self._llm:
            return self._prune_messages(messages, budget)
        
        # 构建摘要请求
        summary_prompt = "请简要总结以下对话内容：\n\n"
        for m in messages:
            summary_prompt += f"{m.role}: {self._content_to_text(m.content)}\n"
        
        # 调用 LLM
        response = self._llm.complete([
            Message(role="user", content=summary_prompt)
        ])
        
        # 返回摘要消息
        return [
            Message(
                role="assistant",
                content="[历史对话摘要]\n" + response.content,
            )
        ]
    
    def _content_to_text(self, content: Union[str, List[ContentBlock]]) -> str:
        """将内容转换为文本。"""
        if isinstance(content, str):
            return content
        return " ".join(
            b.text if b.type == "text" else f"[{b.type}]"
            for b in content
        )
    
    def _estimate_total(self, messages: List[Message]) -> int:
        """计算消息列表总 Token。"""
        return sum(self._estimator.estimate_tokens(m.content) for m in messages)
```

## 12. 代码来源映射

| agentforge 模块 | hermes-agent 来源 | 复用率 |
|----------------|------------------|-------|
| `providers/transports/` | `agent/transports/` | 80% |
| `tools/` | `tools/` | 70% |
| `providers/base.py` | `agent/provider.py` | 50% |
| `agent.py` | `agent/conversation_loop.py` | 40% |
| `context/` | `agent/context_compressor.py` | 60% |
| `delegation/` | `tools/delegate_tool.py` | 50% |
| `interrupt/` | `agent/conversation_loop.py` + `agent/tool_executor.py` | 70% |
| **总体** | | **60%** |

## 13. 错误处理策略

### 13.1 错误分类与处理

```python
class ErrorHandler:
    """统一错误处理器。"""
    
    def handle(self, error: Exception, context: Dict = None) -> ErrorResult:
        """处理错误并返回统一结果。"""
        if isinstance(error, ProviderRateLimitError):
            return self._handle_rate_limit(error, context)
        elif isinstance(error, ProviderConnectionError):
            return self._handle_connection_error(error, context)
        elif isinstance(error, ToolTimeoutError):
            return self._handle_tool_timeout(error, context)
        elif isinstance(error, DelegationDepthExceededError):
            return self._handle_depth_exceeded(error, context)
        elif isinstance(error, InterruptException):
            return self._handle_interrupt(error, context)
        else:
            return self._handle_unknown(error, context)
    
    def _handle_rate_limit(
        self,
        error: ProviderRateLimitError,
        context: Dict,
    ) -> ErrorResult:
        """处理速率限制错误。"""
        retry_after = error.retry_after or 60
        return ErrorResult(
            recoverable=True,
            action="retry",
            delay=retry_after,
            message=f"API 速率限制，{retry_after} 秒后重试",
        )
    
    def _handle_connection_error(
        self,
        error: ProviderConnectionError,
        context: Dict,
    ) -> ErrorResult:
        """处理连接错误。"""
        return ErrorResult(
            recoverable=True,
            action="retry",
            delay=5,
            max_retries=3,
            message="网络连接失败，正在重试",
        )
    
    def _handle_tool_timeout(
        self,
        error: ToolTimeoutError,
        context: Dict,
    ) -> ErrorResult:
        """处理工具超时。"""
        return ErrorResult(
            recoverable=False,
            action="skip",
            message=f"工具 {error.tool_name} 执行超时",
        )
    
    def _handle_depth_exceeded(
        self,
        error: DelegationDepthExceededError,
        context: Dict,
    ) -> ErrorResult:
        """处理委托深度超限。"""
        return ErrorResult(
            recoverable=False,
            action="fallback",
            message="委托深度超限，回退到父 Agent",
        )
    
    def _handle_interrupt(
        self,
        error: InterruptException,
        context: Dict,
    ) -> ErrorResult:
        """处理中断。"""
        return ErrorResult(
            recoverable=False,
            action="abort",
            message=f"执行被中断: {error.reason}",
        )


@dataclass
class ErrorResult:
    """错误处理结果。"""
    recoverable: bool
    action: str  # "retry" | "skip" | "fallback" | "abort"
    message: str
    delay: float = 0
    max_retries: int = 0
```

### 13.2 重试策略

```python
class RetryPolicy:
    """重试策略配置。"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """计算第 N 次重试的延迟。"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay
```

## 14. 日志规范

### 14.1 日志级别

| 级别 | 用途 |
|------|------|
| DEBUG | 详细调试信息（消息内容、API 请求/响应） |
| INFO | 正常操作（Agent 启动、工具执行、委托） |
| WARNING | 可恢复问题（重试、降级） |
| ERROR | 操作失败（API 错误、工具异常） |
| CRITICAL | 系统级故障（配置错误、资源耗尽） |

### 14.2 日志格式

```python
LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s - "
    "%(message)s trace_id=%(trace_id)s span_id=%(span_id)s"
)

# 敏感信息脱敏
SENSITIVE_FIELDS = frozenset([
    "api_key", "token", "password", "secret",
    "authorization", "credential",
])

def redact_sensitive(data: Dict) -> Dict:
    """脱敏敏感字段。"""
    result = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            result[key] = "***REDACTED***"
        elif isinstance(value, dict):
            result[key] = redact_sensitive(value)
        else:
            result[key] = value
    return result
```

### 14.3 结构化日志

```python
import structlog

def configure_logging(debug: bool = False) -> None:
    """配置结构化日志。"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
    )
```

## 15. 版本兼容性

### 15.1 API 稳定性保证

- **稳定 API**：`agentforge` 包下的公共 API 保证向后兼容
- **实验性 API**：标记为 `@experimental` 的 API 可能变更
- **内部 API**：`agentforge._internal` 不保证兼容性

### 15.2 版本策略

```python
# 版本号格式：MAJOR.MINOR.PATCH
# - MAJOR：不兼容的 API 变更
# - MINOR：向后兼容的功能新增
# - PATCH：向后兼容的问题修复

__version__ = "0.1.0"

# 废弃警告
def deprecated(since: str, removal: str, alternative: str = None):
    """标记废弃的 API。"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} 自 {since} 起废弃，"
                f"将在 {removal} 移除"
                + (f"，请使用 {alternative}" if alternative else ""),
                DeprecationWarning,
                stacklevel=2,
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### 15.3 迁移指南

每个 MAJOR 版本变更提供迁移指南，包括：
- 废弃 API 列表
- 替代方案
- 代码示例

## 16. 安全考虑

### 16.1 敏感信息处理

```python
class SecretManager:
    """敏感信息管理器。"""
    
    def __init__(self):
        self._secrets: Dict[str, SecretStr] = {}
    
    def set(self, key: str, value: str) -> None:
        """存储敏感信息。"""
        self._secrets[key] = SecretStr(value)
    
    def get(self, key: str) -> Optional[str]:
        """获取敏感信息。"""
        secret = self._secrets.get(key)
        return secret.get_secret_value() if secret else None
    
    def redact(self, text: str) -> str:
        """从文本中移除敏感信息。"""
        for key, secret in self._secrets.items():
            value = secret.get_secret_value()
            if value and value in text:
                text = text.replace(value, f"[{key}_REDACTED]")
        return text
```

### 16.2 工具执行安全

```python
class ToolSecurityPolicy:
    """工具执行安全策略。"""
    
    def __init__(
        self,
        allowed_commands: FrozenSet[str] = None,
        blocked_commands: FrozenSet[str] = None,
        allow_network: bool = True,
        allow_file_write: bool = True,
        sandbox_dir: Path = None,
    ):
        self.allowed_commands = allowed_commands
        self.blocked_commands = blocked_commands or frozenset([
            "rm -rf", "sudo", "chmod 777",
        ])
        self.allow_network = allow_network
        self.allow_file_write = allow_file_write
        self.sandbox_dir = sandbox_dir
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """验证命令是否允许执行。"""
        # 检查阻止列表
        for blocked in self.blocked_commands:
            if blocked in command:
                return False, f"命令包含阻止的模式: {blocked}"
        
        # 检查允许列表（如果配置）
        if self.allowed_commands:
            base_cmd = command.split()[0] if command.split() else ""
            if base_cmd not in self.allowed_commands:
                return False, f"命令不在允许列表中: {base_cmd}"
        
        return True, ""
    
    def validate_path(self, path: Path, for_write: bool = False) -> Tuple[bool, str]:
        """验证路径访问权限。"""
        if for_write and not self.allow_file_write:
            return False, "文件写入被禁止"
        
        if self.sandbox_dir:
            try:
                path.resolve().relative_to(self.sandbox_dir.resolve())
            except ValueError:
                return False, "路径不在沙箱目录内"
        
        return True, ""
```

### 16.3 审批系统安全

```python
class SecureApprovalCallback(ApprovalCallback):
    """安全审批回调，支持命令白名单和风险评级。"""
    
    # 风险评级
    RISK_LOW = "low"  # 自动批准
    RISK_MEDIUM = "medium"  # 需要确认
    RISK_HIGH = "high"  # 需要明确批准
    
    TOOL_RISK_LEVELS = {
        "read_file": RISK_LOW,
        "write_file": RISK_MEDIUM,
        "execute_shell": RISK_HIGH,
        "delegate_task": RISK_MEDIUM,
    }
    
    def __init__(
        self,
        auto_approve_low_risk: bool = True,
        require_explicit_high_risk: bool = True,
    ):
        self.auto_approve_low_risk = auto_approve_low_risk
        self.require_explicit_high_risk = require_explicit_high_risk
    
    def check(self, tool_name: str, args: Dict) -> ApprovalDecision:
        """检查工具调用审批。"""
        risk = self.TOOL_RISK_LEVELS.get(tool_name, self.RISK_MEDIUM)
        
        if risk == self.RISK_LOW and self.auto_approve_low_risk:
            return ApprovalDecision(
                approved=True,
                reason="低风险工具自动批准",
            )
        
        if risk == self.RISK_HIGH and self.require_explicit_high_risk:
            return ApprovalDecision(
                approved=False,
                reason="高风险工具需要明确批准",
            )
        
        # 中等风险或需要用户确认
        return ApprovalDecision(
            approved=False,
            reason="需要用户确认",
        )
```

## 17. 实现计划

### 17.1 阶段划分

| 阶段 | 内容 | 优先级 | 依赖 | 说明 |
|------|------|-------|------|------|
| **P0** | `types/`, `config/` | 核心 | 无 | 类型系统是所有组件基础，配置系统是初始化依赖 |
| **P1** | `providers/transports/`, `providers/base.py`, `providers/registry.py` | Provider | P0 | Transport 可直接复用 hermes-agent 80% |
| **P2** | `interrupt/`, `events/` | 基础设施 | P0 | 中断和事件是 Agent 运行的底层设施 |
| **P3** | `tools/base.py`, `tools/executor.py`, `tools/approval.py` | 工具 | P0, P2 | 工具系统依赖中断机制 |
| **P4** | `agent.py`, `context/` | 引擎 | P0-P3 | Agent 门面整合所有组件 |
| **P5** | `delegation/` | 委托 | P0-P4 | 委托依赖 Agent 和工具系统 |
| **P6** | `memory/`, `skills/` | 扩展 | P0-P4 | 存储和技能扩展组件 |
| **P7** | `providers/builtins/`, `tools/builtins/` | 内置实现 | P1, P3 | 内置 Provider 和工具 |
| **P8** | `utils/` | 工具函数 | 无 | 独立工具函数，可随时实现 |

### 17.2 阶段详细说明

#### P0: 类型系统与配置（预计 2 天）

```
agentforge/
├── types/
│   ├── __init__.py
│   ├── messages.py      # Message, ContentBlock, TextContent, ImageContent...
│   ├── responses.py     # NormalizedResponse, ToolCall, Usage
│   ├── tools.py         # ToolSpec, ToolResult
│   └── errors.py        # AgentForgeError 及子类
└── config/
    ├── __init__.py
    ├── settings.py      # Settings, ProviderSettings, CompressionSettings...
    └── secrets.py      # SecretManager
```

**交付物**：
- 完整的类型定义，支持类型检查
- Pydantic 配置验证
- 单元测试覆盖

#### P1: Provider 与 Transport（预计 3 天）

```
agentforge/
├── providers/
│   ├── __init__.py
│   ├── base.py          # Provider ABC, ProviderCapabilities
│   ├── registry.py      # ProviderRegistry
│   └── transports/
│       ├── __init__.py
│       ├── base.py      # Transport ABC
│       ├── types.py     # 内部类型（如有）
│       ├── chat_completions.py  # ChatCompletionsTransport
│       └── adapters/
│           ├── __init__.py
│           ├── moonshot.py
│           ├── qwen.py
│           └── deepseek.py
```

**交付物**：
- Transport 抽象基类
- ChatCompletionsTransport 完整实现
- 中国大模型适配器
- Provider 注册机制
- 单元测试 + Mock API 测试

#### P2: 中断与事件（预计 2 天）

```
agentforge/
├── interrupt/
│   ├── __init__.py
│   └── cooperative.py   # InterruptToken, InterruptHandler
└── events/
    ├── __init__.py
    ├── types.py         # EventType, Event
    └── emitter.py       # EventEmitter, EventDispatcher
```

**交付物**：
- 线程安全的中断令牌
- 父子链式中断传播
- 事件分发系统
- 单元测试

#### P3: 工具系统（预计 3 天）

```
agentforge/
└── tools/
    ├── __init__.py
    ├── base.py          # Tool ABC, FunctionTool
    ├── executor.py      # ToolExecutor, ToolExecutionContext
    ├── approval.py      # ApprovalCallback, ApprovalDecision
    └── toolsets.py      # Toolset 定义
```

**交付物**：
- Tool 抽象基类
- 函数装饰器 `@tool`
- 并发执行器（ThreadPoolExecutor + ContextVars）
- 审批系统
- 单元测试

#### P4: Agent 核心与上下文压缩（预计 4 天）

```
agentforge/
├── agent.py             # Agent 门面类
├── managers/
│   ├── __init__.py
│   ├── message.py       # MessageManager
│   └── tool_orchestrator.py  # ToolOrchestrator
└── context/
    ├── __init__.py
    ├── compressor.py    # ContextCompressor
    ├── estimator.py     # TokenEstimator
    └── protection.py    # 保护区域计算
```

**交付物**：
- Agent 门面类
- MessageManager 消息管理
- ToolOrchestrator 工具编排
- ContextCompressor 压缩策略
- 集成测试

#### P5: 委托系统（预计 3 天）

```
agentforge/
└── delegation/
    ├── __init__.py
    ├── config.py        # DelegationConfig, IsolationConfig
    ├── manager.py       # DelegationManager
    ├── result.py        # DelegationResult, DelegationStrategy
    └── approval.py      # ChildAgentApprovalCallback
```

**交付物**：
- 委托配置与隔离边界
- DelegationManager 完整实现
- 失败处理与重试
- 单元测试 + 集成测试

#### P6: 存储与技能（预计 2 天）

```
agentforge/
├── memory/
│   ├── __init__.py
│   ├── base.py          # MemoryProvider ABC
│   └── builtins/
│       ├── __init__.py
│       ├── in_memory.py
│       └── file_based.py
└── skills/
    ├── __init__.py
    ├── base.py          # Skill ABC
    ├── loader.py        # Skill 加载器
    └── registry.py      # SkillRegistry
```

**交付物**：
- MemoryProvider 抽象与内置实现
- Skill 抽象与注册机制
- 单元测试

#### P7: 内置实现（预计 3 天）

```
agentforge/
├── providers/
│   └── builtins/
│       ├── __init__.py
│       ├── openai.py
│       ├── anthropic.py
│       └── chinese/
│           ├── __init__.py
│           ├── moonshot.py
│           ├── qwen.py
│           └── deepseek.py
└── tools/
    └── builtins/
        ├── __init__.py
        ├── delegate.py
        ├── shell.py
        └── ...
```

**交付物**：
- OpenAI/Anthropic Provider
- 中国大模型 Provider
- 内置工具（delegate, shell 等）
- 集成测试

#### P8: 工具函数（预计 1 天）

```
agentforge/
└── utils/
    ├── __init__.py
    ├── platform.py      # 跨平台兼容
    └── logging.py       # 日志配置
```

**交付物**：
- 平台检测与兼容
- 日志配置
- 文档完善

### 17.3 测试策略

- **单元测试**：每个组件独立测试，覆盖率 > 80%
- **集成测试**：Agent 完整流程测试
- **Provider 测试**：Mock API 响应，验证协议转换
- **跨平台测试**：Windows、Linux、macOS CI

### 17.4 里程碑

| 里程碑 | 阶段 | 交付物 |
|--------|------|--------|
| M1 | P0-P1 | 可用的 Provider + Transport，支持 API 调用 |
| M2 | P0-P3 | 完整的工具执行能力 |
| M3 | P0-P4 | 可运行的 Agent，支持对话循环 |
| M4 | P0-P5 | 支持子 Agent 委托 |
| M5 | P0-P6 | 完整框架，支持存储和技能 |
| M6 | P0-P8 | 发布就绪，包含内置实现和文档 |

## 18. 附录

### 18.1 依赖

```
pydantic>=2.0
typing-extensions>=4.0
```

### 18.2 可选依赖

```
[anthropic]
anthropic>=0.20.0

[openai]
openai>=1.0.0

[chinese]
# 中国大模型 SDK
```

### 18.3 Python 版本

- 最低：Python 3.9
- 推荐：Python 3.11+
