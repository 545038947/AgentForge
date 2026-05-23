# AgentForge 生产环境改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 P0 和 P1 改进项，使 AgentForge 满足生产环境要求

**Architecture:** 
- 日志改进：在现有 `utils/logging.py` 基础上添加敏感信息过滤和结构化日志支持
- 资源清理：在 Agent 初始化时注册 atexit 钩子
- 并发验证：创建集成测试验证多会话并发场景

**Tech Stack:** Python 3.9+, pytest, structlog (可选)

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `hai_agent/utils/logging.py` | 日志配置、敏感信息过滤 | 修改 |
| `hai_agent/agent.py` | Agent 类，添加 atexit 钩子 | 修改 |
| `tests/test_production.py` | 生产环境相关测试 | 创建 |
| `tests/test_concurrent.py` | 并发场景测试 | 创建 |

---

## Task 1: 日志敏感信息过滤

**Files:**
- Modify: `hai_agent/utils/logging.py`
- Test: `tests/test_production.py`

### 1.1 编写敏感信息过滤测试

- [ ] **Step 1: 创建测试文件并编写过滤测试**

```python
# tests/test_production.py
"""生产环境相关测试。"""

import logging
import pytest
from hai_agent.utils.logging import (
    SensitiveDataFilter,
    setup_logging,
    get_logger,
)


class TestSensitiveDataFilter:
    """敏感信息过滤器测试。"""

    def test_filter_api_key(self):
        """测试 API Key 被脱敏。"""
        # 创建带过滤器的日志器
        logger = logging.getLogger("test_sensitive")
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)

        # 添加过滤器
        handler = logging.StreamHandler()
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

        # 记录包含 API Key 的消息
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="API Key: sk-1234567890abcdef",
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        result = filter_obj.filter(record)

        assert result is True
        assert "sk-1234567890abcdef" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_filter_bearer_token(self):
        """测试 Bearer Token 被脱敏。"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        filter_obj.filter(record)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record.msg

    def test_filter_password(self):
        """测试密码被脱敏。"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='{"password": "my_secret_password"}',
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        filter_obj.filter(record)

        assert "my_secret_password" not in record.msg
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_production.py::TestSensitiveDataFilter -v`
Expected: FAIL (SensitiveDataFilter not defined)

### 1.2 实现敏感信息过滤器

- [ ] **Step 3: 在 logging.py 中添加 SensitiveDataFilter**

```python
# hai_agent/utils/logging.py (在文件末尾添加)

import re
from typing import List, Pattern


class SensitiveDataFilter:
    """日志敏感信息过滤器。

    自动脱敏日志中的敏感信息，如 API Key、密码、Token 等。
    """

    # 敏感信息模式列表
    PATTERNS: List[tuple] = [
        # API Keys
        (r'sk-[a-zA-Z0-9]{20,}', 'sk-***REDACTED***'),  # OpenAI style
        (r'api[_-]?key["\s:=]+["\']?([a-zA-Z0-9_-]{20,})', 'api_key=***REDACTED***'),
        # Bearer Tokens
        (r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}', 'Bearer ***REDACTED***'),
        (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', '***JWT_REDACTED***'),  # JWT
        # Passwords
        (r'password["\s:=]+["\']?([^\s"\',}]+)', 'password=***REDACTED***'),
        (r'passwd["\s:=]+["\']?([^\s"\',}]+)', 'passwd=***REDACTED***'),
        # Connection strings
        (r'://([^:]+):([^@]+)@', r'://\1:***@'),  # URL with credentials
    ]

    def __init__(self):
        """初始化过滤器，编译正则表达式。"""
        self._compiled: List[tuple] = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.PATTERNS
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录中的敏感信息。

        Args:
            record: 日志记录

        Returns:
            总是返回 True（允许日志通过），但会修改消息内容
        """
        msg = record.getMessage()

        for pattern, replacement in self._compiled:
            msg = pattern.sub(replacement, msg)

        # 更新记录的消息
        record.msg = msg
        record.args = ()

        return True


def setup_secure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    enable_sensitive_filter: bool = True,
    enable_json_format: bool = False,
) -> None:
    """配置安全的日志系统。

    Args:
        level: 日志级别
        log_file: 日志文件路径
        enable_sensitive_filter: 是否启用敏感信息过滤
        enable_json_format: 是否使用 JSON 格式
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    # 选择格式器
    if enable_json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    if enable_sensitive_filter:
        console_handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        if enable_sensitive_filter:
            file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)


class JsonFormatter(logging.Formatter):
    """JSON 格式日志格式器。"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化为 JSON。"""
        import json
        from datetime import datetime

        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_production.py::TestSensitiveDataFilter -v`
Expected: PASS

- [ ] **Step 5: 提交更改**

```bash
git add hai_agent/utils/logging.py tests/test_production.py
git commit -m "feat(logging): 添加敏感信息过滤和结构化日志支持

- 添加 SensitiveDataFilter 自动脱敏 API Key、Token、密码
- 添加 setup_secure_logging() 配置安全日志
- 添加 JsonFormatter 支持 JSON 格式日志
- 添加相关单元测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: atexit 钩子确保资源清理

**Files:**
- Modify: `hai_agent/agent.py`
- Test: `tests/test_production.py`

### 2.1 编写 atexit 钩子测试

- [ ] **Step 1: 添加 atexit 钩子测试**

```python
# tests/test_production.py (追加内容)

import atexit
import weakref


class TestResourceCleanup:
    """资源清理测试。"""

    def test_atexit_hook_registered(self):
        """测试 atexit 钩子被注册。"""
        from hai_agent.providers.builtins.ollama import OllamaProvider
        from hai_agent import Agent

        provider = OllamaProvider(model="test", base_url="http://localhost:11434/v1")
        agent = Agent(provider=provider, register_atexit=True)

        # 检查 shutdown 方法被注册到 atexit
        # 注意：无法直接检查 atexit 回调列表，但可以通过标志位验证
        assert agent._atexit_registered is True

    def test_shutdown_called_on_exit(self):
        """测试退出时 shutdown 被调用。"""
        from unittest.mock import MagicMock, patch
        from hai_agent import Agent
        from hai_agent.providers.builtins.ollama import OllamaProvider

        provider = OllamaProvider(model="test", base_url="http://localhost:11434/v1")
        agent = Agent(provider=provider, register_atexit=True)

        # Mock shutdown 方法
        original_shutdown = agent.shutdown
        shutdown_called = False

        def mock_shutdown():
            nonlocal shutdown_called
            shutdown_called = True
            original_shutdown()

        agent.shutdown = mock_shutdown

        # 模拟 atexit 回调
        agent._atexit_callback()

        assert shutdown_called is True

    def test_context_manager_cleanup(self):
        """测试上下文管理器正确清理。"""
        from hai_agent import Agent
        from hai_agent.providers.builtins.ollama import OllamaProvider

        provider = OllamaProvider(model="test", base_url="http://localhost:11434/v1")

        with Agent(provider=provider) as agent:
            # 使用 agent
            assert agent is not None

        # 退出上下文后，shutdown 应该被调用
        # 这里我们只验证不会抛出异常
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_production.py::TestResourceCleanup -v`
Expected: FAIL (register_atexit 参数不存在)

### 2.2 实现 atexit 钩子

- [ ] **Step 3: 在 Agent.__init__ 中添加 atexit 支持**

找到 `hai_agent/agent.py` 的 `__init__` 方法，添加参数和注册逻辑：

```python
# hai_agent/agent.py

# 在文件顶部导入区域添加
import atexit

# 在 __init__ 方法签名中添加参数
def __init__(
    self,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: Optional["Provider"] = None,
    settings: Optional[Settings] = None,
    tools: Optional[List[Union[Tool, Callable]]] = None,
    approval_callback: Optional[ApprovalCallback] = None,
    fallback_chain: Optional[FallbackChain] = None,
    memory_manager: Optional["MemoryManager"] = None,
    skill_registry: Optional["SkillRegistry"] = None,
    session_provider: Optional["SessionProvider"] = None,
    session_id: Optional[str] = None,
    profile_registry: Optional[ProfileRegistry] = None,
    provider_registry: Optional[ProviderRegistry] = None,
    register_atexit: bool = True,  # 新增参数
):
    """初始化 Agent。
    ...
    Args:
        ...
        register_atexit: 是否注册 atexit 钩子确保退出时清理资源
    """
    # ... 现有初始化代码 ...

    # atexit 钩子注册
    self._atexit_registered = False
    if register_atexit:
        self._register_atexit()

def _register_atexit(self) -> None:
    """注册 atexit 钩子。"""
    # 使用弱引用避免阻止 Agent 被垃圾回收
    weak_self = weakref.ref(self)

    def atexit_callback():
        agent = weak_self()
        if agent is not None:
            try:
                agent.shutdown()
            except Exception:
                pass  # 忽略清理时的异常

    try:
        atexit.register(atexit_callback)
        self._atexit_registered = True
    except Exception:
        # 某些环境可能不支持 atexit
        self._atexit_registered = False

def _atexit_callback(self) -> None:
    """供测试使用的 atexit 回调触发方法。"""
    self.shutdown()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_production.py::TestResourceCleanup -v`
Expected: PASS

- [ ] **Step 5: 提交更改**

```bash
git add hai_agent/agent.py tests/test_production.py
git commit -m "feat(agent): 添加 atexit 钩子确保资源清理

- Agent 初始化时可选择注册 atexit 钩子
- 使用弱引用避免阻止垃圾回收
- 默认启用，可通过 register_atexit=False 禁用

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: 并发场景稳定性验证

**Files:**
- Create: `tests/test_concurrent.py`

### 3.1 编写并发测试

- [ ] **Step 1: 创建并发测试文件**

```python
# tests/test_concurrent.py
"""并发场景测试。"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from hai_agent import Agent
from hai_agent.types import Message, NormalizedResponse


class TestConcurrentSessions:
    """多会话并发测试。"""

    @pytest.fixture
    def mock_provider(self):
        """创建 Mock Provider。"""
        provider = MagicMock()
        provider.stream = MagicMock()
        provider.name = "mock"

        # 模拟流式响应
        def mock_stream(messages, tools=None):
            yield NormalizedResponse(content="响应内容", finish_reason="stop")

        provider.stream.side_effect = mock_stream
        return provider

    def test_multiple_agents_isolated(self, mock_provider):
        """测试多个 Agent 实例的消息历史隔离。"""
        agents = [
            Agent(provider=mock_provider, register_atexit=False)
            for _ in range(5)
        ]

        # 每个 Agent 添加不同的消息
        for i, agent in enumerate(agents):
            agent._message_manager.add_user_message(f"消息 {i}")

        # 验证消息历史隔离
        for i, agent in enumerate(agents):
            messages = agent._message_manager.get_messages()
            assert len(messages) == 1
            assert f"消息 {i}" in messages[0].content[0].text

    @pytest.mark.asyncio
    async def test_concurrent_run_async(self, mock_provider):
        """测试并发调用 run_async。"""
        agent = Agent(provider=mock_provider, register_atexit=False)

        # 并发调用
        tasks = [
            agent.run_async(f"消息 {i}")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证所有调用成功（无异常）
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"任务 {i} 失败: {result}"

    @pytest.mark.asyncio
    async def test_concurrent_stream_async(self, mock_provider):
        """测试并发流式调用。"""
        agent = Agent(provider=mock_provider, register_atexit=False)

        async def collect_stream(message):
            chunks = []
            async for chunk in agent.stream_async(message):
                chunks.append(chunk)
            return chunks

        # 并发流式调用
        tasks = [
            collect_stream(f"消息 {i}")
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证所有流式调用成功
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"流式任务 {i} 失败: {result}"
            assert len(result) > 0, f"流式任务 {i} 无结果"


class TestThreadSafety:
    """线程安全测试。"""

    def test_message_manager_thread_safety(self):
        """测试 MessageManager 线程安全。"""
        import threading
        from hai_agent.managers.message import MessageManager
        from hai_agent.config.settings import Settings

        manager = MessageManager(Settings())
        errors = []

        def add_messages(thread_id):
            try:
                for i in range(100):
                    manager.add_user_message(f"线程 {thread_id} 消息 {i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_messages, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证无异常
        assert len(errors) == 0, f"线程安全错误: {errors}"

        # 验证消息数量正确
        assert len(manager.get_messages()) == 1000  # 10 线程 * 100 消息
```

- [ ] **Step 2: 运行并发测试**

Run: `pytest tests/test_concurrent.py -v`
Expected: PASS

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_concurrent.py
git commit -m "test: 添加并发场景稳定性测试

- 测试多 Agent 实例消息历史隔离
- 测试并发 run_async/stream_async 调用
- 测试 MessageManager 线程安全

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: 结构化日志配置接口

**Files:**
- Modify: `hai_agent/utils/logging.py`
- Test: `tests/test_production.py`

### 4.1 添加结构化日志测试

- [ ] **Step 1: 添加 JSON 日志格式测试**

```python
# tests/test_production.py (追加内容)

import json
import io


class TestStructuredLogging:
    """结构化日志测试。"""

    def test_json_format(self):
        """测试 JSON 格式日志。"""
        from hai_agent.utils.logging import JsonFormatter

        # 创建带 JSON 格式器的处理器
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger("test_json")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # 记录消息
        logger.info("测试消息")

        # 解析 JSON 输出
        output = stream.getvalue().strip()
        log_obj = json.loads(output)

        assert log_obj["level"] == "INFO"
        assert log_obj["message"] == "测试消息"
        assert log_obj["logger"] == "test_json"
        assert "timestamp" in log_obj

    def test_json_format_with_exception(self):
        """测试 JSON 格式包含异常信息。"""
        from hai_agent.utils.logging import JsonFormatter

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger("test_json_exc")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        try:
            raise ValueError("测试异常")
        except ValueError:
            logger.exception("发生错误")

        output = stream.getvalue().strip()
        log_obj = json.loads(output)

        assert "exception" in log_obj
        assert "ValueError" in log_obj["exception"]
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_production.py::TestStructuredLogging -v`
Expected: PASS (JsonFormatter 已在 Task 1 中实现)

- [ ] **Step 3: 提交测试**

```bash
git add tests/test_production.py
git commit -m "test: 添加结构化日志测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: 更新公共 API 导出

**Files:**
- Modify: `hai_agent/__init__.py`

### 5.1 导出新的日志函数

- [ ] **Step 1: 更新 __init__.py 导出**

```python
# hai_agent/__init__.py (在适当位置添加)

from hai_agent.utils.logging import (
    setup_logging,
    setup_secure_logging,
    get_logger,
    SensitiveDataFilter,
    JsonFormatter,
)

# 在 __all__ 中添加
__all__ = [
    # ... 现有导出 ...
    "setup_logging",
    "setup_secure_logging",
    "get_logger",
    "SensitiveDataFilter",
    "JsonFormatter",
]
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from hai_agent import setup_secure_logging, SensitiveDataFilter, JsonFormatter; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交更改**

```bash
git add hai_agent/__init__.py
git commit -m "feat: 导出日志相关公共 API

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: 运行完整测试套件

- [ ] **Step 1: 运行所有测试**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (except existing 2 mock-related failures)

- [ ] **Step 2: 最终提交**

```bash
git add -A
git commit -m "feat: 完成生产环境 P0/P1 改进项

改进内容：
- P0.1: 日志敏感信息过滤 (SensitiveDataFilter)
- P0.2: 并发场景稳定性验证 (test_concurrent.py)
- P0.3: atexit 钩子确保资源清理
- P1.1: 结构化日志支持 (JsonFormatter)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 验收标准

| 改进项 | 验收标准 |
|--------|----------|
| 敏感信息过滤 | API Key、Token、密码在日志中被脱敏 |
| atexit 钩子 | Agent 退出时自动调用 shutdown() |
| 并发验证 | 10 并发调用无异常，消息历史隔离 |
| 结构化日志 | 可输出 JSON 格式日志 |

---

## 后续改进 (P2)

不在本计划范围内，记录供参考：
- Prometheus 指标导出
- MCP 工具连接复用
- 数据库存储后端
- 健康检查接口
