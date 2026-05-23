"""MCP 配置模块单元测试。"""

import os
import tempfile

import pytest

from hai_agent.mcp.config import MCPConfig, MCPServerConfig
from hai_agent.mcp.errors import MCPConfigError


class TestMCPServerConfigFromDict:
    """测试 MCPServerConfig.from_dict。"""

    def test_stdio_config(self):
        """测试 stdio 类型服务器配置。"""
        data = {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {"NODE_ENV": "production"},
        }
        config = MCPServerConfig.from_dict("fs-server", data)
        assert config.name == "fs-server"
        assert config.transport == "stdio"
        assert config.enabled is True
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert config.env == {"NODE_ENV": "production"}

    def test_http_config(self):
        """测试 http 类型服务器配置。"""
        data = {
            "transport": "http",
            "url": "http://localhost:8080/mcp",
            "api_key": "sk-test-key",
            "headers": {"X-Custom": "value"},
        }
        config = MCPServerConfig.from_dict("remote-server", data)
        assert config.name == "remote-server"
        assert config.transport == "http"
        assert config.url == "http://localhost:8080/mcp"
        assert config.api_key == "sk-test-key"
        assert config.headers == {"X-Custom": "value"}

    def test_disabled_server(self):
        """测试 disabled 服务器。"""
        data = {
            "transport": "stdio",
            "command": "echo",
            "enabled": False,
        }
        config = MCPServerConfig.from_dict("disabled-server", data)
        assert config.enabled is False

    def test_default_transport_is_stdio(self):
        """测试默认 transport 为 stdio。"""
        data = {"command": "echo"}
        config = MCPServerConfig.from_dict("default-transport", data)
        assert config.transport == "stdio"

    def test_default_enabled_is_true(self):
        """测试默认 enabled 为 True。"""
        data = {"command": "echo"}
        config = MCPServerConfig.from_dict("default-enabled", data)
        assert config.enabled is True

    def test_env_var_api_key(self, monkeypatch):
        """测试 ${ENV_VAR} 格式的 api_key 解析。"""
        monkeypatch.setenv("MY_MCP_API_KEY", "resolved-secret-key")
        data = {
            "transport": "http",
            "url": "http://localhost:8080",
            "api_key": "${MY_MCP_API_KEY}",
        }
        config = MCPServerConfig.from_dict("env-server", data)
        assert config.api_key == "resolved-secret-key"

    def test_env_var_api_key_not_set(self, monkeypatch):
        """测试环境变量未设置时 api_key 为 None。"""
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        data = {
            "transport": "http",
            "url": "http://localhost:8080",
            "api_key": "${NONEXISTENT_KEY}",
        }
        config = MCPServerConfig.from_dict("unset-server", data)
        assert config.api_key is None

    def test_plain_api_key_unchanged(self):
        """测试非环境变量格式的 api_key 保持原值。"""
        data = {
            "transport": "http",
            "url": "http://localhost:8080",
            "api_key": "plain-key-no-braces",
        }
        config = MCPServerConfig.from_dict("plain-server", data)
        assert config.api_key == "plain-key-no-braces"

    def test_defaults_for_optional_fields(self):
        """测试可选字段的默认值。"""
        data = {"command": "echo"}
        config = MCPServerConfig.from_dict("minimal", data)
        assert config.args == []
        assert config.env == {}
        assert config.url is None
        assert config.api_key is None
        assert config.headers == {}


class TestMCPServerConfigValidate:
    """测试 MCPServerConfig.validate。"""

    def test_stdio_missing_command_raises(self):
        """测试 stdio 缺少 command 时抛出异常。"""
        config = MCPServerConfig(name="bad-stdio", transport="stdio", command=None)
        with pytest.raises(MCPConfigError, match="stdio transport requires 'command'"):
            config.validate()

    def test_stdio_empty_command_raises(self):
        """测试 stdio command 为空字符串时抛出异常。"""
        config = MCPServerConfig(name="empty-stdio", transport="stdio", command="")
        with pytest.raises(MCPConfigError, match="stdio transport requires 'command'"):
            config.validate()

    def test_http_missing_url_raises(self):
        """测试 http 缺少 url 时抛出异常。"""
        config = MCPServerConfig(name="bad-http", transport="http", url=None)
        with pytest.raises(MCPConfigError, match="http transport requires 'url'"):
            config.validate()

    def test_http_empty_url_raises(self):
        """测试 http url 为空字符串时抛出异常。"""
        config = MCPServerConfig(name="empty-http", transport="http", url="")
        with pytest.raises(MCPConfigError, match="http transport requires 'url'"):
            config.validate()

    def test_unknown_transport_raises(self):
        """测试未知 transport 时抛出异常。"""
        config = MCPServerConfig(name="unknown", transport="websocket", command="echo")
        with pytest.raises(MCPConfigError, match="Unknown transport: websocket"):
            config.validate()

    def test_valid_stdio_passes(self):
        """测试合法 stdio 配置通过验证。"""
        config = MCPServerConfig(name="ok-stdio", transport="stdio", command="npx")
        config.validate()  # 不应抛出异常

    def test_valid_http_passes(self):
        """测试合法 http 配置通过验证。"""
        config = MCPServerConfig(
            name="ok-http", transport="http", url="http://localhost:8080"
        )
        config.validate()  # 不应抛出异常


class TestMCPConfigFromDict:
    """测试 MCPConfig.from_dict。"""

    def test_multiple_servers(self):
        """测试解析多个服务器配置。"""
        data = {
            "servers": {
                "fs-server": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "fs-server"],
                },
                "remote-server": {
                    "transport": "http",
                    "url": "http://localhost:8080",
                },
            }
        }
        config = MCPConfig.from_dict(data)
        assert len(config.servers) == 2
        names = {s.name for s in config.servers}
        assert names == {"fs-server", "remote-server"}

    def test_empty_servers(self):
        """测试空服务器配置。"""
        data = {"servers": {}}
        config = MCPConfig.from_dict(data)
        assert config.servers == []

    def test_no_servers_key(self):
        """测试缺少 servers 键时返回空配置。"""
        data = {}
        config = MCPConfig.from_dict(data)
        assert config.servers == []

    def test_invalid_server_raises(self):
        """测试无效服务器配置（stdio 缺少 command）抛出异常。"""
        data = {
            "servers": {
                "bad-server": {
                    "transport": "stdio",
                    # 缺少 command
                },
            }
        }
        with pytest.raises(MCPConfigError, match="stdio transport requires 'command'"):
            MCPConfig.from_dict(data)


class TestMCPConfigFromYaml:
    """测试 MCPConfig.from_yaml。"""

    def test_file_not_found_raises(self):
        """测试 YAML 文件不存在时抛出异常。"""
        with pytest.raises(MCPConfigError, match="Config file not found"):
            MCPConfig.from_yaml("/nonexistent/path/config.yaml")

    def test_valid_yaml(self, tmp_path):
        """测试合法 YAML 文件解析。"""
        yaml_content = """
servers:
  fs-server:
    transport: stdio
    command: npx
    args:
      - -y
      - fs-server
  remote-server:
    transport: http
    url: http://localhost:8080
    api_key: sk-test
"""
        config_file = tmp_path / "mcp_config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        config = MCPConfig.from_yaml(str(config_file))
        assert len(config.servers) == 2
        names = {s.name for s in config.servers}
        assert names == {"fs-server", "remote-server"}

    def test_empty_yaml(self, tmp_path):
        """测试空 YAML 文件。"""
        config_file = tmp_path / "empty_config.yaml"
        config_file.write_text("", encoding="utf-8")

        config = MCPConfig.from_yaml(str(config_file))
        assert config.servers == []

    def test_yaml_with_invalid_server(self, tmp_path):
        """测试 YAML 中包含无效服务器配置时抛出异常。"""
        yaml_content = """
servers:
  bad-server:
    transport: http
    # 缺少 url
"""
        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(MCPConfigError, match="http transport requires 'url'"):
            MCPConfig.from_yaml(str(config_file))
