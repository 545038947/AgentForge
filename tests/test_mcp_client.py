"""MCP Client 单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agentforge.mcp.client import MCPClient
from agentforge.mcp.config import MCPServerConfig
from agentforge.mcp.errors import MCPConnectionError, MCPToolCallError, MCPResourceError
from agentforge.mcp.types import MCPToolSchema, MCPResourceSchema


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_stdio_config(name: str = "test-server") -> MCPServerConfig:
    """创建一个 stdio 类型的 MCPServerConfig。"""
    return MCPServerConfig(
        name=name,
        transport="stdio",
        command="echo",
        args=[],
        env={},
    )


def _make_http_config(name: str = "test-http") -> MCPServerConfig:
    """创建一个 http 类型的 MCPServerConfig。"""
    return MCPServerConfig(
        name=name,
        transport="http",
        url="http://localhost:8080",
    )


def _make_mock_transport() -> MagicMock:
    """创建一个模拟 MCPTransport 的 Mock 对象。

    - connect / close / request / send_notification 为 AsyncMock
    - is_connected 返回 True
    - request 默认按顺序返回 initialize、tools/list、resources/list 的空结果
    """
    transport = MagicMock()
    transport.connect = AsyncMock()
    transport.close = AsyncMock()
    transport.request = AsyncMock()
    transport.send_notification = AsyncMock()
    transport.is_connected = MagicMock(return_value=True)
    # 默认 side_effect：initialize -> tools/list -> resources/list
    transport.request.side_effect = [
        {},  # initialize
        {"tools": []},  # tools/list
        {"resources": []},  # resources/list
    ]
    return transport


# ---------------------------------------------------------------------------
# 初始化状态测试
# ---------------------------------------------------------------------------

class TestMCPClientInit:
    """测试 MCPClient 初始化状态。"""

    def test_init_stores_config(self):
        """初始化时保存配置和名称。"""
        config = _make_stdio_config("my-server")
        client = MCPClient(config)
        assert client.config is config
        assert client.name == "my-server"

    def test_init_default_state(self):
        """初始化后状态应为空/未连接。"""
        client = MCPClient(_make_stdio_config())
        assert client._transport is None
        assert client._tools == []
        assert client._resources == []
        assert client._initialized is False

    def test_is_connected_false_after_init(self):
        """初始化后 is_connected 应返回 False。"""
        client = MCPClient(_make_stdio_config())
        assert client.is_connected() is False

    def test_get_tools_empty_after_init(self):
        """初始化后 get_tools 应返回空列表。"""
        client = MCPClient(_make_stdio_config())
        assert client.get_tools() == []

    def test_get_resources_empty_after_init(self):
        """初始化后 get_resources 应返回空列表。"""
        client = MCPClient(_make_stdio_config())
        assert client.get_resources() == []


# ---------------------------------------------------------------------------
# connect 测试
# ---------------------------------------------------------------------------

class TestMCPClientConnect:
    """测试 MCPClient.connect()。"""

    @pytest.mark.asyncio
    async def test_connect_stdio(self):
        """stdio transport 应创建 StdioTransport 并完成连接。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        mock_transport.connect.assert_awaited_once()
        assert client._initialized is True
        assert client._transport is mock_transport

    @pytest.mark.asyncio
    async def test_connect_http(self):
        """http transport 应创建 HTTPTransport 并完成连接。"""
        config = _make_http_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.HTTPTransport", return_value=mock_transport):
            await client.connect()

        mock_transport.connect.assert_awaited_once()
        assert client._initialized is True
        assert client._transport is mock_transport

    @pytest.mark.asyncio
    async def test_connect_unknown_transport(self):
        """未知 transport 类型应抛出 MCPConnectionError。"""
        config = MCPServerConfig(
            name="bad",
            transport="websocket",  # 不支持的类型
        )
        client = MCPClient(config)

        with pytest.raises(MCPConnectionError, match="Unknown transport"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_idempotent(self):
        """重复调用 connect 应为幂等（不重复创建 transport）。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            # 第二次调用应直接返回，不再次初始化
            await client.connect()

        # connect 只被调用一次
        assert mock_transport.connect.await_count == 1

    @pytest.mark.asyncio
    async def test_connect_sends_initialize_request(self):
        """connect 应通过 transport 发送 initialize 请求。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        # 第一次 request 调用应为 initialize
        first_call = mock_transport.request.call_args_list[0]
        assert first_call[0][0] == "initialize"
        assert first_call[0][1]["protocolVersion"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_connect_sends_initialized_notification(self):
        """connect 在 initialize 后应发送 notifications/initialized 通知。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        mock_transport.send_notification.assert_awaited_once_with(
            "notifications/initialized", {}
        )

    @pytest.mark.asyncio
    async def test_connect_loads_tools(self):
        """connect 应加载工具列表。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": [{"name": "tool1", "description": "测试工具", "inputSchema": {"type": "object"}}]},
            {"resources": []},  # resources/list
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        tools = client.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "tool1"

    @pytest.mark.asyncio
    async def test_connect_loads_resources(self):
        """connect 应加载资源列表。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            {"resources": [{"uri": "file:///test.txt", "name": "test"}]},
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        resources = client.get_resources()
        assert len(resources) == 1
        assert resources[0].uri == "file:///test.txt"

    @pytest.mark.asyncio
    async def test_connect_tools_list_failure_graceful(self):
        """tools/list 失败时应优雅降级为空列表。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            MCPConnectionError("no tools"),  # tools/list 失败
            {"resources": []},  # resources/list
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        assert client.get_tools() == []

    @pytest.mark.asyncio
    async def test_connect_resources_list_failure_graceful(self):
        """resources/list 失败时应优雅降级为空列表。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            MCPConnectionError("no resources"),  # resources/list 失败
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        assert client.get_resources() == []

    @pytest.mark.asyncio
    async def test_connect_request_order(self):
        """connect 中 request 调用顺序应为 initialize -> tools/list -> resources/list。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        call_order = []

        def record_request(method, params=None):
            call_order.append(method)
            if method == "initialize":
                return {}
            elif method == "tools/list":
                return {"tools": []}
            elif method == "resources/list":
                return {"resources": []}
            return {}

        mock_transport.request.side_effect = record_request

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()

        assert call_order == ["initialize", "tools/list", "resources/list"]


# ---------------------------------------------------------------------------
# disconnect 测试
# ---------------------------------------------------------------------------

class TestMCPClientDisconnect:
    """测试 MCPClient.disconnect()。"""

    @pytest.mark.asyncio
    async def test_disconnect_closes_transport(self):
        """disconnect 应关闭 transport 并重置状态。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            await client.disconnect()

        mock_transport.close.assert_awaited_once()
        assert client._transport is None
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_disconnect_without_transport(self):
        """没有 transport 时调用 disconnect 不应报错。"""
        client = MCPClient(_make_stdio_config())
        # 未连接就断开，不应抛异常
        await client.disconnect()
        assert client._transport is None
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_is_connected_false_after_disconnect(self):
        """disconnect 后 is_connected 应返回 False。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            await client.disconnect()

        assert client.is_connected() is False


# ---------------------------------------------------------------------------
# call_tool 测试
# ---------------------------------------------------------------------------

class TestMCPClientCallTool:
    """测试 MCPClient.call_tool()。"""

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        """未连接时调用 call_tool 应抛出 MCPConnectionError。"""
        client = MCPClient(_make_stdio_config())
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.call_tool("some_tool")

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """成功调用工具应返回 MCPToolResult。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        # 连接阶段的 request 返回 + call_tool 的 request
        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            {"resources": []},  # resources/list
            {"content": [{"type": "text", "text": "结果"}], "isError": False},
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            result = await client.call_tool("my_tool", {"key": "value"})

        assert result.content == "结果"
        assert result.isError is False

        # 验证最后一次 request 调用参数
        last_call = mock_transport.request.call_args_list[-1]
        assert last_call[0][0] == "tools/call"
        assert last_call[0][1]["name"] == "my_tool"
        assert last_call[0][1]["arguments"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_call_tool_default_arguments(self):
        """不传 arguments 时应使用空字典。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            {"resources": []},  # resources/list
            {"content": "ok"},  # call_tool
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            result = await client.call_tool("my_tool")

        last_call = mock_transport.request.call_args_list[-1]
        assert last_call[0][1]["arguments"] == {}

    @pytest.mark.asyncio
    async def test_call_tool_connection_error_wrapped(self):
        """transport 抛 MCPConnectionError 时应包装为 MCPToolCallError。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            {"resources": []},  # resources/list
            MCPConnectionError("连接断开"),  # call_tool 失败
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            with pytest.raises(MCPToolCallError, match="Tool call failed"):
                await client.call_tool("my_tool")


# ---------------------------------------------------------------------------
# read_resource 测试
# ---------------------------------------------------------------------------

class TestMCPClientReadResource:
    """测试 MCPClient.read_resource()。"""

    @pytest.mark.asyncio
    async def test_read_resource_not_connected(self):
        """未连接时调用 read_resource 应抛出 MCPConnectionError。"""
        client = MCPClient(_make_stdio_config())
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.read_resource("file:///test.txt")

    @pytest.mark.asyncio
    async def test_read_resource_success(self):
        """成功读取资源应返回 MCPResourceContent。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            {"resources": []},  # resources/list
            {"contents": [{"uri": "file:///test.txt", "text": "文件内容", "mimeType": "text/plain"}]},
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            result = await client.read_resource("file:///test.txt")

        assert result.uri == "file:///test.txt"
        assert result.text == "文件内容"
        assert result.mimeType == "text/plain"

        last_call = mock_transport.request.call_args_list[-1]
        assert last_call[0][0] == "resources/read"
        assert last_call[0][1]["uri"] == "file:///test.txt"

    @pytest.mark.asyncio
    async def test_read_resource_connection_error_wrapped(self):
        """transport 抛 MCPConnectionError 时应包装为 MCPResourceError。"""
        config = _make_stdio_config()
        client = MCPClient(config)
        mock_transport = _make_mock_transport()

        mock_transport.request.side_effect = [
            {},  # initialize
            {"tools": []},  # tools/list
            {"resources": []},  # resources/list
            MCPConnectionError("连接断开"),  # read_resource 失败
        ]

        with patch("agentforge.mcp.client.StdioTransport", return_value=mock_transport):
            await client.connect()
            with pytest.raises(MCPResourceError, match="Resource read failed"):
                await client.read_resource("file:///test.txt")


# ---------------------------------------------------------------------------
# get_tool_schema 测试
# ---------------------------------------------------------------------------

class TestMCPClientGetToolSchema:
    """测试 MCPClient.get_tool_schema()。"""

    def test_get_tool_schema_found(self):
        """找到工具时应返回对应的 MCPToolSchema。"""
        client = MCPClient(_make_stdio_config())
        tool = MCPToolSchema(name="search", description="搜索", inputSchema={"type": "object"})
        client._tools = [tool]

        result = client.get_tool_schema("search")
        assert result is tool
        assert result.name == "search"

    def test_get_tool_schema_not_found(self):
        """未找到工具时应返回 None。"""
        client = MCPClient(_make_stdio_config())
        tool = MCPToolSchema(name="search", description="搜索", inputSchema={"type": "object"})
        client._tools = [tool]

        result = client.get_tool_schema("nonexistent")
        assert result is None

    def test_get_tool_schema_empty_tools(self):
        """工具列表为空时应返回 None。"""
        client = MCPClient(_make_stdio_config())
        result = client.get_tool_schema("anything")
        assert result is None
