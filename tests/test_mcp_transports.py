"""MCP Transport 层单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agentforge.mcp.errors import MCPConnectionError
from agentforge.mcp.transports.stdio import StdioTransport
from agentforge.mcp.transports.http import HTTPTransport


# ---------------------------------------------------------------------------
# StdioTransport 测试
# ---------------------------------------------------------------------------


class TestStdioTransportInit:
    """测试 StdioTransport 初始化。"""

    def test_init_stores_command(self):
        """初始化时保存 command。"""
        transport = StdioTransport(command="node")
        assert transport.command == "node"

    def test_init_stores_args(self):
        """初始化时保存 args。"""
        transport = StdioTransport(command="node", args=["server.js", "--port", "8080"])
        assert transport.args == ["server.js", "--port", "8080"]

    def test_init_stores_env(self):
        """初始化时保存 env。"""
        env = {"API_KEY": "test-key"}
        transport = StdioTransport(command="node", env=env)
        assert transport.env == env

    def test_init_default_args(self):
        """不传 args 时默认为空列表。"""
        transport = StdioTransport(command="node")
        assert transport.args == []

    def test_init_default_env(self):
        """不传 env 时默认为空字典。"""
        transport = StdioTransport(command="node")
        assert transport.env == {}


class TestStdioTransportConnectionState:
    """测试 StdioTransport 连接状态。"""

    def test_not_connected_after_init(self):
        """初始化后 is_connected 应返回 False。"""
        transport = StdioTransport(command="node")
        assert transport.is_connected() is False

    def test_internal_state_after_init(self):
        """初始化后内部状态应为空。"""
        transport = StdioTransport(command="node")
        assert transport._process is None
        assert transport._reader is None
        assert transport._writer is None
        assert transport._pid is None

    @pytest.mark.asyncio
    async def test_close_without_process(self):
        """无进程时调用 close 不应报错。"""
        transport = StdioTransport(command="node")
        # 未连接就关闭，不应抛异常
        await transport.close()
        assert transport._process is None
        assert transport._pid is None

    @pytest.mark.asyncio
    async def test_request_not_connected(self):
        """未连接时调用 request 应抛出 MCPConnectionError。"""
        transport = StdioTransport(command="node")
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await transport.request("tools/list")

    @pytest.mark.asyncio
    async def test_send_notification_not_connected(self):
        """未连接时调用 send_notification 应抛出 MCPConnectionError。"""
        transport = StdioTransport(command="node")
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await transport.send_notification("notifications/initialized")


# ---------------------------------------------------------------------------
# HTTPTransport 测试
# ---------------------------------------------------------------------------


class TestHTTPTransportInit:
    """测试 HTTPTransport 初始化。"""

    def test_init_stores_url(self):
        """初始化时保存 url（去除尾部斜杠）。"""
        transport = HTTPTransport(url="http://localhost:8080/")
        assert transport.url == "http://localhost:8080"

    def test_init_stores_url_without_trailing_slash(self):
        """url 无尾部斜杠时保持不变。"""
        transport = HTTPTransport(url="http://localhost:8080")
        assert transport.url == "http://localhost:8080"

    def test_init_stores_api_key(self):
        """初始化时保存 api_key。"""
        transport = HTTPTransport(url="http://localhost:8080", api_key="my-key")
        assert transport.api_key == "my-key"

    def test_init_default_api_key(self):
        """不传 api_key 时默认为 None。"""
        transport = HTTPTransport(url="http://localhost:8080")
        assert transport.api_key is None

    def test_init_stores_timeout(self):
        """初始化时保存 timeout。"""
        transport = HTTPTransport(url="http://localhost:8080", timeout=60.0)
        assert transport.timeout == 60.0

    def test_init_default_timeout(self):
        """不传 timeout 时默认为 30.0。"""
        transport = HTTPTransport(url="http://localhost:8080")
        assert transport.timeout == 30.0

    def test_init_stores_custom_headers(self):
        """初始化时保存自定义请求头。"""
        headers = {"X-Custom": "value"}
        transport = HTTPTransport(url="http://localhost:8080", headers=headers)
        assert transport.custom_headers == headers

    def test_init_default_headers(self):
        """不传 headers 时默认为空字典。"""
        transport = HTTPTransport(url="http://localhost:8080")
        assert transport.custom_headers == {}


class TestHTTPTransportConnectionState:
    """测试 HTTPTransport 连接状态。"""

    def test_not_connected_after_init(self):
        """初始化后 is_connected 应返回 False。"""
        transport = HTTPTransport(url="http://localhost:8080")
        assert transport.is_connected() is False

    def test_client_none_after_init(self):
        """初始化后 _client 应为 None。"""
        transport = HTTPTransport(url="http://localhost:8080")
        assert transport._client is None

    @pytest.mark.asyncio
    async def test_request_not_connected(self):
        """未连接时调用 request 应抛出 MCPConnectionError。"""
        transport = HTTPTransport(url="http://localhost:8080")
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await transport.request("tools/list")

    @pytest.mark.asyncio
    async def test_send_notification_not_connected(self):
        """未连接时调用 send_notification 应抛出 MCPConnectionError。"""
        transport = HTTPTransport(url="http://localhost:8080")
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await transport.send_notification("notifications/initialized")


class TestHTTPTransportConnect:
    """测试 HTTPTransport.connect()。"""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        """connect 应创建 httpx.AsyncClient。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_client = MagicMock()
        mock_client.is_closed = False

        with patch("agentforge.mcp.transports.http.httpx.AsyncClient", return_value=mock_client):
            await transport.connect()

        assert transport._client is mock_client
        assert transport.is_connected() is True

    @pytest.mark.asyncio
    async def test_connect_with_api_key(self):
        """有 api_key 时 connect 应在请求头中添加 Authorization。"""
        transport = HTTPTransport(url="http://localhost:8080", api_key="secret")

        mock_client = MagicMock()
        mock_client.is_closed = False

        with patch("agentforge.mcp.transports.http.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await transport.connect()

        # 检查传给 AsyncClient 的 headers 包含 Authorization
        call_kwargs = mock_cls.call_args[1]
        headers = call_kwargs["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer secret"

    @pytest.mark.asyncio
    async def test_connect_without_api_key(self):
        """无 api_key 时 connect 不应添加 Authorization 请求头。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_client = MagicMock()
        mock_client.is_closed = False

        with patch("agentforge.mcp.transports.http.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await transport.connect()

        call_kwargs = mock_cls.call_args[1]
        headers = call_kwargs["headers"]
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_connect_merges_custom_headers(self):
        """connect 应合并自定义请求头。"""
        custom = {"X-App-Id": "my-app"}
        transport = HTTPTransport(url="http://localhost:8080", headers=custom)

        mock_client = MagicMock()
        mock_client.is_closed = False

        with patch("agentforge.mcp.transports.http.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await transport.connect()

        call_kwargs = mock_cls.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["X-App-Id"] == "my-app"
        # 默认请求头也应存在
        assert "Content-Type" in headers

    @pytest.mark.asyncio
    async def test_connect_sets_base_url(self):
        """connect 应将 url 作为 base_url 传给 AsyncClient。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_client = MagicMock()
        mock_client.is_closed = False

        with patch("agentforge.mcp.transports.http.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await transport.connect()

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["base_url"] == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_connect_sets_timeout(self):
        """connect 应将 timeout 传给 AsyncClient。"""
        transport = HTTPTransport(url="http://localhost:8080", timeout=60.0)

        mock_client = MagicMock()
        mock_client.is_closed = False

        with patch("agentforge.mcp.transports.http.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await transport.connect()

        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["timeout"] == 60.0


class TestHTTPTransportRequest:
    """测试 HTTPTransport.request()。"""

    @pytest.mark.asyncio
    async def test_request_success(self):
        """成功请求应返回 result 字段内容。"""
        transport = HTTPTransport(url="http://localhost:8080")

        # 模拟已连接的 client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []},
        }

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)

        transport._client = mock_client

        result = await transport.request("tools/list")
        assert result == {"tools": []}

        # 验证 post 调用参数
        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["method"] == "tools/list"
        assert call_kwargs["json"]["jsonrpc"] == "2.0"

    @pytest.mark.asyncio
    async def test_request_increments_id(self):
        """每次请求 id 应递增。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)

        transport._client = mock_client

        await transport.request("method1")
        await transport.request("method2")

        calls = mock_client.post.call_args_list
        assert calls[0][1]["json"]["id"] == 1
        assert calls[1][1]["json"]["id"] == 2

    @pytest.mark.asyncio
    async def test_request_http_error(self):
        """HTTP 非 200 状态应抛出 MCPConnectionError。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)

        transport._client = mock_client

        with pytest.raises(MCPConnectionError, match="HTTP Error 500"):
            await transport.request("tools/list")

    @pytest.mark.asyncio
    async def test_request_jsonrpc_error(self):
        """JSON-RPC 错误响应应抛出 MCPConnectionError。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        }

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)

        transport._client = mock_client

        with pytest.raises(MCPConnectionError, match="MCP Error -32600"):
            await transport.request("bad_method")

    @pytest.mark.asyncio
    async def test_request_httpx_error(self):
        """httpx 网络错误应抛出 MCPConnectionError。"""
        import httpx

        transport = HTTPTransport(url="http://localhost:8080")

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("连接被拒绝"))

        transport._client = mock_client

        with pytest.raises(MCPConnectionError, match="HTTP request failed"):
            await transport.request("tools/list")

    @pytest.mark.asyncio
    async def test_request_default_params(self):
        """不传 params 时应使用空字典。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.post = AsyncMock(return_value=mock_response)

        transport._client = mock_client

        await transport.request("tools/list")

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["params"] == {}


class TestHTTPTransportClose:
    """测试 HTTPTransport.close()。"""

    @pytest.mark.asyncio
    async def test_close_cleans_client(self):
        """close 应关闭 client 并置为 None。"""
        transport = HTTPTransport(url="http://localhost:8080")

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()

        transport._client = mock_client

        await transport.close()

        mock_client.aclose.assert_awaited_once()
        assert transport._client is None
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        """无 client 时调用 close 不应报错。"""
        transport = HTTPTransport(url="http://localhost:8080")
        # 未连接就关闭，不应抛异常
        await transport.close()
        assert transport._client is None
