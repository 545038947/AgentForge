"""MCP 连接池测试。"""

import time
from unittest.mock import MagicMock, patch

from agentforge.mcp.pool import MCPConnectionPool


class TestMCPConnectionPoolInit:
    def test_init_defaults(self):
        pool = MCPConnectionPool()
        assert pool._max_idle_seconds == 300.0
        assert pool._max_connections == 10
        assert not pool._started

    def test_init_custom(self):
        pool = MCPConnectionPool(max_idle_seconds=60, max_connections=5)
        assert pool._max_idle_seconds == 60
        assert pool._max_connections == 5


class TestMCPConnectionPoolLifecycle:
    def test_start_creates_loop(self):
        pool = MCPConnectionPool()
        pool.start()
        try:
            assert pool._started
            assert pool._loop is not None
        finally:
            pool.shutdown()

    def test_start_idempotent(self):
        pool = MCPConnectionPool()
        pool.start()
        try:
            pool.start()  # 第二次不应创建新线程
        finally:
            pool.shutdown()

    def test_shutdown_closes_loop(self):
        pool = MCPConnectionPool()
        pool.start()
        pool.shutdown()
        assert pool._closed

    def test_shutdown_idempotent(self):
        pool = MCPConnectionPool()
        pool.start()
        pool.shutdown()
        pool.shutdown()  # 不应抛异常


class TestMCPConnectionPoolConfigKey:
    def test_config_key_deterministic(self):
        config = MagicMock()
        config.name = "test"
        config.command = "python"
        config.args = ["server.py"]
        config.url = None
        key1 = MCPConnectionPool._config_key(config)
        key2 = MCPConnectionPool._config_key(config)
        assert key1 == key2

    def test_config_key_different_args(self):
        config1 = MagicMock()
        config1.name = "test"
        config1.command = "python"
        config1.args = ["server1.py"]
        config1.url = None
        config2 = MagicMock()
        config2.name = "test"
        config2.command = "python"
        config2.args = ["server2.py"]
        config2.url = None
        key1 = MCPConnectionPool._config_key(config1)
        key2 = MCPConnectionPool._config_key(config2)
        assert key1 != key2

    def test_config_key_http_transport(self):
        config = MagicMock()
        config.name = "remote"
        config.command = None
        config.args = []
        config.url = "http://localhost:8080"
        key = MCPConnectionPool._config_key(config)
        assert "http:" in key


class TestMCPConnectionPoolMocked:
    """使用 Mock 测试连接池逻辑。"""

    def test_get_or_create_reuses_existing(self):
        pool = MCPConnectionPool()
        config = MagicMock()
        config.name = "test"
        config.command = "python"
        config.args = ["test.py"]
        config.url = None

        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        pool._started = True
        pool._loop = MagicMock()

        key = pool._config_key(config)
        pool._clients[key] = mock_client
        pool._last_used[key] = time.monotonic()

        client = pool.get_or_create(config)
        assert client is mock_client
        pool.shutdown()

    def test_get_or_create_new_with_mock_loop(self):
        pool = MCPConnectionPool()
        config = MagicMock()
        config.name = "new"
        config.command = "python"
        config.args = ["test.py"]
        config.url = None

        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        with patch("agentforge.mcp.pool.MCPClient", return_value=mock_client):
            mock_future = MagicMock()
            mock_future.result.return_value = None
            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                pool._started = True
                pool._loop = MagicMock()
                client = pool.get_or_create(config)
                assert client is mock_client

        pool.shutdown()

    def test_call_tool_delegates_to_pool(self):
        pool = MCPConnectionPool()
        config = MagicMock()
        config.name = "test"
        config.command = "python"
        config.args = ["test.py"]
        config.url = None

        mock_result = MagicMock()
        mock_result.content = "工具执行结果"
        mock_result.isError = False

        with patch.object(pool, "get_or_create") as mock_get:
            mock_client = MagicMock()
            mock_get.return_value = mock_client

            mock_future = MagicMock()
            mock_future.result.return_value = mock_result

            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
                pool._started = True
                pool._loop = MagicMock()
                result = pool.call_tool(config, "search", {"q": "test"})
                assert result == "工具执行结果"

        pool.shutdown()
