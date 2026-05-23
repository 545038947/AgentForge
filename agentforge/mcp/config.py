"""MCP 配置解析。"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from agentforge.mcp.errors import MCPConfigError


@dataclass
class MCPServerConfig:
    """单个 MCP Server 配置。"""
    name: str
    transport: str  # "stdio" or "http"
    enabled: bool = True

    # Stdio 配置
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)

    # HTTP 配置
    url: Optional[str] = None
    api_key: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MCPServerConfig":
        """从字典创建配置。"""
        transport = data.get("transport", "stdio")

        # 解析 API Key（支持环境变量引用）
        api_key = data.get("api_key")
        if api_key and api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            api_key = os.environ.get(env_var)

        return cls(
            name=name,
            transport=transport,
            enabled=data.get("enabled", True),
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            api_key=api_key,
            headers=data.get("headers", {}),
        )

    def validate(self) -> None:
        """验证配置。"""
        if self.transport == "stdio":
            if not self.command:
                raise MCPConfigError(f"stdio transport requires 'command': {self.name}")
        elif self.transport == "http":
            if not self.url:
                raise MCPConfigError(f"http transport requires 'url': {self.name}")
        else:
            raise MCPConfigError(f"Unknown transport: {self.transport}")


@dataclass
class MCPConfig:
    """MCP 总配置。"""
    servers: List[MCPServerConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "MCPConfig":
        """从 YAML 文件加载配置。"""
        config_path = Path(path)
        if not config_path.exists():
            raise MCPConfigError(f"Config file not found: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        servers = []
        servers_data = data.get("servers", {})
        for name, server_data in servers_data.items():
            config = MCPServerConfig.from_dict(name, server_data)
            config.validate()
            servers.append(config)

        return cls(servers=servers)

    @classmethod
    def from_dict(cls, data: dict) -> "MCPConfig":
        """从字典创建配置。"""
        servers = []
        servers_data = data.get("servers", {})
        for name, server_data in servers_data.items():
            config = MCPServerConfig.from_dict(name, server_data)
            config.validate()
            servers.append(config)
        return cls(servers=servers)
