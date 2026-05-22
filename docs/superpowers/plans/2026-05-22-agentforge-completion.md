# AgentForge 完善实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善 AgentForge 框架，补充缺失功能，确保所有组件完整可用

**Architecture:** 基于 hermes-agent 成熟架构，补充工具集系统、会话管理、模型元数据、活动追踪等功能

**Tech Stack:** Python 3.9+, Pydantic, dataclasses, threading

---

## 当前实现状态分析

### 已完成模块

| 模块 | 完成度 | 说明 |
|------|--------|------|
| `types/` | 95% | 完整的消息、响应、工具类型 |
| `config/` | 90% | Settings、SecretManager |
| `providers/transports/` | 85% | ChatCompletions、Anthropic、Bedrock |
| `providers/builtins/` | 80% | OpenAI、Anthropic、Moonshot、Qwen、DeepSeek |
| `interrupt/` | 95% | InterruptToken、InterruptHandler |
| `events/` | 90% | EventType（部分）、EventDispatcher |
| `tools/` | 85% | Tool、ToolExecutor、Approval、Guardrails |
| `delegation/` | 90% | DelegationManager、DelegationConfig |
| `memory/` | 85% | MemoryProvider、MemoryManager |
| `skills/` | 80% | Skill、SkillRegistry、SkillLoader |
| `core/` | 80% | IterationBudget、CredentialPool、FallbackChain、ExecutionEngine |
| `agent.py` | 90% | Agent 门面类 |
| `utils/` | 70% | platform、logging、model_metadata、schema_sanitizer |

### 缺失功能

| 功能 | 优先级 | 参考 |
|------|--------|------|
| 工具集系统 (ToolsetDefinition, ToolsetRegistry) | P0 | hermes-agent/toolsets.py |
| 会话管理 (SessionProvider, SessionInfo) | P1 | hermes-agent/hermes_state.py |
| Agent 活动追踪 (_last_activity_ts, get_activity_summary) | P1 | hermes-agent/run_agent.py |
| 速率限制状态追踪 (_rate_limit_state) | P2 | hermes-agent/run_agent.py |
| EventType 扩展 (AGENT_THINKING 等) | P2 | hermes-agent/run_agent.py |
| 模型能力查询 (ModelCapabilities) | P2 | hermes-agent/agent/model_metadata.py |
| OAuth 凭证刷新 | P3 | hermes-agent/agent/credential_pool.py |

---

## 文件结构

```
agentforge/
├── tools/
│   └── toolsets.py          # 新增：工具集定义
├── session/
│   ├── __init__.py          # 新增：会话模块入口
│   ├── base.py              # 新增：SessionProvider ABC
│   ├── info.py              # 新增：SessionInfo, MessageRecord
│   └── builtins/
│       ├── __init__.py
│       └── in_memory.py     # 新增：InMemorySessionProvider
├── core/
│   └── model_metadata.py    # 新增：ModelCapabilities
├── events/
│   └── types.py             # 修改：扩展 EventType
├── agent.py                 # 修改：添加活动追踪
└── utils/
    └── model_metadata.py    # 修改：完善模型元数据
```

---

## Task 1: 工具集系统 - ToolsetDefinition

**Files:**
- Create: `agentforge/tools/toolsets.py`
- Test: `tests/test_toolsets.py`

- [ ] **Step 1: Write the failing test for ToolsetDefinition**

```python
# tests/test_toolsets.py
"""工具集系统测试。"""

import pytest
import os
from unittest.mock import patch

from agentforge.tools.toolsets import (
    ToolsetDefinition,
    ToolsetRegistry,
    register_toolset,
    get_toolset,
    resolve_toolset,
)


class TestToolsetDefinition:
    """ToolsetDefinition 测试。"""

    def test_create_definition(self):
        """测试创建工具集定义。"""
        toolset = ToolsetDefinition(
            description="网络搜索工具",
            tools=["web_search", "web_extract"],
        )

        assert toolset.description == "网络搜索工具"
        assert "web_search" in toolset.tools
        assert toolset.is_available() is True

    def test_check_fn(self):
        """测试条件检查函数。"""
        toolset = ToolsetDefinition(
            description="需要网关的工具",
            tools=["send_message"],
            check_fn=lambda: False,
        )

        assert toolset.is_available() is False

    def test_requires_env(self):
        """测试环境变量要求。"""
        toolset = ToolsetDefinition(
            description="需要 API Key",
            tools=["api_call"],
            requires_env=["MY_API_KEY"],
        )

        # 没有设置环境变量
        assert toolset.is_available() is False

        # 设置环境变量后
        with patch.dict(os.environ, {"MY_API_KEY": "test"}):
            assert toolset.is_available() is True

    def test_includes(self):
        """测试包含其他工具集。"""
        toolset = ToolsetDefinition(
            description="完整工具集",
            tools=["extra_tool"],
            includes=["web"],
        )

        assert "web" in toolset.includes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_toolsets.py -v`
Expected: FAIL with "No module named 'agentforge.tools.toolsets'"

- [ ] **Step 3: Write ToolsetDefinition implementation**

```python
# agentforge/tools/toolsets.py
"""工具集系统。

支持工具分组和条件启用，参考 hermes-agent/toolsets.py 实现。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolsetDefinition:
    """工具集定义。
    
    支持工具分组和条件启用。
    
    Attributes:
        description: 工具集描述
        tools: 包含的工具名称列表
        includes: 包含的其他工具集名称
        check_fn: 运行时检查函数，返回 False 时工具集不可用
        requires_env: 需要的环境变量列表
    """
    
    description: str
    tools: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    check_fn: Optional[Callable[[], bool]] = None
    requires_env: List[str] = field(default_factory=list)
    
    def is_available(self) -> bool:
        """检查工具集是否可用。
        
        Returns:
            如果所有条件满足则返回 True
        """
        # 检查环境变量
        for env_var in self.requires_env:
            if not os.environ.get(env_var):
                logger.debug(f"工具集缺少环境变量: {env_var}")
                return False
        
        # 检查自定义函数
        if self.check_fn is not None:
            try:
                if not self.check_fn():
                    logger.debug(f"工具集条件检查未通过")
                    return False
            except Exception as e:
                logger.debug(f"工具集条件检查异常: {e}")
                return False
        
        return True


class ToolsetRegistry:
    """工具集注册表。
    
    管理工具集定义和解析。
    """
    
    def __init__(self):
        self._definitions: Dict[str, ToolsetDefinition] = {}
        self._tool_to_toolset: Dict[str, str] = {}
    
    def register(self, name: str, definition: ToolsetDefinition) -> None:
        """注册工具集。
        
        Args:
            name: 工具集名称
            definition: 工具集定义
        """
        self._definitions[name] = definition
        for tool_name in definition.tools:
            self._tool_to_toolset[tool_name] = name
        logger.debug(f"已注册工具集: {name}")
    
    def get(self, name: str) -> Optional[ToolsetDefinition]:
        """获取工具集定义。
        
        Args:
            name: 工具集名称
            
        Returns:
            工具集定义，不存在则返回 None
        """
        return self._definitions.get(name)
    
    def resolve(self, name: str, visited: Optional[Set[str]] = None) -> List[str]:
        """递归解析工具集，返回所有工具名称。
        
        Args:
            name: 工具集名称
            visited: 已访问的工具集（防止循环引用）
            
        Returns:
            工具名称列表
        """
        if visited is None:
            visited = set()
        
        if name in visited:
            logger.warning(f"检测到工具集循环引用: {name}")
            return []
        
        visited.add(name)
        definition = self._definitions.get(name)
        if not definition:
            logger.warning(f"工具集不存在: {name}")
            return []
        
        tools = set(definition.tools)
        
        # 递归解析包含的工具集
        for included_name in definition.includes:
            included_tools = self.resolve(included_name, visited)
            tools.update(included_tools)
        
        return sorted(tools)
    
    def check_requirements(self, name: str) -> Optional[str]:
        """检查工具集要求是否满足。
        
        Args:
            name: 工具集名称
            
        Returns:
            错误信息，如果满足要求则返回 None
        """
        definition = self._definitions.get(name)
        if not definition:
            return f"工具集 '{name}' 不存在"
        
        # 检查环境变量
        missing_env = [
            env for env in definition.requires_env
            if not os.environ.get(env)
        ]
        if missing_env:
            return f"缺少环境变量: {', '.join(missing_env)}"
        
        # 检查自定义函数
        if definition.check_fn is not None:
            try:
                if not definition.check_fn():
                    return f"工具集 '{name}' 的条件检查未通过"
            except Exception as e:
                return f"工具集 '{name}' 条件检查异常: {e}"
        
        return None
    
    def list_available(self) -> List[str]:
        """列出所有可用的工具集。
        
        Returns:
            可用工具集名称列表
        """
        return [
            name for name, definition in self._definitions.items()
            if definition.is_available()
        ]
    
    def list_all(self) -> List[str]:
        """列出所有已注册的工具集。
        
        Returns:
            所有工具集名称列表
        """
        return list(self._definitions.keys())


# 全局注册表
_global_registry = ToolsetRegistry()


def register_toolset(name: str, definition: ToolsetDefinition) -> None:
    """注册工具集到全局注册表。
    
    Args:
        name: 工具集名称
        definition: 工具集定义
    """
    _global_registry.register(name, definition)


def get_toolset(name: str) -> Optional[ToolsetDefinition]:
    """从全局注册表获取工具集。
    
    Args:
        name: 工具集名称
        
    Returns:
        工具集定义
    """
    return _global_registry.get(name)


def resolve_toolset(name: str) -> List[str]:
    """解析工具集获取工具列表。
    
    Args:
        name: 工具集名称
        
    Returns:
        工具名称列表
    """
    return _global_registry.resolve(name)


# 预定义工具集
BUILTIN_TOOLSETS = {
    "web": ToolsetDefinition(
        description="网络搜索和内容提取工具",
        tools=["web_search", "web_extract"],
    ),
    "terminal": ToolsetDefinition(
        description="终端命令执行工具",
        tools=["terminal", "process"],
    ),
    "file": ToolsetDefinition(
        description="文件操作工具",
        tools=["read_file", "write_file", "patch", "search_files"],
    ),
    "vision": ToolsetDefinition(
        description="图像分析工具",
        tools=["vision_analyze"],
    ),
    "browser": ToolsetDefinition(
        description="浏览器自动化工具",
        tools=[
            "browser_navigate", "browser_snapshot", "browser_click",
            "browser_type", "browser_scroll", "browser_back",
        ],
        includes=["web"],
    ),
    "delegate": ToolsetDefinition(
        description="子 Agent 委托工具",
        tools=["delegate_task"],
    ),
}

# 注册内置工具集
for name, definition in BUILTIN_TOOLSETS.items():
    register_toolset(name, definition)


__all__ = [
    "ToolsetDefinition",
    "ToolsetRegistry",
    "register_toolset",
    "get_toolset",
    "resolve_toolset",
    "BUILTIN_TOOLSETS",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_toolsets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentforge/tools/toolsets.py tests/test_toolsets.py
git commit -m "feat: 添加工具集系统 (ToolsetDefinition, ToolsetRegistry)"
```

---

## Task 2: 工具集系统 - ToolsetRegistry 测试

**Files:**
- Modify: `tests/test_toolsets.py`

- [ ] **Step 1: Write the failing test for ToolsetRegistry**

```python
# 添加到 tests/test_toolsets.py

class TestToolsetRegistry:
    """ToolsetRegistry 测试。"""

    def test_register_and_get(self):
        """测试注册和获取。"""
        registry = ToolsetRegistry()
        
        toolset = ToolsetDefinition(
            description="测试工具集",
            tools=["tool1", "tool2"],
        )
        
        registry.register("test", toolset)
        
        assert registry.get("test") == toolset

    def test_resolve_tools(self):
        """测试解析工具列表。"""
        registry = ToolsetRegistry()
        
        registry.register("base", ToolsetDefinition(
            description="基础工具",
            tools=["tool1"],
        ))
        
        registry.register("extended", ToolsetDefinition(
            description="扩展工具",
            tools=["tool2"],
            includes=["base"],
        ))
        
        tools = registry.resolve("extended")
        
        assert "tool1" in tools
        assert "tool2" in tools

    def test_resolve_circular(self):
        """测试循环引用检测。"""
        registry = ToolsetRegistry()
        
        registry.register("a", ToolsetDefinition(
            description="A",
            tools=["tool_a"],
            includes=["b"],
        ))
        
        registry.register("b", ToolsetDefinition(
            description="B",
            tools=["tool_b"],
            includes=["a"],
        ))
        
        # 不应该无限循环
        tools = registry.resolve("a")
        assert "tool_a" in tools

    def test_check_requirements(self):
        """测试要求检查。"""
        registry = ToolsetRegistry()
        
        registry.register("needs_key", ToolsetDefinition(
            description="需要 API Key",
            tools=["api_tool"],
            requires_env=["REQUIRED_API_KEY"],
        ))
        
        # 没有环境变量
        error = registry.check_requirements("needs_key")
        assert error is not None
        assert "REQUIRED_API_KEY" in error

    def test_list_available(self):
        """测试列出可用工具集。"""
        registry = ToolsetRegistry()
        
        registry.register("available", ToolsetDefinition(
            description="可用",
            tools=["tool1"],
        ))
        
        registry.register("unavailable", ToolsetDefinition(
            description="不可用",
            tools=["tool2"],
            check_fn=lambda: False,
        ))
        
        available = registry.list_available()
        
        assert "available" in available
        assert "unavailable" not in available
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_toolsets.py::TestToolsetRegistry -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_toolsets.py
git commit -m "test: 添加 ToolsetRegistry 测试"
```

---

## Task 3: 会话管理 - SessionProvider 接口

**Files:**
- Create: `agentforge/session/__init__.py`
- Create: `agentforge/session/base.py`
- Create: `agentforge/session/info.py`
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing test for SessionProvider**

```python
# tests/test_session.py
"""会话管理系统测试。"""

import pytest
import time

from agentforge.session import (
    SessionProvider,
    SessionInfo,
    MessageRecord,
    InMemorySessionProvider,
)


class TestSessionInfo:
    """SessionInfo 测试。"""

    def test_create_session_info(self):
        """测试创建会话信息。"""
        info = SessionInfo(
            id="session-1",
            source="cli",
        )

        assert info.id == "session-1"
        assert info.source == "cli"
        assert info.message_count == 0

    def test_parent_session(self):
        """测试父会话链接（压缩链）。"""
        info = SessionInfo(
            id="session-2",
            source="cli",
            parent_session_id="session-1",
        )

        assert info.parent_session_id == "session-1"


class TestMessageRecord:
    """MessageRecord 测试。"""

    def test_create_record(self):
        """测试创建消息记录。"""
        record = MessageRecord(
            id=1,
            session_id="session-1",
            role="user",
            content="你好",
        )

        assert record.id == 1
        assert record.role == "user"
        assert record.content == "你好"

    def test_multimodal_content(self):
        """测试多模态内容编码。"""
        content = [
            {"type": "text", "text": "看这张图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        ]
        
        record = MessageRecord(
            id=1,
            session_id="session-1",
            role="user",
            content=content,
        )

        # 编码后存储
        encoded = SessionProvider.encode_content(content)
        assert encoded.startswith("\x00json:")

        # 解码后恢复
        decoded = SessionProvider.decode_content(encoded)
        assert decoded == content


class TestInMemorySessionProvider:
    """InMemorySessionProvider 测试。"""

    def test_create_session(self):
        """测试创建会话。"""
        provider = InMemorySessionProvider()
        
        session_id = provider.create_session("test-session", "cli")
        
        assert session_id == "test-session"
        info = provider.get_session("test-session")
        assert info is not None
        assert info.source == "cli"

    def test_append_and_get_messages(self):
        """测试追加和获取消息。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")
        
        provider.append_message("test-session", "user", "你好")
        provider.append_message("test-session", "assistant", "你好！")
        
        messages = provider.get_messages("test-session")
        
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_set_and_get_title(self):
        """测试设置和获取标题。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")
        
        provider.set_session_title("test-session", "测试会话")
        
        info = provider.get_session("test-session")
        assert info.title == "测试会话"
        
        # 通过标题查找
        found = provider.get_session_by_title("测试会话")
        assert found is not None
        assert found.id == "test-session"

    def test_end_session(self):
        """测试结束会话。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")
        
        provider.end_session("test-session", "completed")
        
        info = provider.get_session("test-session")
        assert info.ended_at is not None
        assert info.end_reason == "completed"

    def test_compression_chain(self):
        """测试压缩链追踪。"""
        provider = InMemorySessionProvider()
        
        # 创建原始会话
        provider.create_session("session-1", "cli")
        
        # 创建压缩后的会话
        provider.create_session(
            "session-2",
            "cli",
            parent_session_id="session-1",
        )
        provider.end_session("session-1", "compression")
        
        # 获取压缩链末端
        tip = provider.get_compression_tip("session-1")
        assert tip == "session-2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session.py -v`
Expected: FAIL with "No module named 'agentforge.session'"

- [ ] **Step 3: Write SessionProvider implementation**

```python
# agentforge/session/__init__.py
"""会话管理模块。"""

from agentforge.session.base import SessionProvider
from agentforge.session.info import SessionInfo, MessageRecord
from agentforge.session.builtins.in_memory import InMemorySessionProvider

__all__ = [
    "SessionProvider",
    "SessionInfo",
    "MessageRecord",
    "InMemorySessionProvider",
]
```

```python
# agentforge/session/base.py
"""SessionProvider 抽象基类。"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agentforge.session.info import SessionInfo, MessageRecord

logger = logging.getLogger(__name__)


class SessionProvider(ABC):
    """会话存储提供者抽象基类。
    
    支持会话持久化、消息历史、压缩链追踪。
    参考 hermes-agent/hermes_state.py 的 SessionDB 实现。
    """
    
    @abstractmethod
    def create_session(
        self,
        session_id: str,
        source: str,
        **kwargs,
    ) -> str:
        """创建新会话。
        
        Args:
            session_id: 会话 ID
            source: 来源（cli、telegram、discord 等）
            
        Returns:
            会话 ID
        """
        ...
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息。
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话信息，不存在则返回 None
        """
        ...
    
    @abstractmethod
    def end_session(self, session_id: str, end_reason: str) -> None:
        """结束会话。
        
        Args:
            session_id: 会话 ID
            end_reason: 结束原因
        """
        ...
    
    @abstractmethod
    def append_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        **kwargs,
    ) -> int:
        """追加消息到会话。
        
        Args:
            session_id: 会话 ID
            role: 角色（user、assistant）
            content: 消息内容
            
        Returns:
            消息 ID
        """
        ...
    
    @abstractmethod
    def get_messages(self, session_id: str) -> List[MessageRecord]:
        """获取会话所有消息。
        
        Args:
            session_id: 会话 ID
            
        Returns:
            消息记录列表
        """
        ...
    
    @abstractmethod
    def set_session_title(self, session_id: str, title: str) -> bool:
        """设置会话标题。
        
        Args:
            session_id: 会话 ID
            title: 标题
            
        Returns:
            是否成功
        """
        ...
    
    @abstractmethod
    def get_session_by_title(self, title: str) -> Optional[SessionInfo]:
        """通过标题查找会话。
        
        Args:
            title: 标题
            
        Returns:
            会话信息
        """
        ...
    
    @abstractmethod
    def search_messages(
        self,
        query: str,
        session_id: str = None,
        limit: int = 20,
    ) -> List[MessageRecord]:
        """搜索消息内容。
        
        Args:
            query: 搜索查询
            session_id: 限定会话 ID（可选）
            limit: 最大结果数
            
        Returns:
            匹配的消息记录
        """
        ...
    
    @abstractmethod
    def list_sessions(
        self,
        source: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[SessionInfo]:
        """列出会话。
        
        Args:
            source: 限定来源（可选）
            limit: 最大数量
            offset: 偏移量
            
        Returns:
            会话信息列表
        """
        ...
    
    # 压缩链追踪
    def get_compression_tip(self, session_id: str) -> str:
        """获取压缩链的最新会话 ID。
        
        压缩链：parent_session_id 链接的会话序列，
        用于上下文压缩后继续对话。
        
        Args:
            session_id: 起始会话 ID
            
        Returns:
            链末端的会话 ID
        """
        current = session_id
        for _ in range(100):  # 防止无限循环
            session = self.get_session(current)
            if not session:
                return current
            # 查找子会话（end_reason='compression'）
            child = self._find_compression_child(current)
            if not child:
                return current
            current = child.id
        return current
    
    def get_session_lineage(self, session_id: str) -> List[str]:
        """获取会话的血统链（从根到当前）。
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话 ID 列表（从根到当前）
        """
        lineage = [session_id]
        current = session_id
        while True:
            session = self.get_session(current)
            if not session or not session.parent_session_id:
                break
            lineage.append(session.parent_session_id)
            current = session.parent_session_id
        return list(reversed(lineage))
    
    def _find_compression_child(self, session_id: str) -> Optional[SessionInfo]:
        """查找压缩子会话。
        
        Args:
            session_id: 父会话 ID
            
        Returns:
            子会话信息
        """
        # 默认实现：遍历所有会话
        # 子类可以优化此方法
        for session in self.list_sessions(limit=1000):
            if session.parent_session_id == session_id:
                parent = self.get_session(session_id)
                if parent and parent.end_reason == "compression":
                    return session
        return None
    
    # 消息编码/解码（用于多模态内容持久化）
    _CONTENT_JSON_PREFIX = "\x00json:"
    
    @staticmethod
    def encode_content(content: Any) -> Any:
        """编码内容用于存储。
        
        多模态内容（List[ContentBlock]）需要序列化为 JSON。
        使用哨兵前缀区分 JSON 编码内容和纯文本。
        
        Args:
            content: 原始内容
            
        Returns:
            编码后的内容
        """
        if content is None or isinstance(content, (str, bytes, int, float)):
            return content
        # 使用 NUL 字节作为哨兵前缀（不会出现在正常文本中）
        return SessionProvider._CONTENT_JSON_PREFIX + json.dumps(content)
    
    @staticmethod
    def decode_content(content: Any) -> Any:
        """解码存储的内容。
        
        Args:
            content: 存储的内容
            
        Returns:
            原始内容
        """
        if isinstance(content, str) and content.startswith(SessionProvider._CONTENT_JSON_PREFIX):
            try:
                return json.loads(content[len(SessionProvider._CONTENT_JSON_PREFIX):])
            except json.JSONDecodeError:
                return content
        return content
```

```python
# agentforge/session/info.py
"""会话信息数据结构。"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionInfo:
    """会话信息。
    
    Attributes:
        id: 会话 ID
        source: 来源（cli、telegram、discord 等）
        user_id: 用户 ID
        model: 模型名称
        model_config: 模型配置
        system_prompt: 系统提示
        parent_session_id: 父会话 ID（压缩链/分支链）
        started_at: 开始时间戳
        ended_at: 结束时间戳
        end_reason: 结束原因
        message_count: 消息数量
        title: 会话标题
    """
    
    id: str
    source: str
    user_id: Optional[str] = None
    model: Optional[str] = None
    model_config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    parent_session_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    end_reason: Optional[str] = None
    message_count: int = 0
    title: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return dataclasses.asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionInfo":
        """从字典创建。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MessageRecord:
    """消息记录。
    
    Attributes:
        id: 消息 ID
        session_id: 会话 ID
        role: 角色（user、assistant）
        content: 消息内容（str 或 List[ContentBlock]）
        tool_call_id: 工具调用 ID
        tool_calls: 工具调用列表
        tool_name: 工具名称
        timestamp: 时间戳
        token_count: Token 数量
        finish_reason: 结束原因
        reasoning: 推理内容
    """
    
    id: int
    session_id: str
    role: str
    content: Any
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_name: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    token_count: Optional[int] = None
    finish_reason: Optional[str] = None
    reasoning: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return dataclasses.asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageRecord":
        """从字典创建。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
```

```python
# agentforge/session/builtins/__init__.py
"""内置会话提供者。"""

from agentforge.session.builtins.in_memory import InMemorySessionProvider

__all__ = ["InMemorySessionProvider"]
```

```python
# agentforge/session/builtins/in_memory.py
"""内存会话提供者。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from agentforge.session.base import SessionProvider
from agentforge.session.info import SessionInfo, MessageRecord

logger = logging.getLogger(__name__)


class InMemorySessionProvider(SessionProvider):
    """内存会话提供者。
    
    默认实现，适用于测试和短期会话。
    """
    
    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._messages: Dict[str, List[MessageRecord]] = {}
        self._title_index: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._message_id_counter = 0
    
    def create_session(
        self,
        session_id: str,
        source: str,
        **kwargs,
    ) -> str:
        with self._lock:
            session = SessionInfo(
                id=session_id,
                source=source,
                **kwargs,
            )
            self._sessions[session_id] = session
            self._messages[session_id] = []
        return session_id
    
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        with self._lock:
            return self._sessions.get(session_id)
    
    def end_session(self, session_id: str, end_reason: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.ended_at = time.time()
                session.end_reason = end_reason
    
    def append_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        **kwargs,
    ) -> int:
        with self._lock:
            self._message_id_counter += 1
            record = MessageRecord(
                id=self._message_id_counter,
                session_id=session_id,
                role=role,
                content=self.encode_content(content),
                **kwargs,
            )
            self._messages.setdefault(session_id, []).append(record)
            
            session = self._sessions.get(session_id)
            if session:
                session.message_count += 1
            
            return record.id
    
    def get_messages(self, session_id: str) -> List[MessageRecord]:
        with self._lock:
            messages = self._messages.get(session_id, [])
            # 解码内容
            return [
                MessageRecord(
                    **{k: self.decode_content(v) if k == "content" else v
                       for k, v in dataclasses.asdict(m).items()}
                )
                for m in messages
            ]
    
    def set_session_title(self, session_id: str, title: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            # 检查标题唯一性
            if title in self._title_index and self._title_index[title] != session_id:
                raise ValueError(f"标题 '{title}' 已被其他会话使用")
            # 清除旧标题索引
            if session.title:
                self._title_index.pop(session.title, None)
            session.title = title
            self._title_index[title] = session_id
            return True
    
    def get_session_by_title(self, title: str) -> Optional[SessionInfo]:
        with self._lock:
            session_id = self._title_index.get(title)
            if session_id:
                return self._sessions.get(session_id)
            return None
    
    def search_messages(
        self,
        query: str,
        session_id: str = None,
        limit: int = 20,
    ) -> List[MessageRecord]:
        results = []
        with self._lock:
            sessions_to_search = [session_id] if session_id else list(self._messages.keys())
            for sid in sessions_to_search:
                for msg in self._messages.get(sid, []):
                    content = self.decode_content(msg.content)
                    if isinstance(content, str) and query.lower() in content.lower():
                        results.append(msg)
                        if len(results) >= limit:
                            return results
        return results
    
    def list_sessions(
        self,
        source: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[SessionInfo]:
        with self._lock:
            sessions = list(self._sessions.values())
            if source:
                sessions = [s for s in sessions if s.source == source]
            sessions.sort(key=lambda s: s.started_at, reverse=True)
            return sessions[offset:offset + limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentforge/session/ tests/test_session.py
git commit -m "feat: 添加会话管理系统 (SessionProvider, SessionInfo, MessageRecord)"
```

---

## Task 4: Agent 活动追踪

**Files:**
- Modify: `agentforge/agent.py`
- Test: `tests/test_p4_agent.py`

- [ ] **Step 1: Write the failing test for activity tracking**

```python
# 添加到 tests/test_p4_agent.py

class TestAgentActivityTracking:
    """Agent 活动追踪测试。"""

    def test_activity_timestamp(self):
        """测试活动时间戳更新。"""
        import time
        from agentforge.agent import Agent
        from agentforge.providers.builtins import OpenAIProvider
        
        provider = OpenAIProvider(api_key="test-key")
        agent = Agent(provider=provider)
        
        # 获取初始时间戳
        initial_ts = agent._last_activity_ts
        assert initial_ts > 0
        
        # 等待一小段时间
        time.sleep(0.1)
        
        # 触发活动更新
        agent._touch_activity("测试活动")
        
        # 时间戳应该更新
        assert agent._last_activity_ts > initial_ts
        assert agent._last_activity_desc == "测试活动"

    def test_activity_summary(self):
        """测试活动摘要。"""
        from agentforge.agent import Agent
        from agentforge.providers.builtins import OpenAIProvider
        
        provider = OpenAIProvider(api_key="test-key")
        agent = Agent(provider=provider)
        
        agent._touch_activity("处理请求")
        agent._api_call_count = 5
        
        summary = agent.get_activity_summary()
        
        assert "last_activity_ts" in summary
        assert "last_activity_desc" in summary
        assert summary["last_activity_desc"] == "处理请求"
        assert summary["api_call_count"] == 5
        assert "seconds_since_activity" in summary

    def test_rate_limit_state(self):
        """测试速率限制状态。"""
        from agentforge.agent import Agent
        from agentforge.providers.builtins import OpenAIProvider
        
        provider = OpenAIProvider(api_key="test-key")
        agent = Agent(provider=provider)
        
        # 初始状态为 None
        assert agent._rate_limit_state is None
        
        # 模拟捕获速率限制
        agent._capture_rate_limit_state({
            "headers": {
                "x-ratelimit-remaining": "10",
                "x-ratelimit-reset": "60",
            }
        })
        
        # 应该有状态了
        assert agent._rate_limit_state is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p4_agent.py::TestAgentActivityTracking -v`
Expected: FAIL with "AttributeError: 'Agent' object has no attribute '_touch_activity'"

- [ ] **Step 3: Add activity tracking to Agent**

在 `agentforge/agent.py` 中添加活动追踪相关代码：

```python
# 在 Agent.__init__ 中添加（约第 170 行后）

        # Agent 状态追踪（用于诊断和监控）
        self._last_activity_ts: float = time.time()
        self._last_activity_desc: str = "初始化"
        self._rate_limit_state: Optional[Dict[str, Any]] = None
        self._api_call_count: int = 0
```

```python
# 添加方法（在类末尾）

    def _touch_activity(self, desc: str) -> None:
        """更新活动状态（线程安全）。
        
        Args:
            desc: 活动描述
        """
        self._last_activity_ts = time.time()
        self._last_activity_desc = desc
    
    def _capture_rate_limit_state(self, http_response: Any) -> None:
        """从 HTTP 响应捕获速率限制状态。
        
        Args:
            http_response: HTTP 响应对象
        """
        if http_response is None:
            return
        headers = getattr(http_response, "headers", None)
        if not headers:
            return
        try:
            self._rate_limit_state = {
                "remaining": headers.get("x-ratelimit-remaining"),
                "reset": headers.get("x-ratelimit-reset"),
                "limit": headers.get("x-ratelimit-limit"),
            }
        except Exception:
            pass
    
    def get_activity_summary(self) -> Dict[str, Any]:
        """返回 Agent 当前活动状态摘要（用于诊断）。
        
        Returns:
            活动状态摘要
        """
        return {
            "last_activity_ts": self._last_activity_ts,
            "last_activity_desc": self._last_activity_desc,
            "seconds_since_activity": round(time.time() - self._last_activity_ts, 1),
            "api_call_count": self._api_call_count,
            "rate_limit_state": self._rate_limit_state,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_p4_agent.py::TestAgentActivityTracking -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentforge/agent.py tests/test_p4_agent.py
git commit -m "feat: 添加 Agent 活动追踪 (_last_activity_ts, get_activity_summary)"
```

---

## Task 5: EventType 扩展

**Files:**
- Modify: `agentforge/events/types.py`
- Test: `tests/test_p2_interrupt_events.py`

- [ ] **Step 1: Write the failing test for new event types**

```python
# 添加到 tests/test_p2_interrupt_events.py

class TestExtendedEventTypes:
    """扩展事件类型测试。"""

    def test_agent_thinking_event(self):
        """测试 AGENT_THINKING 事件。"""
        from agentforge.events import EventType
        
        assert hasattr(EventType, "AGENT_THINKING")
        assert EventType.AGENT_THINKING == "agent.thinking"

    def test_agent_reasoning_event(self):
        """测试 AGENT_REASONING 事件。"""
        from agentforge.events import EventType
        
        assert hasattr(EventType, "AGENT_REASONING")
        assert EventType.AGENT_REASONING == "agent.reasoning"

    def test_tool_progress_event(self):
        """测试 TOOL_PROGRESS 事件。"""
        from agentforge.events import EventType
        
        assert hasattr(EventType, "TOOL_PROGRESS")
        assert EventType.TOOL_PROGRESS == "tool.progress"

    def test_stream_delta_event(self):
        """测试 STREAM_DELTA 事件。"""
        from agentforge.events import EventType
        
        assert hasattr(EventType, "STREAM_DELTA")
        assert EventType.STREAM_DELTA == "stream.delta"

    def test_clarify_request_event(self):
        """测试 CLARIFY_REQUEST 事件。"""
        from agentforge.events import EventType
        
        assert hasattr(EventType, "CLARIFY_REQUEST")
        assert EventType.CLARIFY_REQUEST == "clarify.request"

    def test_all_new_event_types(self):
        """测试所有新增事件类型。"""
        from agentforge.events import EventType
        
        new_types = [
            "AGENT_THINKING",
            "AGENT_REASONING",
            "AGENT_STATUS",
            "TOOL_PROGRESS",
            "STREAM_DELTA",
            "STREAM_CHUNK",
            "STREAM_END",
            "CLARIFY_REQUEST",
            "INTERIM_ASSISTANT",
            "TOOL_GENERATED",
            "MEMORY_PREFETCH",
            "MEMORY_PREFETCH_DONE",
            "MEMORY_SYNC",
            "MEMORY_SYNC_DONE",
        ]
        
        for type_name in new_types:
            assert hasattr(EventType, type_name), f"Missing EventType.{type_name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p2_interrupt_events.py::TestExtendedEventTypes -v`
Expected: FAIL with "AssertionError: False is not true : Missing EventType.AGENT_THINKING"

- [ ] **Step 3: Extend EventType**

```python
# 修改 agentforge/events/types.py

class EventType:
    """事件类型常量。"""
    
    # Agent 生命周期
    AGENT_START = "agent.start"
    AGENT_END = "agent.end"
    AGENT_INTERRUPT = "agent.interrupt"
    AGENT_THINKING = "agent.thinking"       # 思考过程（流式）
    AGENT_REASONING = "agent.reasoning"     # 推理过程（流式）
    AGENT_STATUS = "agent.status"           # 状态更新
    
    # 工具执行
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    TOOL_ERROR = "tool.error"
    TOOL_PROGRESS = "tool.progress"         # 工具执行进度
    TOOL_APPROVAL_REQUIRED = "tool.approval_required"
    
    # Provider 调用
    PROVIDER_REQUEST = "provider.request"
    PROVIDER_RESPONSE = "provider.response"
    PROVIDER_ERROR = "provider.error"
    STREAM_DELTA = "stream.delta"           # 流式 Token 增量
    STREAM_CHUNK = "stream.chunk"           # 流式响应块
    STREAM_END = "stream.end"               # 流式结束
    
    # 上下文压缩
    COMPRESSION_START = "compression.start"
    COMPRESSION_END = "compression.end"
    
    # 委托
    DELEGATION_START = "delegation.start"
    DELEGATION_END = "delegation.end"
    
    # 用户交互
    CLARIFY_REQUEST = "clarify.request"     # 澄清请求
    INTERIM_ASSISTANT = "interim.assistant" # 中间 assistant 消息
    TOOL_GENERATED = "tool.generated"       # 工具调用生成
    
    # 记忆管理
    MEMORY_PREFETCH = "memory.prefetch"
    MEMORY_PREFETCH_DONE = "memory.prefetch_done"
    MEMORY_SYNC = "memory.sync"
    MEMORY_SYNC_DONE = "memory.sync_done"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_p2_interrupt_events.py::TestExtendedEventTypes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentforge/events/types.py tests/test_p2_interrupt_events.py
git commit -m "feat: 扩展 EventType（AGENT_THINKING, TOOL_PROGRESS 等）"
```

---

## Task 6: 模型能力系统

**Files:**
- Create: `agentforge/core/model_metadata.py`
- Modify: `agentforge/utils/model_metadata.py`
- Test: `tests/test_model_metadata.py`

- [ ] **Step 1: Write the failing test for ModelCapabilities**

```python
# tests/test_model_metadata.py
"""模型能力系统测试。"""

import pytest

from agentforge.core.model_metadata import (
    ModelCapabilities,
    DefaultModelMetadataProvider,
)


class TestModelCapabilities:
    """ModelCapabilities 测试。"""

    def test_default_capabilities(self):
        """测试默认能力。"""
        caps = ModelCapabilities()
        
        assert caps.context_length == 128000
        assert caps.supports_tools is True
        assert caps.supports_vision is False

    def test_custom_capabilities(self):
        """测试自定义能力。"""
        caps = ModelCapabilities(
            context_length=200000,
            supports_vision=True,
            supports_reasoning=True,
            reasoning_effort_levels=["low", "medium", "high"],
        )
        
        assert caps.context_length == 200000
        assert caps.supports_vision is True
        assert "high" in caps.reasoning_effort_levels


class TestDefaultModelMetadataProvider:
    """DefaultModelMetadataProvider 测试。"""

    def test_get_gpt4_capabilities(self):
        """测试获取 GPT-4 能力。"""
        provider = DefaultModelMetadataProvider()
        
        caps = provider.get_model_capabilities("gpt-4")
        
        assert caps.supports_tools is True
        assert caps.supports_vision is True

    def test_get_claude_capabilities(self):
        """测试获取 Claude 能力。"""
        provider = DefaultModelMetadataProvider()
        
        caps = provider.get_model_capabilities("claude-opus-4")
        
        assert caps.context_length == 200000
        assert caps.supports_prompt_caching is True

    def test_get_deepseek_capabilities(self):
        """测试获取 DeepSeek 能力。"""
        provider = DefaultModelMetadataProvider()
        
        caps = provider.get_model_capabilities("deepseek-v3")
        
        assert caps.supports_reasoning is True

    def test_estimate_tokens_text(self):
        """测试文本 Token 估算。"""
        provider = DefaultModelMetadataProvider()
        
        # 100 字符约 25 Token
        tokens = provider.estimate_tokens("a" * 100)
        
        assert tokens == 25

    def test_estimate_tokens_multimodal(self):
        """测试多模态 Token 估算。"""
        provider = DefaultModelMetadataProvider()
        
        content = [
            {"type": "text", "text": "hello"},  # ~1 Token
            {"type": "image_url", "image_url": {"url": "..."}},  # ~1600 Token
        ]
        
        tokens = provider.estimate_tokens(content)
        
        assert tokens >= 1600

    def test_unknown_model_defaults(self):
        """测试未知模型返回默认值。"""
        provider = DefaultModelMetadataProvider()
        
        caps = provider.get_model_capabilities("unknown-model-xyz")
        
        assert caps.context_length == 128000  # 默认值
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_model_metadata.py -v`
Expected: FAIL with "No module named 'agentforge.core.model_metadata'"

- [ ] **Step 3: Write ModelCapabilities implementation**

```python
# agentforge/core/model_metadata.py
"""模型能力系统。

提供 Provider 声明和查询模型特性的机制。
参考 hermes-agent/agent/model_metadata.py 实现。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class ModelCapabilities:
    """模型能力描述。
    
    Provider 通过此结构声明其支持的模型特性，
    用于运行时决策（如是否启用特定功能）。
    
    Attributes:
        context_length: 上下文窗口大小
        max_output_tokens: 最大输出 Token
        supports_tools: 是否支持工具调用
        supports_vision: 是否支持视觉
        supports_streaming: 是否支持流式
        supports_reasoning: 是否支持推理
        reasoning_effort_levels: 推理级别列表
        supports_prompt_caching: 是否支持提示缓存
        supports_parallel_tool_calls: 是否支持并行工具调用
        pricing: 价格信息
    """
    
    context_length: int = 128000
    max_output_tokens: int = 4096
    
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    
    supports_reasoning: bool = False
    reasoning_effort_levels: List[str] = field(default_factory=list)
    
    supports_prompt_caching: bool = False
    supports_parallel_tool_calls: bool = True
    
    pricing: Optional[Dict[str, float]] = None


class ModelMetadataProvider:
    """模型元数据提供者接口。"""
    
    def get_model_capabilities(self, model: str) -> ModelCapabilities:
        """获取模型能力描述。
        
        Args:
            model: 模型名称
            
        Returns:
            模型能力
        """
        raise NotImplementedError
    
    def estimate_tokens(self, content: Union[str, List[Dict]]) -> int:
        """估算内容的 Token 数量。
        
        Args:
            content: 文本或多模态内容
            
        Returns:
            Token 数量估算
        """
        raise NotImplementedError


class DefaultModelMetadataProvider(ModelMetadataProvider):
    """默认模型元数据提供者。
    
    参考 hermes-agent/agent/model_metadata.py 实现。
    """
    
    # Token 估算常量
    CHARS_PER_TOKEN = 4  # 平均每 Token 约 4 字符
    IMAGE_TOKEN_ESTIMATE = 1600  # 单张图片约 1600 Token
    
    # 预定义模型能力
    MODEL_CAPABILITIES: Dict[str, ModelCapabilities] = {
        # OpenAI
        "gpt-4": ModelCapabilities(
            context_length=128000,
            supports_tools=True,
            supports_vision=True,
            supports_parallel_tool_calls=True,
        ),
        "gpt-4-turbo": ModelCapabilities(
            context_length=128000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),
        "gpt-4o": ModelCapabilities(
            context_length=128000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),
        
        # Anthropic
        "claude-opus-4": ModelCapabilities(
            context_length=200000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),
        "claude-sonnet-4": ModelCapabilities(
            context_length=200000,
            supports_tools=True,
            supports_vision=True,
            supports_prompt_caching=True,
        ),
        
        # 中国大模型
        "deepseek-v3": ModelCapabilities(
            context_length=64000,
            supports_tools=True,
            supports_reasoning=True,
        ),
        "qwen-max": ModelCapabilities(
            context_length=32000,
            supports_tools=True,
            supports_vision=True,
        ),
        "kimi": ModelCapabilities(
            context_length=200000,
            supports_tools=True,
            supports_reasoning=True,
            reasoning_effort_levels=["low", "medium", "high"],
        ),
    }
    
    def get_model_capabilities(self, model: str) -> ModelCapabilities:
        """获取模型能力描述。
        
        Args:
            model: 模型名称
            
        Returns:
            模型能力
        """
        # 精确匹配
        if model in self.MODEL_CAPABILITIES:
            return self.MODEL_CAPABILITIES[model]
        
        # 模糊匹配（前缀）
        model_lower = model.lower()
        for key, caps in self.MODEL_CAPABILITIES.items():
            if model_lower.startswith(key.lower()):
                return caps
        
        # 默认值
        return ModelCapabilities()
    
    def estimate_tokens(self, content: Union[str, List[Dict]]) -> int:
        """估算内容的 Token 数量。
        
        Args:
            content: 文本或多模态内容
            
        Returns:
            Token 数量估算
        """
        if isinstance(content, str):
            return (len(content) + self.CHARS_PER_TOKEN - 1) // self.CHARS_PER_TOKEN
        
        total = 0
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    total += len(text) // self.CHARS_PER_TOKEN
                elif block_type == "image_url":
                    total += self.IMAGE_TOKEN_ESTIMATE
                elif block_type == "tool_use":
                    import json
                    input_data = block.get("input", {})
                    total += len(json.dumps(input_data)) // self.CHARS_PER_TOKEN
                elif block_type == "tool_result":
                    content_str = block.get("content", "")
                    total += len(str(content_str)) // self.CHARS_PER_TOKEN
        
        return total


__all__ = [
    "ModelCapabilities",
    "ModelMetadataProvider",
    "DefaultModelMetadataProvider",
]
```

- [ ] **Step 4: Update core/__init__.py**

```python
# 在 agentforge/core/__init__.py 中添加

from agentforge.core.model_metadata import (
    ModelCapabilities,
    ModelMetadataProvider,
    DefaultModelMetadataProvider,
)

# 添加到 __all__
__all__ = [
    # ... 现有导出 ...
    # 模型能力
    "ModelCapabilities",
    "ModelMetadataProvider",
    "DefaultModelMetadataProvider",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_model_metadata.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agentforge/core/model_metadata.py agentforge/core/__init__.py tests/test_model_metadata.py
git commit -m "feat: 添加模型能力系统 (ModelCapabilities, DefaultModelMetadataProvider)"
```

---

## Task 7: 更新 __init__.py 导出

**Files:**
- Modify: `agentforge/__init__.py`

- [ ] **Step 1: Update main __init__.py**

```python
# 在 agentforge/__init__.py 中添加新模块导出

# 工具集
from agentforge.tools.toolsets import (
    ToolsetDefinition,
    ToolsetRegistry,
    register_toolset,
    get_toolset,
    resolve_toolset,
)

# 会话管理
from agentforge.session import (
    SessionProvider,
    SessionInfo,
    MessageRecord,
    InMemorySessionProvider,
)

# 模型能力
from agentforge.core.model_metadata import (
    ModelCapabilities,
    DefaultModelMetadataProvider,
)

# 更新 __all__
__all__ = [
    # ... 现有导出 ...
    
    # 工具集
    "ToolsetDefinition",
    "ToolsetRegistry",
    "register_toolset",
    "get_toolset",
    "resolve_toolset",
    
    # 会话管理
    "SessionProvider",
    "SessionInfo",
    "MessageRecord",
    "InMemorySessionProvider",
    
    # 模型能力
    "ModelCapabilities",
    "DefaultModelMetadataProvider",
]
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from agentforge import ToolsetDefinition, SessionProvider, ModelCapabilities; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add agentforge/__init__.py
git commit -m "feat: 更新 __init__.py 导出新模块"
```

---

## Task 8: 集成测试

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""集成测试：验证所有组件协同工作。"""

import pytest

from agentforge import (
    Agent,
    ToolsetDefinition,
    register_toolset,
    InMemorySessionProvider,
    ModelCapabilities,
    DefaultModelMetadataProvider,
)
from agentforge.providers.builtins import OpenAIProvider


class TestIntegration:
    """集成测试。"""

    def test_agent_with_toolsets(self):
        """测试 Agent 使用工具集。"""
        # 注册自定义工具集
        register_toolset("custom", ToolsetDefinition(
            description="自定义工具集",
            tools=["custom_tool"],
        ))
        
        # 创建 Agent
        provider = OpenAIProvider(api_key="test-key")
        agent = Agent(provider=provider)
        
        # 验证工具集已注册
        from agentforge.tools.toolsets import get_toolset
        toolset = get_toolset("custom")
        assert toolset is not None

    def test_agent_with_session(self):
        """测试 Agent 使用会话管理。"""
        provider = OpenAIProvider(api_key="test-key")
        agent = Agent(provider=provider)
        
        # 添加会话提供者
        session_provider = InMemorySessionProvider()
        agent.add_memory("session", session_provider)
        
        # 验证可以访问
        assert agent.get_memory("session") is not None

    def test_model_capabilities_integration(self):
        """测试模型能力集成。"""
        meta_provider = DefaultModelMetadataProvider()
        
        # 获取 GPT-4 能力
        caps = meta_provider.get_model_capabilities("gpt-4")
        
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        
        # 估算 Token
        tokens = meta_provider.estimate_tokens("Hello world")
        assert tokens > 0

    def test_activity_tracking_integration(self):
        """测试活动追踪集成。"""
        provider = OpenAIProvider(api_key="test-key")
        agent = Agent(provider=provider)
        
        # 更新活动状态
        agent._touch_activity("集成测试")
        
        # 获取摘要
        summary = agent.get_activity_summary()
        
        assert summary["last_activity_desc"] == "集成测试"
        assert "seconds_since_activity" in summary
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: 添加集成测试"
```

---

## 自检清单

### 1. 规格覆盖检查

| 设计文档章节 | 对应任务 | 状态 |
|-------------|---------|------|
| 5.5 工具集系统 | Task 1-2 | ✅ |
| 5.6 会话管理系统 | Task 3 | ✅ |
| Agent 活动追踪 | Task 4 | ✅ |
| EventType 扩展 | Task 5 | ✅ |
| 5.7 模型能力系统 | Task 6 | ✅ |

### 2. 占位符扫描

- [ ] 无 TBD/TODO
- [ ] 无 "implement later"
- [ ] 无 "add validation" 无具体代码
- [ ] 无 "similar to Task N"
- [ ] 所有代码步骤都有完整代码

### 3. 类型一致性

- [ ] ToolsetDefinition.is_available() 返回 bool
- [ ] SessionProvider.encode_content() 使用 "\x00json:" 前缀
- [ ] ModelCapabilities.context_length 默认 128000
- [ ] EventType 值格式为 "category.action"

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-22-agentforge-completion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
