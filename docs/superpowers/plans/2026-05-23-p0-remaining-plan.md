# AgentForge P0 剩余项实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成剩余 3 项 P0 改进，使框架满足生产环境最低要求

**Architecture:**
- MCP 测试：为 `hai_agent/mcp/` 11 个文件编写单元测试，覆盖类型、配置、客户端、工具包装、管理器
- Mock 降级修复：将所有 Provider 的静默 Mock 响应替换为 `ProviderError` 抛出
- 裸异常修复：将 79 处 `except Exception` 缩窄为具体异常类型，并为静默吞异常的块添加日志

**Tech Stack:** Python 3.9+, pytest, pytest-asyncio, unittest.mock

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `tests/test_mcp_types.py` | MCP 类型测试 | 创建 |
| `tests/test_mcp_config.py` | MCP 配置测试 | 创建 |
| `tests/test_mcp_client.py` | MCP 客户端测试 | 创建 |
| `tests/test_mcp_tool.py` | MCP 工具包装测试 | 创建 |
| `tests/test_mcp_manager.py` | MCP 管理器测试 | 创建 |
| `tests/test_mcp_transports.py` | MCP 传输层测试 | 创建 |
| `hai_agent/providers/builtins/openai.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/anthropic.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/deepseek.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/qwen.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/moonshot.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/chinese/deepseek.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/chinese/moonshot.py` | 移除 Mock 响应 | 修改 |
| `hai_agent/providers/builtins/chinese/qwen.py` | 移除 Mock 响应 | 修改 |
| 27 个源文件 | 缩窄 except Exception | 修改 |

---

## Task 1: MCP 类型测试

**Files:**
- Create: `tests/test_mcp_types.py`

- [ ] **Step 1: 创建 MCP 类型测试文件**

```python
# tests/test_mcp_types.py
"""MCP 类型定义测试。"""

import pytest

from hai_agent.mcp.types import (
    MCPToolSchema,
    MCPResourceSchema,
    MCPToolResult,
    MCPResourceContent,
)
from hai_agent.mcp.errors import (
    MCPError,
    MCPConnectionError,
    MCPToolCallError,
    MCPResourceError,
    MCPConfigError,
)
from hai_agent.types.errors import AgentForgeError


class TestMCPToolSchema:
    """MCPToolSchema 测试。"""

    def test_from_dict_full(self):
        data = {
            "name": "search",
            "description": "搜索工具",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
        schema = MCPToolSchema.from_dict(data)
        assert schema.name == "search"
        assert schema.description == "搜索工具"
        assert schema.inputSchema == data["inputSchema"]

    def test_from_dict_minimal(self):
        data = {"name": "tool1"}
        schema = MCPToolSchema.from_dict(data)
        assert schema.name == "tool1"
        assert schema.description == ""
        assert schema.inputSchema == {"type": "object"}

    def test_from_dict_missing_description(self):
        data = {"name": "tool2", "inputSchema": {"type": "object"}}
        schema = MCPToolSchema.from_dict(data)
        assert schema.description == ""


class TestMCPResourceSchema:
    """MCPResourceSchema 测试。"""

    def test_from_dict_full(self):
        data = {
            "uri": "file:///test.txt",
            "name": "测试文件",
            "description": "测试描述",
            "mimeType": "text/plain",
        }
        schema = MCPResourceSchema.from_dict(data)
        assert schema.uri == "file:///test.txt"
        assert schema.name == "测试文件"
        assert schema.description == "测试描述"
        assert schema.mimeType == "text/plain"

    def test_from_dict_name_fallback_to_uri(self):
        data = {"uri": "file:///test.txt"}
        schema = MCPResourceSchema.from_dict(data)
        assert schema.name == "file:///test.txt"

    def test_from_dict_optional_fields(self):
        data = {"uri": "file:///a.txt", "name": "a"}
        schema = MCPResourceSchema.from_dict(data)
        assert schema.description is None
        assert schema.mimeType is None


class TestMCPToolResult:
    """MCPToolResult 测试。"""

    def test_from_dict_string_content(self):
        data = {"content": "结果文本", "isError": False}
        result = MCPToolResult.from_dict(data)
        assert result.content == "结果文本"
        assert result.isError is False

    def test_from_dict_list_content(self):
        data = {
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "text", "text": "第二段"},
            ],
            "isError": True,
        }
        result = MCPToolResult.from_dict(data)
        assert result.content == "第一段\n第二段"
        assert result.isError is True

    def test_from_dict_default_is_error(self):
        data = {"content": "ok"}
        result = MCPToolResult.from_dict(data)
        assert result.isError is False

    def test_from_dict_empty_content(self):
        data = {}
        result = MCPToolResult.from_dict(data)
        assert result.content == ""
        assert result.isError is False


class TestMCPResourceContent:
    """MCPResourceContent 测试。"""

    def test_from_dict_normal(self):
        data = {
            "contents": [
                {"uri": "file:///a.txt", "text": "内容", "mimeType": "text/plain"}
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.uri == "file:///a.txt"
        assert content.text == "内容"
        assert content.mimeType == "text/plain"

    def test_from_dict_bytes_text(self):
        data = {
            "contents": [
                {"uri": "file:///b.bin", "text": b"binary data"}
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.text == "binary data"

    def test_from_dict_empty_contents(self):
        data = {"contents": []}
        content = MCPResourceContent.from_dict(data)
        assert content.uri == ""
        assert content.text == ""

    def test_from_dict_no_contents_key(self):
        data = {}
        content = MCPResourceContent.from_dict(data)
        assert content.uri == ""
        assert content.text == ""


class TestMCPErrorHierarchy:
    """MCP 错误层次结构测试。"""

    def test_mcp_error_is_agentforge_error(self):
        assert issubclass(MCPError, AgentForgeError)

    def test_connection_error_hierarchy(self):
        assert issubclass(MCPConnectionError, MCPError)
        assert issubclass(MCPConnectionError, AgentForgeError)

    def test_tool_call_error_hierarchy(self):
        assert issubclass(MCPToolCallError, MCPError)

    def test_resource_error_hierarchy(self):
        assert issubclass(MCPResourceError, MCPError)

    def test_config_error_hierarchy(self):
        assert issubclass(MCPConfigError, MCPError)

    def test_errors_are_distinct(self):
        errors = [MCPConnectionError, MCPToolCallError, MCPResourceError, MCPConfigError]
        for i, e1 in enumerate(errors):
            for j, e2 in enumerate(errors):
                if i != j:
                    assert not issubclass(e1, e2)
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_mcp_types.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_types.py
git commit -m "test(mcp): 添加 MCP 类型和错误层次结构测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: MCP 配置测试

**Files:**
- Create: `tests/test_mcp_config.py`

- [ ] **Step 1: 创建 MCP 配置测试文件**

```python
# tests/test_mcp_config.py
"""MCP 配置测试。"""

import os
import tempfile

import pytest

from hai_agent.mcp.config import MCPConfig, MCPServerConfig
from hai_agent.mcp.errors import MCPConfigError


class TestMCPServerConfig:
    """MCPServerConfig 测试。"""

    def test_from_dict_stdio(self):
        data = {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-server"],
            "env": {"API_KEY": "test"},
        }
        config = MCPServerConfig.from_dict("test-server", data)
        assert config.name == "test-server"
        assert config.transport == "stdio"
        assert config.command == "npx"
        assert config.args == ["-y", "@anthropic/mcp-server"]
        assert config.env == {"API_KEY": "test"}
        assert config.enabled is True

    def test_from_dict_http(self):
        data = {
            "transport": "http",
            "url": "http://localhost:8080/mcp",
        }
        config = MCPServerConfig.from_dict("http-server", data)
        assert config.transport == "http"
        assert config.url == "http://localhost:8080/mcp"

    def test_from_dict_disabled(self):
        data = {
            "transport": "stdio",
            "command": "test",
            "enabled": False,
        }
        config = MCPServerConfig.from_dict("disabled", data)
        assert config.enabled is False

    def test_from_dict_env_var_in_api_key(self):
        os.environ["TEST_MCP_KEY"] = "secret-key-123"
        try:
            data = {
                "transport": "http",
                "url": "http://localhost:8080",
                "api_key": "${TEST_MCP_KEY}",
            }
            config = MCPServerConfig.from_dict("env-server", data)
            assert config.api_key == "secret-key-123"
        finally:
            del os.environ["TEST_MCP_KEY"]

    def test_validate_stdio_missing_command(self):
        config = MCPServerConfig(
            name="bad", transport="stdio", enabled=True,
            command=None, args=[], env={},
            url=None, api_key=None, headers={},
        )
        with pytest.raises(MCPConfigError):
            config.validate()

    def test_validate_http_missing_url(self):
        config = MCPServerConfig(
            name="bad", transport="http", enabled=True,
            command=None, args=[], env={},
            url=None, api_key=None, headers={},
        )
        with pytest.raises(MCPConfigError):
            config.validate()

    def test_validate_unknown_transport(self):
        config = MCPServerConfig(
            name="bad", transport="websocket", enabled=True,
            command=None, args=[], env={},
            url=None, api_key=None, headers={},
        )
        with pytest.raises(MCPConfigError):
            config.validate()

    def test_validate_valid_stdio(self):
        config = MCPServerConfig(
            name="ok", transport="stdio", enabled=True,
            command="npx", args=[], env={},
            url=None, api_key=None, headers={},
        )
        config.validate()  # 不应抛异常


class TestMCPConfig:
    """MCPConfig 测试。"""

    def test_from_dict_multiple_servers(self):
        data = {
            "servers": {
                "server1": {
                    "transport": "stdio",
                    "command": "cmd1",
                },
                "server2": {
                    "transport": "http",
                    "url": "http://localhost:8080",
                },
            }
        }
        config = MCPConfig.from_dict(data)
        assert len(config.servers) == 2
        names = [s.name for s in config.servers]
        assert "server1" in names
        assert "server2" in names

    def test_from_dict_invalid_server(self):
        data = {
            "servers": {
                "bad": {
                    "transport": "stdio",
                    # 缺少 command
                }
            }
        }
        with pytest.raises(MCPConfigError):
            MCPConfig.from_dict(data)

    def test_from_yaml_file_not_found(self):
        with pytest.raises(MCPConfigError):
            MCPConfig.from_yaml("/nonexistent/path.yaml")

    def test_from_yaml_valid(self):
        yaml_content = """
servers:
  test-server:
    transport: stdio
    command: npx
    args:
      - -y
      - "@test/mcp-server"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            try:
                config = MCPConfig.from_yaml(f.name)
                assert len(config.servers) == 1
                assert config.servers[0].name == "test-server"
            finally:
                os.unlink(f.name)
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_mcp_config.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_config.py
git commit -m "test(mcp): 添加 MCP 配置测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: MCP 客户端测试

**Files:**
- Create: `tests/test_mcp_client.py`

- [ ] **Step 1: 创建 MCP 客户端测试文件**

```python
# tests/test_mcp_client.py
"""MCP Client 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.config import MCPServerConfig
from hai_agent.mcp.errors import MCPConnectionError, MCPToolCallError, MCPResourceError
from hai_agent.mcp.types import MCPToolSchema, MCPToolResult, MCPResourceContent


def _make_stdio_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="test-server",
        transport="stdio",
        enabled=True,
        command="test-cmd",
        args=[],
        env={},
        url=None,
        api_key=None,
        headers={},
    )


class TestMCPClientInit:
    """MCPClient 初始化测试。"""

    def test_init_stores_config(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        assert client.config is config
        assert client.name == "test-server"
        assert client.is_connected() is False

    def test_init_no_tools_or_resources(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        assert client.get_tools() == []
        assert client.get_resources() == []


class TestMCPClientConnect:
    """MCPClient 连接测试。"""

    @pytest.mark.asyncio
    async def test_connect_creates_stdio_transport(self):
        config = _make_stdio_config()
        client = MCPClient(config)

        mock_transport = AsyncMock()
        mock_transport.is_connected.return_value = True
        mock_transport.request.side_effect = [
            {"protocolVersion": "2024-11-05", "capabilities": {}},
            {"tools": [{"name": "t1", "description": "d1", "inputSchema": {"type": "object"}}]},
            {"resources": []},
        ]

        with patch("hai_agent.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        assert client.is_connected() is True
        assert len(client.get_tools()) == 1

    @pytest.mark.asyncio
    async def test_connect_creates_http_transport(self):
        config = MCPServerConfig(
            name="http-server", transport="http", enabled=True,
            command=None, args=[], env={},
            url="http://localhost:8080", api_key=None, headers={},
        )
        client = MCPClient(config)

        mock_transport = AsyncMock()
        mock_transport.is_connected.return_value = True
        mock_transport.request.side_effect = [
            {"protocolVersion": "2024-11-05", "capabilities": {}},
            {"tools": []},
            {"resources": []},
        ]

        with patch("hai_agent.mcp.client.HTTPTransport", return_value=mock_transport):
            await client.connect()

        assert client.is_connected() is True

    @pytest.mark.asyncio
    async def test_connect_unknown_transport(self):
        config = MCPServerConfig(
            name="bad", transport="websocket", enabled=True,
            command=None, args=[], env={},
            url=None, api_key=None, headers={},
        )
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_idempotent(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        client._initialized = True
        client._transport = AsyncMock()
        client._transport.is_connected.return_value = True
        # 第二次调用不应报错
        await client.connect()


class TestMCPClientDisconnect:
    """MCPClient 断开测试。"""

    @pytest.mark.asyncio
    async def test_disconnect_closes_transport(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = AsyncMock()
        client._transport = mock_transport
        client._initialized = True

        await client.disconnect()

        mock_transport.close.assert_called_once()
        assert client._transport is None
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_disconnect_no_transport(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        await client.disconnect()  # 不应抛异常


class TestMCPClientCallTool:
    """MCPClient 工具调用测试。"""

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.call_tool("search", {"q": "test"})

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = AsyncMock()
        mock_transport.is_connected.return_value = True
        mock_transport.request.return_value = {
            "content": "搜索结果",
            "isError": False,
        }
        client._transport = mock_transport
        client._initialized = True

        result = await client.call_tool("search", {"q": "test"})
        assert isinstance(result, MCPToolResult)
        assert result.content == "搜索结果"
        assert result.isError is False

    @pytest.mark.asyncio
    async def test_call_tool_connection_error_wrapped(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = AsyncMock()
        mock_transport.is_connected.return_value = True
        mock_transport.request.side_effect = MCPConnectionError("lost")
        client._transport = mock_transport
        client._initialized = True

        with pytest.raises(MCPToolCallError):
            await client.call_tool("search", {})


class TestMCPClientReadResource:
    """MCPClient 资源读取测试。"""

    @pytest.mark.asyncio
    async def test_read_resource_not_connected(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.read_resource("file:///test.txt")

    @pytest.mark.asyncio
    async def test_read_resource_success(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = AsyncMock()
        mock_transport.is_connected.return_value = True
        mock_transport.request.return_value = {
            "contents": [{"uri": "file:///test.txt", "text": "文件内容"}]
        }
        client._transport = mock_transport
        client._initialized = True

        result = await client.read_resource("file:///test.txt")
        assert isinstance(result, MCPResourceContent)
        assert result.text == "文件内容"

    @pytest.mark.asyncio
    async def test_read_resource_connection_error_wrapped(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = AsyncMock()
        mock_transport.is_connected.return_value = True
        mock_transport.request.side_effect = MCPConnectionError("lost")
        client._transport = mock_transport
        client._initialized = True

        with pytest.raises(MCPResourceError):
            await client.read_resource("file:///test.txt")


class TestMCPClientGetToolSchema:
    """MCPClient 获取工具 Schema 测试。"""

    def test_get_tool_schema_found(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        client._tools = [
            MCPToolSchema(name="search", description="搜索", inputSchema={"type": "object"}),
        ]
        schema = client.get_tool_schema("search")
        assert schema is not None
        assert schema.name == "search"

    def test_get_tool_schema_not_found(self):
        config = _make_stdio_config()
        client = MCPClient(config)
        assert client.get_tool_schema("nonexistent") is None
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_mcp_client.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_client.py
git commit -m "test(mcp): 添加 MCP Client 测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: MCP 工具包装测试

**Files:**
- Create: `tests/test_mcp_tool.py`

- [ ] **Step 1: 创建 MCP 工具包装测试文件**

```python
# tests/test_mcp_tool.py
"""MCP Tool 包装器测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hai_agent.mcp.tool import MCPTool
from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.types import MCPToolSchema
from hai_agent.types import ToolResult


def _make_mcp_tool() -> MCPTool:
    mock_client = MagicMock(spec=MCPClient)
    mock_client.name = "test-server"
    mock_client.config = MagicMock()
    schema = MCPToolSchema(
        name="search",
        description="搜索工具",
        inputSchema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )
    return MCPTool(client=mock_client, schema=schema)


class TestMCPToolProperties:
    """MCPTool 属性测试。"""

    def test_name(self):
        tool = _make_mcp_tool()
        assert tool.name == "search"

    def test_description(self):
        tool = _make_mcp_tool()
        assert tool.description == "搜索工具"

    def test_parameters(self):
        tool = _make_mcp_tool()
        assert tool.parameters["type"] == "object"
        assert "q" in tool.parameters["properties"]


class TestMCPToolSchema:
    """MCPTool get_schema 测试。"""

    def test_get_schema(self):
        tool = _make_mcp_tool()
        schema = tool.get_schema()
        assert schema["name"] == "search"
        assert schema["description"] == "搜索工具"
        assert schema["input_schema"] == tool.parameters


class TestMCPToolValidateParameters:
    """MCPTool validate_parameters 测试。"""

    def test_valid_params(self):
        tool = _make_mcp_tool()
        assert tool.validate_parameters({"q": "test"}) is True

    def test_missing_required(self):
        tool = _make_mcp_tool()
        assert tool.validate_parameters({}) is False

    def test_extra_params_ok(self):
        tool = _make_mcp_tool()
        assert tool.validate_parameters({"q": "test", "limit": 10}) is True


class TestMCPToolExecute:
    """MCPTool execute 测试。"""

    def test_execute_timeout(self):
        tool = _make_mcp_tool()
        # Mock _execute_with_new_connection 使其永远不返回
        async def hang(**kwargs):
            import asyncio
            await asyncio.sleep(100)

        with patch.object(tool, "_execute_with_new_connection", hang):
            # 设置极短超时
            tool._timeout = 0.1
            result = tool.execute("call-1", q="test")
            assert result.is_error is True
            assert "超时" in result.content

    def test_execute_success(self):
        tool = _make_mcp_tool()

        async def mock_exec(**kwargs):
            return "搜索结果"

        with patch.object(tool, "_execute_with_new_connection", mock_exec):
            result = tool.execute("call-1", q="test")
            assert isinstance(result, ToolResult)
            assert result.is_error is False
            assert result.content == "搜索结果"

    def test_execute_error(self):
        tool = _make_mcp_tool()

        async def mock_exec(**kwargs):
            raise RuntimeError("连接失败")

        with patch.object(tool, "_execute_with_new_connection", mock_exec):
            result = tool.execute("call-1", q="test")
            assert result.is_error is True
            assert "连接失败" in result.content


class TestMCPToolRepr:
    """MCPTool __repr__ 测试。"""

    def test_repr(self):
        tool = _make_mcp_tool()
        assert "search" in repr(tool)
        assert "test-server" in repr(tool)
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_mcp_tool.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_tool.py
git commit -m "test(mcp): 添加 MCP Tool 包装器测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: MCP 管理器测试

**Files:**
- Create: `tests/test_mcp_manager.py`

- [ ] **Step 1: 创建 MCP 管理器测试文件**

```python
# tests/test_mcp_manager.py
"""MCP Manager 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hai_agent.mcp.manager import MCPManager
from hai_agent.mcp.config import MCPConfig, MCPServerConfig
from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.tool import MCPTool
from hai_agent.mcp.types import MCPToolSchema
from hai_agent.mcp.errors import MCPConfigError, MCPConnectionError


def _make_config_with_servers(n: int) -> MCPConfig:
    servers = []
    for i in range(n):
        servers.append(MCPServerConfig(
            name=f"server-{i}",
            transport="stdio",
            enabled=True,
            command=f"cmd-{i}",
            args=[],
            env={},
            url=None,
            api_key=None,
            headers={},
        ))
    return MCPConfig(servers=servers)


class TestMCPManagerInit:
    """MCPManager 初始化测试。"""

    def test_init_state(self):
        manager = MCPManager()
        assert manager.is_initialized() is False
        assert manager.get_all_tools() == []
        assert manager.get_server_names() == []


class TestMCPManagerInitialize:
    """MCPManager 初始化连接测试。"""

    @pytest.mark.asyncio
    async def test_initialize_single_server(self):
        manager = MCPManager()
        config = _make_config_with_servers(1)

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.name = "server-0"
        mock_client.get_tools.return_value = [
            MCPToolSchema(name="tool1", description="t1", inputSchema={"type": "object"}),
        ]
        mock_client.connect = AsyncMock()
        mock_client.is_connected.return_value = True

        with patch("hai_agent.mcp.manager.MCPClient", return_value=mock_client):
            await manager.initialize(config)

        assert manager.is_initialized() is True
        assert "server-0" in manager.get_server_names()
        assert len(manager.get_all_tools()) == 1

    @pytest.mark.asyncio
    async def test_initialize_disabled_server_skipped(self):
        manager = MCPManager()
        config = MCPConfig(servers=[
            MCPServerConfig(
                name="disabled", transport="stdio", enabled=False,
                command="cmd", args=[], env={},
                url=None, api_key=None, headers={},
            ),
        ])

        await manager.initialize(config)
        assert manager.is_initialized() is True
        assert len(manager.get_server_names()) == 0

    @pytest.mark.asyncio
    async def test_initialize_connection_failure_tolerated(self):
        manager = MCPManager()
        config = _make_config_with_servers(1)

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.connect.side_effect = MCPConnectionError("failed")

        with patch("hai_agent.mcp.manager.MCPClient", return_value=mock_client):
            await manager.initialize(config)

        # 应继续初始化，不抛异常
        assert manager.is_initialized() is True


class TestMCPManagerShutdown:
    """MCPManager 关闭测试。"""

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all(self):
        manager = MCPManager()
        mock_client = AsyncMock(spec=MCPClient)
        mock_client.disconnect = AsyncMock()
        manager._clients = {"s1": mock_client}
        manager._tools = {"s1.t1": MagicMock()}
        manager._initialized = True

        await manager.shutdown()

        mock_client.disconnect.assert_called_once()
        assert len(manager._clients) == 0
        assert len(manager._tools) == 0
        assert manager.is_initialized() is False


class TestMCPManagerGetTool:
    """MCPManager 工具查找测试。"""

    def test_get_tool_by_full_name(self):
        manager = MCPManager()
        mock_tool = MagicMock()
        manager._tools = {"server.search": mock_tool}

        assert manager.get_tool("server.search") is mock_tool

    def test_get_tool_by_short_name(self):
        manager = MCPManager()
        mock_tool = MagicMock()
        manager._tools = {"server.search": mock_tool}

        assert manager.get_tool("search") is mock_tool

    def test_get_tool_not_found(self):
        manager = MCPManager()
        assert manager.get_tool("nonexistent") is None


class TestMCPManagerCallTool:
    """MCPManager 工具调用测试。"""

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self):
        manager = MCPManager()
        with pytest.raises(MCPConfigError):
            await manager.call_tool("nonexistent", {})


class TestMCPManagerServerInfo:
    """MCPManager 服务信息测试。"""

    def test_get_tools_for_server(self):
        manager = MCPManager()
        tool1 = MagicMock()
        tool2 = MagicMock()
        manager._tools = {
            "s1.tool1": tool1,
            "s2.tool2": tool2,
        }
        tools = manager.get_tools_for_server("s1")
        assert tool1 in tools
        assert tool2 not in tools

    def test_is_server_connected(self):
        manager = MCPManager()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        manager._clients = {"s1": mock_client}

        assert manager.is_server_connected("s1") is True
        assert manager.is_server_connected("s2") is False

    def test_get_tool_schemas_for_llm(self):
        manager = MCPManager()
        mock_tool = MagicMock()
        mock_tool.get_schema.return_value = {"name": "t", "description": "d", "input_schema": {}}
        manager._tools = {"s.t": mock_tool}

        schemas = manager.get_tool_schemas_for_llm()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "t"
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_mcp_manager.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_manager.py
git commit -m "test(mcp): 添加 MCP Manager 测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: MCP 传输层测试

**Files:**
- Create: `tests/test_mcp_transports.py`

- [ ] **Step 1: 创建 MCP 传输层测试文件**

```python
# tests/test_mcp_transports.py
"""MCP Transport 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hai_agent.mcp.transports.stdio import StdioTransport
from hai_agent.mcp.transports.http import HTTPTransport
from hai_agent.mcp.errors import MCPConnectionError


class TestStdioTransportInit:
    """StdioTransport 初始化测试。"""

    def test_init_stores_params(self):
        transport = StdioTransport(command="npx", args=["-y", "@test/server"])
        assert transport._command == "npx"
        assert transport._args == ["-y", "@test/server"]

    def test_not_connected_initially(self):
        transport = StdioTransport(command="test")
        assert transport.is_connected() is False


class TestStdioTransportClose:
    """StdioTransport 关闭测试。"""

    @pytest.mark.asyncio
    async def test_close_no_process(self):
        transport = StdioTransport(command="test")
        # 没有进程时关闭不应报错
        await transport.close()


class TestHTTPTransportInit:
    """HTTPTransport 初始化测试。"""

    def test_init_stores_params(self):
        transport = HTTPTransport(
            url="http://localhost:8080/mcp",
            api_key="test-key",
            timeout=60.0,
        )
        assert transport._url == "http://localhost:8080/mcp"
        assert transport._api_key == "test-key"
        assert transport._timeout == 60.0

    def test_not_connected_initially(self):
        transport = HTTPTransport(url="http://localhost:8080/mcp")
        assert transport.is_connected() is False


class TestHTTPTransportConnect:
    """HTTPTransport 连接测试。"""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        transport = HTTPTransport(url="http://localhost:8080/mcp", api_key="key123")

        mock_http_client = AsyncMock()
        mock_http_client.is_closed = False

        with patch("hai_agent.mcp.transports.http.httpx.AsyncClient", return_value=mock_http_client):
            await transport.connect()

        assert transport.is_connected() is True


class TestHTTPTransportRequest:
    """HTTPTransport 请求测试。"""

    @pytest.mark.asyncio
    async def test_request_not_connected(self):
        transport = HTTPTransport(url="http://localhost:8080/mcp")
        with pytest.raises(MCPConnectionError):
            await transport.request("tools/list", {})

    @pytest.mark.asyncio
    async def test_request_success(self):
        transport = HTTPTransport(url="http://localhost:8080/mcp")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []},
        }

        mock_http_client = AsyncMock()
        mock_http_client.is_closed = False
        mock_http_client.post.return_value = mock_response

        transport._client = mock_http_client

        result = await transport.request("tools/list", {})
        assert "tools" in result


class TestHTTPTransportClose:
    """HTTPTransport 关闭测试。"""

    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        transport = HTTPTransport(url="http://localhost:8080/mcp")
        mock_client = AsyncMock()
        transport._client = mock_client

        await transport.close()

        mock_client.aclose.assert_called_once()
        assert transport._client is None
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_mcp_transports.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_mcp_transports.py
git commit -m "test(mcp): 添加 MCP Transport 测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: 修复 Mock 响应静默降级

**Files:**
- Modify: `hai_agent/providers/builtins/openai.py`
- Modify: `hai_agent/providers/builtins/anthropic.py`
- Modify: `hai_agent/providers/builtins/deepseek.py`
- Modify: `hai_agent/providers/builtins/qwen.py`
- Modify: `hai_agent/providers/builtins/moonshot.py`
- Modify: `hai_agent/providers/builtins/chinese/deepseek.py`
- Modify: `hai_agent/providers/builtins/chinese/moonshot.py`
- Modify: `hai_agent/providers/builtins/chinese/qwen.py`

### 7.1 修复 Builtins Provider（client is None 时抛异常）

- [ ] **Step 1: 修改 openai.py — 将 Mock 响应替换为 ProviderError**

在 `openai.py` 的 `_do_stream` 方法中，找到 `if self._client is None:` 分支，将返回 Mock 响应替换为抛出 `ProviderError`：

```python
# 替换前（约 line 101-155）:
if self._client is None:
    logger.warning("OpenAI SDK 未安装或 API 密钥未配置，使用模拟响应")
    ...  # 大段 Mock 响应代码
    yield MockResponse(...)
    return

# 替换后:
if self._client is None:
    raise ProviderError(
        "OpenAI SDK 未安装或 API 密钥未配置，无法调用 API。"
        "请安装 openai 包并设置 API 密钥。"
    )
```

同时删除 `MockFunction`, `MockToolCall`, `MockMessage`, `MockChoice`, `MockUsage`, `MockResponse` 这 6 个 Mock 数据类定义。

- [ ] **Step 2: 修改 anthropic.py — 将 Mock 响应替换为 ProviderError**

```python
# 替换前（约 line 114-122）:
if self._client is None:
    logger.warning("Anthropic SDK 未安装或 API 密钥未配置，使用模拟响应")
    yield {
        "content": "这是一个模拟响应（SDK 未安装或密钥未配置）。",
        ...
    }
    return

# 替换后:
if self._client is None:
    raise ProviderError(
        "Anthropic SDK 未安装或 API 密钥未配置，无法调用 API。"
        "请安装 anthropic 包并设置 API 密钥。"
    )
```

- [ ] **Step 3: 修改 deepseek.py, qwen.py, moonshot.py — 同样模式**

每个文件中 `if self._client is None:` 分支，替换为：

```python
if self._client is None:
    raise ProviderError(
        f"{Provider名称} SDK 未安装或 API 密钥未配置，无法调用 API。"
    )
```

- [ ] **Step 4: 修改 chinese/ 子目录的三个 Provider**

这三个 Provider（`chinese/deepseek.py`, `chinese/moonshot.py`, `chinese/qwen.py`）的 `_do_stream` 和 `stream` 方法始终返回 Mock 响应。修复方案：

将 `_mock_response()` 方法和 `_do_stream` 中的硬编码响应替换为抛出 `ProviderError`，并在 `_do_stream` 中添加真实的 API 调用逻辑（参照 `builtins/` 目录中对应 Provider 的实现）。

如果这些 Provider 尚未实现真实 API 调用，则至少应：

```python
def _mock_response(self):
    raise ProviderError(
        f"{self.name} Provider 尚未实现真实 API 调用。"
        f"请使用 hai_agent.providers.builtins.{self.name} 代替。"
    )
```

- [ ] **Step 5: 运行现有测试确认无破坏**

Run: `pytest tests/ -v --tb=short -k "not demo"`
Expected: 之前因 Mock 响应通过的测试可能需要更新（改为 expect ProviderError）

- [ ] **Step 6: 提交**

```bash
git add hai_agent/providers/builtins/
git commit -m "fix(providers): 移除 Mock 静默降级，未配置时抛出 ProviderError

- OpenAI/Anthropic/DeepSeek/Qwen/Moonshot: client is None 时抛 ProviderError
- chinese/ 子目录 Provider: 标记为未实现，抛 ProviderError
- 删除 Mock 数据类定义

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: 缩窄裸 except Exception（高优先级块）

**Files:**
- Modify: `hai_agent/agent.py`
- Modify: `hai_agent/core/execution.py`
- Modify: `hai_agent/mcp/tool.py`
- Modify: `hai_agent/mcp/manager.py`
- Modify: `hai_agent/mcp/transports/stdio.py`
- Modify: `hai_agent/mcp/transports/http.py`

此任务只修复**最高风险**的裸 `except Exception` 块（主循环、翻译器模式、静默吞异常）。其余块在 Task 9 中处理。

### 8.1 修复 agent.py 中的关键块

- [ ] **Step 1: 修复流式调用失败（line ~1134, ~1347）**

```python
# 替换前:
except Exception as e:
    logger.error(f"流式调用失败: {e}")
    yield NormalizedResponse(...)

# 替换后:
except (ProviderError, OSError, ConnectionError, TimeoutError) as e:
    logger.error(f"流式调用失败: {e}")
    yield NormalizedResponse(...)
```

需要在文件顶部确保导入 `ProviderError`。

- [ ] **Step 2: 修复 atexit 回调（line ~1496）**

```python
# 替换前:
except Exception:
    pass

# 替换后:
except (OSError, RuntimeError):
    pass
```

- [ ] **Step 3: 修复速率限制头解析（line ~1533）**

```python
# 替换前:
except Exception:
    pass

# 替换后:
except (KeyError, TypeError, ValueError):
    pass
```

### 8.2 修复 execution.py 中的主循环

- [ ] **Step 4: 修复 Agent 主循环异常处理器（line ~295）**

```python
# 替换前:
except Exception as e:
    classified = classify_api_error(e, ...)

# 替换后:
except (ProviderError, OSError, ConnectionError, TimeoutError, RuntimeError) as e:
    classified = classify_api_error(e, ...)
```

### 8.3 修复 MCP 模块

- [ ] **Step 5: 修复 mcp/tool.py（line ~84, ~111）**

```python
# line ~84 (线程内):
except (OSError, RuntimeError, TimeoutError, ConnectionError) as e:
    result_error = e

# line ~111 (execute 外层):
except (OSError, RuntimeError, TimeoutError) as e:
    return ToolResult(tool_call_id=tool_call_id, content=str(e), is_error=True)
```

- [ ] **Step 6: 修复 mcp/manager.py（line ~75）**

```python
# 替换前:
except Exception:
    pass

# 替换后:
except (OSError, RuntimeError, MCPConnectionError):
    pass
```

- [ ] **Step 7: 修复 mcp/transports/stdio.py 的静默吞异常块**

```python
# line ~163 (close writer):
except (OSError, ConnectionError, BrokenPipeError, RuntimeError):
    pass

# line ~174 (process terminate fallback):
except (OSError, ProcessLookupError, subprocess.SubprocessError):
    ...

# line ~201 (process alive check):
except (OSError, PermissionError):
    return False

# line ~227 (force kill):
except (OSError, subprocess.SubprocessError, PermissionError):
    pass
```

- [ ] **Step 8: 修复 mcp/transports/http.py（line ~132）**

```python
# 替换前:
except Exception as e:
    pass

# 替换后:
except (OSError, ConnectionError, TimeoutError) as e:
    logger.debug(f"MCP 通知发送失败: {e}")
```

- [ ] **Step 9: 运行测试**

Run: `pytest tests/ -v --tb=short`
Expected: PASS

- [ ] **Step 10: 提交**

```bash
git add hai_agent/agent.py hai_agent/core/execution.py hai_agent/mcp/
git commit -m "fix: 缩窄高优先级裸 except Exception 块

- agent.py: 流式调用、atexit、速率限制头解析
- execution.py: Agent 主循环异常处理器
- mcp/tool.py: 工具执行异常
- mcp/manager.py: 客户端断开
- mcp/transports/: 进程管理和 HTTP 通知

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: 缩窄裸 except Exception（中低优先级块）

**Files:**
- Modify: `hai_agent/managers/message.py`
- Modify: `hai_agent/memory/manager.py`
- Modify: `hai_agent/memory/memory_store.py`
- Modify: `hai_agent/memory/extractor.py`
- Modify: `hai_agent/memory/builtins/file_based.py`
- Modify: `hai_agent/tools/executor.py`
- Modify: `hai_agent/tools/toolsets.py`
- Modify: `hai_agent/tools/base.py`
- Modify: `hai_agent/tools/checkpoint.py`
- Modify: `hai_agent/tools/builtins/*.py`
- Modify: `hai_agent/providers/client_factory.py`
- Modify: `hai_agent/providers/custom.py`
- Modify: `hai_agent/providers/registry.py`
- Modify: `hai_agent/providers/profile.py`
- Modify: `hai_agent/providers/transports/chat_completions.py`
- Modify: `hai_agent/providers/transports/anthropic.py`
- Modify: `hai_agent/providers/builtins/*.py`
- Modify: `hai_agent/session/builtins/file_based.py`
- Modify: `hai_agent/events/emitter.py`
- Modify: `hai_agent/hooks/__init__.py`
- Modify: `hai_agent/skills/loader.py`
- Modify: `hai_agent/delegation/manager.py`
- Modify: `hai_agent/core/async_utils.py`
- Modify: `hai_agent/core/stream_accumulator.py`
- Modify: `hai_agent/types/errors.py`
- Modify: `hai_agent/profiles/registry.py`

此任务处理剩余约 60 处裸 `except Exception` 块。修改原则：

1. **I/O 操作**：`except Exception` → `except (OSError, IOError, ...)` 加上具体的序列化错误
2. **JSON 操作**：加上 `json.JSONDecodeError`（Python 3.5+ 为 `ValueError` 子类）
3. **导入/加载**：加上 `ImportError, AttributeError, SyntaxError`
4. **网络操作**：加上 `ConnectionError, TimeoutError, httpx.HTTPError` 等
5. **静默吞异常的 `pass` 块**：添加 `logger.debug()` 日志
6. **翻译器模式**（catch-then-reraise-as-domain-error）：缩窄到预期的异常类型

- [ ] **Step 1: 批量修改所有文件**

对每个文件逐一修改，遵循上述原则。由于修改量大，建议按模块分批提交。

- [ ] **Step 2: 运行完整测试套件**

Run: `pytest tests/ -v --tb=short`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add hai_agent/
git commit -m "fix: 缩窄剩余裸 except Exception 块

- I/O 操作: OSError/IOError/PermissionError
- JSON: json.JSONDecodeError
- 导入: ImportError/AttributeError/SyntaxError
- 网络: ConnectionError/TimeoutError
- 静默吞异常: 添加 logger.debug 日志

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: 运行完整测试套件并验证

- [ ] **Step 1: 运行所有测试**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: 验证 MCP 测试覆盖**

Run: `pytest tests/test_mcp_*.py -v --tb=short`
Expected: 所有 MCP 测试通过

- [ ] **Step 3: 验证 Mock 降级已修复**

Run: `python -c "from hai_agent.providers.builtins.openai import OpenAIProvider; p = OpenAIProvider(model='test'); list(p.stream([]))"`
Expected: 抛出 ProviderError 而非返回 Mock 响应

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: 完成 P0 剩余项 — MCP 测试、Mock 降级修复、裸异常缩窄

P0 改进项全部完成：
- MCP 模块测试覆盖（6 个测试文件，50+ 测试用例）
- Mock 响应静默降级修复（8 个 Provider 改为抛 ProviderError）
- 裸 except Exception 缩窄（79 处 → 具体异常类型）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 验收标准

| 改进项 | 验收标准 |
|--------|----------|
| MCP 测试覆盖 | 6 个测试文件，覆盖 types/config/client/tool/manager/transports |
| Mock 降级修复 | Provider 未配置时抛 ProviderError，不再返回假响应 |
| 裸异常缩窄 | 高优先级块使用具体异常类型，静默块添加日志 |

---

## 后续改进 (P1)

不在本计划范围内，记录供参考：
- CheckpointManager 测试覆盖
- MemoryManager/MemoryStore shutdown 方法
- Agent 并发安全（线程锁）
- async 上下文 threading.Lock → asyncio.Lock
- MCP 连接复用
- Prometheus 指标导出
