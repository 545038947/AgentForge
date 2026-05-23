"""MCP Manager 单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agentforge.mcp.manager import MCPManager
from agentforge.mcp.config import MCPConfig, MCPServerConfig
from agentforge.mcp.errors import MCPConfigError, MCPConnectionError
from agentforge.mcp.types import MCPToolSchema


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_server_config(
    name: str = "test-server",
    enabled: bool = True,
    transport: str = "stdio",
) -> MCPServerConfig:
    """创建一个 MCPServerConfig 实例。"""
    return MCPServerConfig(
        name=name,
        transport=transport,
        enabled=enabled,
        command="echo" if transport == "stdio" else None,
        url="http://localhost:8080" if transport == "http" else None,
    )


def _make_tool_schema(name: str = "search", description: str = "搜索工具") -> MCPToolSchema:
    """创建一个 MCPToolSchema 实例。"""
    return MCPToolSchema(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
    )


def _make_mock_client(
    server_name: str = "test-server",
    tool_schemas: list = None,
    connected: bool = True,
) -> MagicMock:
    """创建一个模拟 MCPClient 的 Mock 对象。

    - connect / disconnect 为 AsyncMock
    - get_tools 返回指定的 tool_schemas
    - is_connected 返回 connected
    - call_tool 为 AsyncMock，返回带 content 属性的结果
    """
    client = MagicMock()
    client.name = server_name
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_tools = MagicMock(return_value=tool_schemas or [])
    client.is_connected = MagicMock(return_value=connected)

    # call_tool 返回带 content 属性的 Mock 对象
    call_result = MagicMock()
    call_result.content = "工具执行结果"
    client.call_tool = AsyncMock(return_value=call_result)

    return client


# ---------------------------------------------------------------------------
# 初始化状态测试
# ---------------------------------------------------------------------------

class TestMCPManagerInit:
    """测试 MCPManager 初始化状态。"""

    def test_init_empty_clients(self):
        """初始化后 _clients 应为空字典。"""
        manager = MCPManager()
        assert manager._clients == {}

    def test_init_empty_tools(self):
        """初始化后 _tools 应为空字典。"""
        manager = MCPManager()
        assert manager._tools == {}

    def test_init_not_initialized(self):
        """初始化后 is_initialized 应返回 False。"""
        manager = MCPManager()
        assert manager.is_initialized() is False

    def test_get_all_tools_empty(self):
        """初始化后 get_all_tools 应返回空列表。"""
        manager = MCPManager()
        assert manager.get_all_tools() == []

    def test_get_server_names_empty(self):
        """初始化后 get_server_names 应返回空列表。"""
        manager = MCPManager()
        assert manager.get_server_names() == []


# ---------------------------------------------------------------------------
# initialize 测试
# ---------------------------------------------------------------------------

class TestMCPManagerInitialize:
    """测试 MCPManager.initialize()。"""

    @pytest.mark.asyncio
    async def test_initialize_single_server(self):
        """初始化单个服务器应创建 client 并注册工具。"""
        manager = MCPManager()
        tool_schema = _make_tool_schema("search")
        mock_client = _make_mock_client("my-server", [tool_schema])

        config = MCPConfig(servers=[_make_server_config("my-server")])

        with patch("agentforge.mcp.manager.MCPClient", return_value=mock_client):
            await manager.initialize(config)

        # 验证 client 已创建并连接
        mock_client.connect.assert_awaited_once()
        assert "my-server" in manager._clients
        assert manager.is_initialized() is True

        # 验证工具已注册（全名格式：server.tool）
        assert "my-server.search" in manager._tools
        assert len(manager._tools) == 1

    @pytest.mark.asyncio
    async def test_initialize_multiple_servers(self):
        """初始化多个服务器应创建多个 client 并注册所有工具。"""
        manager = MCPManager()

        tool_a = _make_tool_schema("tool_a", "工具A")
        tool_b = _make_tool_schema("tool_b", "工具B")
        mock_client_a = _make_mock_client("server-a", [tool_a])
        mock_client_b = _make_mock_client("server-b", [tool_b])

        config = MCPConfig(servers=[
            _make_server_config("server-a"),
            _make_server_config("server-b"),
        ])

        with patch("agentforge.mcp.manager.MCPClient", side_effect=[mock_client_a, mock_client_b]):
            await manager.initialize(config)

        assert len(manager._clients) == 2
        assert "server-a" in manager._clients
        assert "server-b" in manager._clients
        assert "server-a.tool_a" in manager._tools
        assert "server-b.tool_b" in manager._tools
        assert manager.is_initialized() is True

    @pytest.mark.asyncio
    async def test_initialize_disabled_server_skipped(self):
        """禁用的服务器应被跳过，不创建 client。"""
        manager = MCPManager()
        mock_client = _make_mock_client("enabled-server", [_make_tool_schema("tool1")])

        config = MCPConfig(servers=[
            _make_server_config("disabled-server", enabled=False),
            _make_server_config("enabled-server", enabled=True),
        ])

        with patch("agentforge.mcp.manager.MCPClient", return_value=mock_client):
            await manager.initialize(config)

        # 只有 enabled-server 创建了 client
        assert "disabled-server" not in manager._clients
        assert "enabled-server" in manager._clients
        assert len(manager._clients) == 1

    @pytest.mark.asyncio
    async def test_initialize_connection_failure_tolerated(self):
        """连接失败的服务器应被跳过，不影响其他服务器。"""
        manager = MCPManager()

        # 第一个 client 连接失败
        fail_client = _make_mock_client("fail-server")
        fail_client.connect = AsyncMock(side_effect=MCPConnectionError("连接失败"))

        # 第二个 client 连接成功
        ok_client = _make_mock_client("ok-server", [_make_tool_schema("tool1")])

        config = MCPConfig(servers=[
            _make_server_config("fail-server"),
            _make_server_config("ok-server"),
        ])

        with patch("agentforge.mcp.manager.MCPClient", side_effect=[fail_client, ok_client]):
            await manager.initialize(config)

        # 失败的 server 不在 clients 中
        assert "fail-server" not in manager._clients
        # 成功的 server 正常注册
        assert "ok-server" in manager._clients
        assert "ok-server.tool1" in manager._tools
        # 即使有失败，initialized 仍为 True
        assert manager.is_initialized() is True

    @pytest.mark.asyncio
    async def test_initialize_all_servers_fail_still_initialized(self):
        """所有服务器都连接失败时，initialized 仍为 True。"""
        manager = MCPManager()

        fail_client = _make_mock_client("fail-server")
        fail_client.connect = AsyncMock(side_effect=MCPConnectionError("连接失败"))

        config = MCPConfig(servers=[_make_server_config("fail-server")])

        with patch("agentforge.mcp.manager.MCPClient", return_value=fail_client):
            await manager.initialize(config)

        assert manager.is_initialized() is True
        assert len(manager._clients) == 0
        assert len(manager._tools) == 0

    @pytest.mark.asyncio
    async def test_initialize_no_servers(self):
        """空配置初始化应正常完成。"""
        manager = MCPManager()
        config = MCPConfig(servers=[])

        await manager.initialize(config)

        assert manager.is_initialized() is True
        assert len(manager._clients) == 0
        assert len(manager._tools) == 0

    @pytest.mark.asyncio
    async def test_initialize_multiple_tools_per_server(self):
        """单个服务器提供多个工具时应全部注册。"""
        manager = MCPManager()

        tool1 = _make_tool_schema("search", "搜索")
        tool2 = _make_tool_schema("calculate", "计算")
        mock_client = _make_mock_client("multi-tool-server", [tool1, tool2])

        config = MCPConfig(servers=[_make_server_config("multi-tool-server")])

        with patch("agentforge.mcp.manager.MCPClient", return_value=mock_client):
            await manager.initialize(config)

        assert "multi-tool-server.search" in manager._tools
        assert "multi-tool-server.calculate" in manager._tools
        assert len(manager._tools) == 2


# ---------------------------------------------------------------------------
# shutdown 测试
# ---------------------------------------------------------------------------

class TestMCPManagerShutdown:
    """测试 MCPManager.shutdown()。"""

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all_clients(self):
        """shutdown 应断开所有 client。"""
        manager = MCPManager()

        mock_client_a = _make_mock_client("server-a")
        mock_client_b = _make_mock_client("server-b")

        # 手动设置内部状态模拟已初始化
        manager._clients = {"server-a": mock_client_a, "server-b": mock_client_b}
        manager._tools = {"server-a.tool1": MagicMock(), "server-b.tool2": MagicMock()}
        manager._initialized = True

        await manager.shutdown()

        mock_client_a.disconnect.assert_awaited_once()
        mock_client_b.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_clears_state(self):
        """shutdown 应清空 clients、tools 和 initialized 标志。"""
        manager = MCPManager()

        mock_client = _make_mock_client("server-a")
        manager._clients = {"server-a": mock_client}
        manager._tools = {"server-a.tool1": MagicMock()}
        manager._initialized = True

        await manager.shutdown()

        assert manager._clients == {}
        assert manager._tools == {}
        assert manager.is_initialized() is False

    @pytest.mark.asyncio
    async def test_shutdown_empty_manager(self):
        """空 manager 调用 shutdown 不应报错。"""
        manager = MCPManager()
        await manager.shutdown()

        assert manager._clients == {}
        assert manager._tools == {}
        assert manager.is_initialized() is False

    @pytest.mark.asyncio
    async def test_shutdown_tolerates_disconnect_error(self):
        """client 断开连接抛异常时不应影响其他 client。"""
        manager = MCPManager()

        fail_client = _make_mock_client("fail-server")
        fail_client.disconnect = AsyncMock(side_effect=RuntimeError("断开失败"))

        ok_client = _make_mock_client("ok-server")
        ok_client.disconnect = AsyncMock()

        manager._clients = {"fail-server": fail_client, "ok-server": ok_client}
        manager._tools = {}
        manager._initialized = True

        # 不应抛异常
        await manager.shutdown()

        # 两个 client 都尝试了断开
        fail_client.disconnect.assert_awaited_once()
        ok_client.disconnect.assert_awaited_once()

        # 状态仍被清空
        assert manager._clients == {}
        assert manager._tools == {}
        assert manager.is_initialized() is False


# ---------------------------------------------------------------------------
# get_tool 测试
# ---------------------------------------------------------------------------

class TestMCPManagerGetTool:
    """测试 MCPManager.get_tool()。"""

    def _setup_manager_with_tools(self) -> MCPManager:
        """创建一个已注册工具的 manager。"""
        manager = MCPManager()

        # 模拟两个 server 各有一个工具
        tool_schema_a = _make_tool_schema("search", "搜索")
        tool_schema_b = _make_tool_schema("calculate", "计算")

        mock_client_a = _make_mock_client("server-a")
        mock_client_b = _make_mock_client("server-b")

        # 直接构造 MCPTool 对象
        from agentforge.mcp.tool import MCPTool
        tool_a = MCPTool(mock_client_a, tool_schema_a)
        tool_b = MCPTool(mock_client_b, tool_schema_b)

        manager._tools = {
            "server-a.search": tool_a,
            "server-b.calculate": tool_b,
        }

        return manager

    def test_get_tool_by_full_name(self):
        """使用完整名称（server.tool）应找到工具。"""
        manager = self._setup_manager_with_tools()
        tool = manager.get_tool("server-a.search")
        assert tool is not None
        assert tool.name == "search"

    def test_get_tool_by_short_name(self):
        """使用短名应找到工具。"""
        manager = self._setup_manager_with_tools()
        tool = manager.get_tool("search")
        assert tool is not None
        assert tool.name == "search"

    def test_get_tool_by_short_name_calculate(self):
        """使用短名 calculate 应找到对应工具。"""
        manager = self._setup_manager_with_tools()
        tool = manager.get_tool("calculate")
        assert tool is not None
        assert tool.name == "calculate"

    def test_get_tool_not_found(self):
        """查找不存在的工具应返回 None。"""
        manager = self._setup_manager_with_tools()
        tool = manager.get_tool("nonexistent")
        assert tool is None

    def test_get_tool_empty_tools(self):
        """工具列表为空时查找应返回 None。"""
        manager = MCPManager()
        tool = manager.get_tool("anything")
        assert tool is None

    def test_get_tool_full_name_priority(self):
        """完整名称匹配应优先于短名匹配。"""
        manager = MCPManager()

        # 构造两个 server 有同名工具的场景
        tool_schema = _make_tool_schema("search", "搜索")
        mock_client = _make_mock_client("server-a")
        from agentforge.mcp.tool import MCPTool
        tool = MCPTool(mock_client, tool_schema)

        manager._tools = {"server-a.search": tool}

        # 完整名称应精确匹配
        result = manager.get_tool("server-a.search")
        assert result is tool


# ---------------------------------------------------------------------------
# call_tool 测试
# ---------------------------------------------------------------------------

class TestMCPManagerCallTool:
    """测试 MCPManager.call_tool()。"""

    @pytest.mark.asyncio
    async def test_call_tool_not_found_raises_error(self):
        """调用不存在的工具应抛出 MCPConfigError。"""
        manager = MCPManager()
        with pytest.raises(MCPConfigError, match="Tool not found"):
            await manager.call_tool("nonexistent_tool")

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """成功调用工具应返回结果内容。"""
        manager = MCPManager()

        tool_schema = _make_tool_schema("search", "搜索")
        mock_client = _make_mock_client("server-a")
        from agentforge.mcp.tool import MCPTool
        tool = MCPTool(mock_client, tool_schema)

        manager._tools = {"server-a.search": tool}

        result = await manager.call_tool("search", {"query": "test"})

        # 验证 client.call_tool 被调用
        mock_client.call_tool.assert_awaited_once()
        assert result == "工具执行结果"

    @pytest.mark.asyncio
    async def test_call_tool_by_full_name(self):
        """使用完整名称调用工具应成功。"""
        manager = MCPManager()

        tool_schema = _make_tool_schema("search", "搜索")
        mock_client = _make_mock_client("server-a")
        from agentforge.mcp.tool import MCPTool
        tool = MCPTool(mock_client, tool_schema)

        manager._tools = {"server-a.search": tool}

        result = await manager.call_tool("server-a.search")
        assert result == "工具执行结果"

    @pytest.mark.asyncio
    async def test_call_tool_default_arguments(self):
        """不传 arguments 时应使用空字典。"""
        manager = MCPManager()

        tool_schema = _make_tool_schema("search", "搜索")
        mock_client = _make_mock_client("server-a")
        from agentforge.mcp.tool import MCPTool
        tool = MCPTool(mock_client, tool_schema)

        manager._tools = {"server-a.search": tool}

        await manager.call_tool("search")

        # 验证 call_tool 被调用时 arguments 为空字典
        call_args = mock_client.call_tool.call_args
        # call_tool(tool.name, arguments or {})
        assert call_args[0][1] == {}


# ---------------------------------------------------------------------------
# get_tools_for_server 测试
# ---------------------------------------------------------------------------

class TestMCPManagerGetToolsForServer:
    """测试 MCPManager.get_tools_for_server()。"""

    def test_get_tools_for_existing_server(self):
        """获取已注册服务器的工具应返回对应列表。"""
        manager = MCPManager()

        tool_schema_a = _make_tool_schema("search", "搜索")
        tool_schema_b = _make_tool_schema("calculate", "计算")
        mock_client = _make_mock_client("server-a")

        from agentforge.mcp.tool import MCPTool
        tool_a = MCPTool(mock_client, tool_schema_a)
        tool_b = MCPTool(mock_client, tool_schema_b)

        manager._tools = {
            "server-a.search": tool_a,
            "server-a.calculate": tool_b,
        }

        tools = manager.get_tools_for_server("server-a")
        assert len(tools) == 2
        assert tool_a in tools
        assert tool_b in tools

    def test_get_tools_for_nonexistent_server(self):
        """获取不存在服务器的工具应返回空列表。"""
        manager = MCPManager()
        tools = manager.get_tools_for_server("nonexistent")
        assert tools == []

    def test_get_tools_filters_by_server(self):
        """应只返回指定服务器的工具，不包含其他服务器的。"""
        manager = MCPManager()

        tool_schema_a = _make_tool_schema("search", "搜索")
        tool_schema_b = _make_tool_schema("search", "搜索")
        mock_client_a = _make_mock_client("server-a")
        mock_client_b = _make_mock_client("server-b")

        from agentforge.mcp.tool import MCPTool
        tool_a = MCPTool(mock_client_a, tool_schema_a)
        tool_b = MCPTool(mock_client_b, tool_schema_b)

        manager._tools = {
            "server-a.search": tool_a,
            "server-b.search": tool_b,
        }

        tools = manager.get_tools_for_server("server-a")
        assert len(tools) == 1
        assert tool_a in tools
        assert tool_b not in tools


# ---------------------------------------------------------------------------
# is_server_connected 测试
# ---------------------------------------------------------------------------

class TestMCPManagerIsServerConnected:
    """测试 MCPManager.is_server_connected()。"""

    def test_connected_server(self):
        """已连接的服务器应返回 True。"""
        manager = MCPManager()
        mock_client = _make_mock_client("server-a", connected=True)
        manager._clients = {"server-a": mock_client}

        assert manager.is_server_connected("server-a") is True

    def test_disconnected_server(self):
        """client 存在但未连接应返回 False。"""
        manager = MCPManager()
        mock_client = _make_mock_client("server-a", connected=False)
        manager._clients = {"server-a": mock_client}

        assert manager.is_server_connected("server-a") is False

    def test_nonexistent_server(self):
        """不存在的服务器应返回 False。"""
        manager = MCPManager()
        assert manager.is_server_connected("nonexistent") is False

    def test_empty_clients(self):
        """clients 为空时应返回 False。"""
        manager = MCPManager()
        assert manager.is_server_connected("any") is False


# ---------------------------------------------------------------------------
# get_tool_schemas_for_llm 测试
# ---------------------------------------------------------------------------

class TestMCPManagerGetToolSchemasForLLM:
    """测试 MCPManager.get_tool_schemas_for_llm()。"""

    def test_returns_schemas_for_all_tools(self):
        """应返回所有工具的 schema 列表。"""
        manager = MCPManager()

        tool_schema_a = _make_tool_schema("search", "搜索")
        tool_schema_b = _make_tool_schema("calculate", "计算")
        mock_client = _make_mock_client("server-a")

        from agentforge.mcp.tool import MCPTool
        tool_a = MCPTool(mock_client, tool_schema_a)
        tool_b = MCPTool(mock_client, tool_schema_b)

        manager._tools = {
            "server-a.search": tool_a,
            "server-a.calculate": tool_b,
        }

        schemas = manager.get_tool_schemas_for_llm()
        assert len(schemas) == 2

        # 验证 schema 格式
        names = [s["name"] for s in schemas]
        assert "search" in names
        assert "calculate" in names

        # 验证每个 schema 包含必要字段
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema

    def test_empty_tools_returns_empty_list(self):
        """工具列表为空时应返回空列表。"""
        manager = MCPManager()
        schemas = manager.get_tool_schemas_for_llm()
        assert schemas == []


# ---------------------------------------------------------------------------
# get_server_names 测试
# ---------------------------------------------------------------------------

class TestMCPManagerGetServerNames:
    """测试 MCPManager.get_server_names()。"""

    def test_returns_server_names(self):
        """应返回所有已注册的服务器名称。"""
        manager = MCPManager()
        manager._clients = {
            "server-a": MagicMock(),
            "server-b": MagicMock(),
        }

        names = manager.get_server_names()
        assert "server-a" in names
        assert "server-b" in names
        assert len(names) == 2

    def test_empty_returns_empty_list(self):
        """没有服务器时应返回空列表。"""
        manager = MCPManager()
        names = manager.get_server_names()
        assert names == []


# ---------------------------------------------------------------------------
# get_all_tools 测试
# ---------------------------------------------------------------------------

class TestMCPManagerGetAllTools:
    """测试 MCPManager.get_all_tools()。"""

    def test_returns_all_tools(self):
        """应返回所有已注册的工具。"""
        manager = MCPManager()

        tool_schema = _make_tool_schema("search", "搜索")
        mock_client = _make_mock_client("server-a")
        from agentforge.mcp.tool import MCPTool
        tool = MCPTool(mock_client, tool_schema)

        manager._tools = {"server-a.search": tool}

        tools = manager.get_all_tools()
        assert len(tools) == 1
        assert tool in tools

    def test_empty_returns_empty_list(self):
        """工具列表为空时应返回空列表。"""
        manager = MCPManager()
        tools = manager.get_all_tools()
        assert tools == []
