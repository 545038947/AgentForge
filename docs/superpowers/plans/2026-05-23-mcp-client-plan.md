# MCP Client 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 MCP Client 支持，让 AgentForge 可以连接外部 MCP Server 并使用其工具和资源。

**Architecture:** 采用分层架构 - Transport 层处理通信，Client 层处理协议，Manager 层管理连接和集成。

**Tech Stack:** Python 3.9+, asyncio, aiohttp, pydantic

---

## 文件结构

```
hai_agent/mcp/
├── __init__.py           # 模块入口，导出公共 API
├── types.py              # MCP 类型定义
├── config.py             # 配置解析
├── transport.py          # Transport 抽象基类
├── transports/
│   ├── __init__.py
│   ├── stdio.py          # Stdio 传输实现
│   └── http.py           # HTTP 传输实现
├── client.py             # MCPClient 实现
├── tool.py               # MCPTool 包装器
├── resource.py           # MCPResource 管理
├── manager.py            # MCPManager 总管理
└── errors.py             # MCP 错误类型
```

---

### Task 1: MCP 类型定义

**Files:**
- Create: `hai_agent/mcp/__init__.py`
- Create: `hai_agent/mcp/types.py`
- Create: `hai_agent/mcp/errors.py`

- [ ] **Step 1: 创建 MCP 错误类型**

```python
# hai_agent/mcp/errors.py
"""MCP 错误类型。"""

from hai_agent.types.errors import AgentForgeError


class MCPError(AgentForgeError):
    """MCP 相关错误基类。"""
    pass


class MCPConnectionError(MCPError):
    """MCP Server 连接失败。"""
    pass


class MCPToolCallError(MCPError):
    """MCP 工具调用失败。"""
    pass


class MCPResourceError(MCPError):
    """MCP Resource 访问失败。"""
    pass


class MCPConfigError(MCPError):
    """MCP 配置错误。"""
    pass
```

- [ ] **Step 2: 创建 MCP 类型定义**

```python
# hai_agent/mcp/types.py
"""MCP 类型定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MCPToolSchema:
    """MCP 工具 Schema。"""
    name: str
    description: str
    inputSchema: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: dict) -> "MCPToolSchema":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            inputSchema=data.get("inputSchema", {"type": "object"}),
        )


@dataclass
class MCPResourceSchema:
    """MCP 资源 Schema。"""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "MCPResourceSchema":
        return cls(
            uri=data["uri"],
            name=data.get("name", data["uri"]),
            description=data.get("description"),
            mimeType=data.get("mimeType"),
        )


@dataclass
class MCPToolResult:
    """MCP 工具调用结果。"""
    content: str
    isError: bool = False
    
    @classmethod
    def from_dict(cls, data: dict) -> "MCPToolResult":
        # MCP 返回的 content 可能是列表
        content = data.get("content", "")
        if isinstance(content, list):
            # 提取文本内容
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            content = "\n".join(texts)
        return cls(content=content, isError=data.get("isError", False))


@dataclass
class MCPResourceContent:
    """MCP 资源内容。"""
    uri: str
    text: str
    mimeType: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "MCPResourceContent":
        contents = data.get("contents", [])
        if contents:
            item = contents[0]
            text = item.get("text", "")
            if isinstance(text, bytes):
                text = text.decode("utf-8")
            return cls(
                uri=item.get("uri", ""),
                text=text,
                mimeType=item.get("mimeType"),
            )
        return cls(uri="", text="")
```

- [ ] **Step 3: 创建模块入口**

```python
# hai_agent/mcp/__init__.py
"""MCP (Model Context Protocol) 支持。"""

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
from hai_agent.mcp.config import MCPConfig, MCPServerConfig
from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.tool import MCPTool
from hai_agent.mcp.manager import MCPManager

__all__ = [
    # Types
    "MCPToolSchema",
    "MCPResourceSchema",
    "MCPToolResult",
    "MCPResourceContent",
    # Errors
    "MCPError",
    "MCPConnectionError",
    "MCPToolCallError",
    "MCPResourceError",
    "MCPConfigError",
    # Config
    "MCPConfig",
    "MCPServerConfig",
    # Client
    "MCPClient",
    "MCPTool",
    "MCPManager",
]
```

- [ ] **Step 4: 提交**

```bash
git add hai_agent/mcp/__init__.py hai_agent/mcp/types.py hai_agent/mcp/errors.py
git commit -m "feat(mcp): 添加 MCP 类型和错误定义"
```

---

### Task 2: MCP 配置解析

**Files:**
- Create: `hai_agent/mcp/config.py`

- [ ] **Step 1: 创建配置类型**

```python
# hai_agent/mcp/config.py
"""MCP 配置解析。"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hai_agent.mcp.errors import MCPConfigError


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
```

- [ ] **Step 2: 提交**

```bash
git add hai_agent/mcp/config.py
git commit -m "feat(mcp): 添加 MCP 配置解析"
```

---

### Task 3: MCP Transport 层

**Files:**
- Create: `hai_agent/mcp/transport.py`
- Create: `hai_agent/mcp/transports/__init__.py`
- Create: `hai_agent/mcp/transports/stdio.py`
- Create: `hai_agent/mcp/transports/http.py`

- [ ] **Step 1: 创建 Transport 抽象基类**

```python
# hai_agent/mcp/transport.py
"""MCP Transport 抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class MCPTransport(ABC):
    """MCP 传输层抽象基类。"""
    
    @abstractmethod
    async def connect(self) -> None:
        """建立连接。"""
        pass
    
    @abstractmethod
    async def request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送 JSON-RPC 请求。"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接。"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """检查是否已连接。"""
        pass
```

- [ ] **Step 2: 创建 Stdio Transport**

```python
# hai_agent/mcp/transports/stdio.py
"""Stdio Transport 实现。"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from hai_agent.mcp.transport import MCPTransport
from hai_agent.mcp.errors import MCPConnectionError

logger = logging.getLogger(__name__)


class StdioTransport(MCPTransport):
    """Stdio 传输层，通过进程间通信连接 MCP Server。"""
    
    def __init__(
        self,
        command: str,
        args: list = None,
        env: Dict[str, str] = None,
    ):
        self._command = command
        self._args = args or []
        self._env = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
    
    async def connect(self) -> None:
        """启动 MCP Server 进程。"""
        try:
            # 合并环境变量
            import os
            env = os.environ.copy()
            env.update(self._env)
            
            self._process = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            logger.info(f"Started MCP Server: {self._command}")
        except Exception as e:
            raise MCPConnectionError(f"Failed to start MCP Server: {e}")
    
    async def request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """通过 stdin/stdout 发送 JSON-RPC 请求。"""
        if not self._process:
            raise MCPConnectionError("Not connected")
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        
        # 发送请求
        request_str = json.dumps(request) + "\n"
        self._process.stdin.write(request_str.encode("utf-8"))
        await self._process.stdin.drain()
        
        # 读取响应
        response_line = await self._process.stdout.readline()
        if not response_line:
            raise MCPConnectionError("Empty response from MCP Server")
        
        response = json.loads(response_line.decode("utf-8"))
        
        # 检查错误
        if "error" in response:
            error = response["error"]
            raise MCPConnectionError(f"MCP error: {error.get('message', error)}")
        
        return response.get("result", {})
    
    async def close(self) -> None:
        """关闭进程。"""
        if self._process:
            self._process.stdin.close()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
            logger.info("Closed MCP Server process")
    
    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return self._process is not None and self._process.returncode is None
```

- [ ] **Step 3: 创建 HTTP Transport**

```python
# hai_agent/mcp/transports/http.py
"""HTTP Transport 实现。"""

import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from hai_agent.mcp.transport import MCPTransport
from hai_agent.mcp.errors import MCPConnectionError

logger = logging.getLogger(__name__)


class HTTPTransport(MCPTransport):
    """HTTP 传输层，通过 HTTP 连接远程 MCP Server。"""
    
    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        headers: Dict[str, str] = None,
    ):
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._headers = headers or {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._request_id = 0
    
    async def connect(self) -> None:
        """初始化 HTTP 连接。"""
        # 构建请求头
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._headers)
        
        self._session = aiohttp.ClientSession(headers=headers)
        logger.info(f"Connected to MCP Server: {self._url}")
    
    async def request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送 HTTP 请求。"""
        if not self._session:
            raise MCPConnectionError("Not connected")
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        
        try:
            async with self._session.post(
                f"{self._url}/rpc",
                json=request,
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise MCPConnectionError(f"HTTP {response.status}: {text}")
                
                data = await response.json()
                
                if "error" in data:
                    error = data["error"]
                    raise MCPConnectionError(f"MCP error: {error.get('message', error)}")
                
                return data.get("result", {})
        except aiohttp.ClientError as e:
            raise MCPConnectionError(f"HTTP request failed: {e}")
    
    async def close(self) -> None:
        """关闭 HTTP 会话。"""
        if self._session:
            await self._session.close()
            self._session = None
            logger.info("Closed HTTP session")
    
    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return self._session is not None and not self._session.closed
```

- [ ] **Step 4: 创建 transports 模块入口**

```python
# hai_agent/mcp/transports/__init__.py
"""MCP Transports。"""

from hai_agent.mcp.transports.stdio import StdioTransport
from hai_agent.mcp.transports.http import HTTPTransport

__all__ = ["StdioTransport", "HTTPTransport"]
```

- [ ] **Step 5: 提交**

```bash
git add hai_agent/mcp/transport.py hai_agent/mcp/transports/
git commit -m "feat(mcp): 添加 MCP Transport 层实现"
```

---

### Task 4: MCP Client 实现

**Files:**
- Create: `hai_agent/mcp/client.py`

- [ ] **Step 1: 创建 MCPClient**

```python
# hai_agent/mcp/client.py
"""MCP Client 实现。"""

import logging
from typing import List, Optional

from hai_agent.mcp.config import MCPServerConfig
from hai_agent.mcp.transport import MCPTransport
from hai_agent.mcp.transports import StdioTransport, HTTPTransport
from hai_agent.mcp.types import MCPToolSchema, MCPResourceSchema, MCPToolResult, MCPResourceContent
from hai_agent.mcp.errors import MCPConnectionError, MCPToolCallError, MCPResourceError

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP Server 客户端。"""
    
    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._transport: Optional[MCPTransport] = None
        self._tools: List[MCPToolSchema] = []
        self._resources: List[MCPResourceSchema] = []
        self._initialized = False
    
    @property
    def name(self) -> str:
        """Server 名称。"""
        return self._config.name
    
    @property
    def config(self) -> MCPServerConfig:
        """Server 配置。"""
        return self._config
    
    @property
    def tools(self) -> List[MCPToolSchema]:
        """已发现的工具列表。"""
        return self._tools
    
    @property
    def resources(self) -> List[MCPResourceSchema]:
        """已发现的资源列表。"""
        return self._resources
    
    async def connect(self) -> None:
        """连接 MCP Server。"""
        # 创建 Transport
        if self._config.transport == "stdio":
            self._transport = StdioTransport(
                command=self._config.command,
                args=self._config.args,
                env=self._config.env,
            )
        elif self._config.transport == "http":
            self._transport = HTTPTransport(
                url=self._config.url,
                api_key=self._config.api_key,
                headers=self._config.headers,
            )
        else:
            raise MCPConnectionError(f"Unknown transport: {self._config.transport}")
        
        # 连接
        await self._transport.connect()
        
        # 初始化协议
        await self._initialize()
        
        # 发现工具和资源
        await self._discover()
        
        logger.info(f"MCP Client connected: {self.name}")
    
    async def _initialize(self) -> None:
        """初始化 MCP 协议。"""
        result = await self._transport.request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {
                "name": "AgentForge",
                "version": "0.1.0",
            },
            "capabilities": {},
        })
        
        # 发送 initialized 通知
        await self._transport.request("notifications/initialized", {})
        self._initialized = True
    
    async def _discover(self) -> None:
        """发现工具和资源。"""
        # 发现工具
        try:
            result = await self._transport.request("tools/list", {})
            for tool_data in result.get("tools", []):
                self._tools.append(MCPToolSchema.from_dict(tool_data))
            logger.debug(f"Discovered {len(self._tools)} tools from {self.name}")
        except Exception as e:
            logger.warning(f"Failed to list tools from {self.name}: {e}")
        
        # 发现资源
        try:
            result = await self._transport.request("resources/list", {})
            for resource_data in result.get("resources", []):
                self._resources.append(MCPResourceSchema.from_dict(resource_data))
            logger.debug(f"Discovered {len(self._resources)} resources from {self.name}")
        except Exception as e:
            logger.warning(f"Failed to list resources from {self.name}: {e}")
    
    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """调用工具。"""
        if not self._transport:
            raise MCPToolCallError("Not connected")
        
        try:
            result = await self._transport.request("tools/call", {
                "name": name,
                "arguments": arguments,
            })
            return MCPToolResult.from_dict(result)
        except Exception as e:
            raise MCPToolCallError(f"Tool call failed: {e}")
    
    async def read_resource(self, uri: str) -> MCPResourceContent:
        """读取资源。"""
        if not self._transport:
            raise MCPResourceError("Not connected")
        
        try:
            result = await self._transport.request("resources/read", {"uri": uri})
            return MCPResourceContent.from_dict(result)
        except Exception as e:
            raise MCPResourceError(f"Resource read failed: {e}")
    
    async def close(self) -> None:
        """关闭连接。"""
        if self._transport:
            await self._transport.close()
            self._transport = None
            self._initialized = False
            logger.info(f"MCP Client closed: {self.name}")
    
    def is_connected(self) -> bool:
        """检查是否已连接。"""
        return self._transport is not None and self._transport.is_connected()
```

- [ ] **Step 2: 提交**

```bash
git add hai_agent/mcp/client.py
git commit -m "feat(mcp): 添加 MCPClient 实现"
```

---

### Task 5: MCPTool 包装器

**Files:**
- Create: `hai_agent/mcp/tool.py`

- [ ] **Step 1: 创建 MCPTool**

```python
# hai_agent/mcp/tool.py
"""MCP Tool 包装器。"""

import asyncio
import logging
from typing import Any, Dict

from hai_agent.tools.base import Tool
from hai_agent.types import ToolResult
from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.types import MCPToolSchema

logger = logging.getLogger(__name__)


class MCPTool(Tool):
    """MCP 工具包装器，将 MCP 工具转换为 AgentForge Tool。"""
    
    # 工具配置
    timeout: float = 60.0
    requires_approval: bool = False
    dangerous: bool = False
    
    def __init__(self, client: MCPClient, schema: MCPToolSchema):
        self._client = client
        self._mcp_schema = schema
    
    @property
    def name(self) -> str:
        """工具名称。"""
        return self._mcp_schema.name
    
    @property
    def description(self) -> str:
        """工具描述。"""
        return self._mcp_schema.description
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """工具参数定义。"""
        return self._mcp_schema.inputSchema
    
    @property
    def mcp_server_name(self) -> str:
        """MCP Server 名称（用于调试）。"""
        return self._client.name
    
    @property
    def mcp_schema(self) -> MCPToolSchema:
        """原始 MCP Schema（保留元数据）。"""
        return self._mcp_schema
    
    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        """执行 MCP 工具调用。"""
        try:
            # MCP Client 是异步的，需要在事件循环中运行
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                # 如果已在异步上下文中，创建任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._client.call_tool(self.name, kwargs)
                    )
                    result = future.result(timeout=self.timeout)
            else:
                # 否则直接运行
                result = loop.run_until_complete(
                    self._client.call_tool(self.name, kwargs)
                )
            
            return ToolResult(
                tool_call_id=tool_call_id,
                content=result.content,
                is_error=result.isError,
            )
        
        except Exception as e:
            logger.error(f"MCP tool call failed: {self.name} - {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"MCP tool error: {e}",
                is_error=True,
            )
```

- [ ] **Step 2: 提交**

```bash
git add hai_agent/mcp/tool.py
git commit -m "feat(mcp): 添加 MCPTool 包装器"
```

---

### Task 6: MCPManager 和 Agent 集成

**Files:**
- Create: `hai_agent/mcp/resource.py`
- Create: `hai_agent/mcp/manager.py`
- Modify: `hai_agent/agent.py`

- [ ] **Step 1: 创建 MCPResourceManager**

```python
# hai_agent/mcp/resource.py
"""MCP Resource 管理。"""

import logging
from typing import List, Optional

from hai_agent.mcp.types import MCPResourceSchema, MCPResourceContent
from hai_agent.mcp.errors import MCPResourceError

logger = logging.getLogger(__name__)


class MCPResourceManager:
    """MCP 资源管理器。"""
    
    def __init__(self, manager: "MCPManager"):
        self._manager = manager
    
    def list_resources(self, server_name: str = None) -> List[MCPResourceSchema]:
        """列出可用资源。"""
        if server_name:
            client = self._manager.get_client(server_name)
            if client:
                return client.resources
            return []
        
        # 收集所有 server 的资源
        all_resources = []
        for client in self._manager.clients:
            all_resources.extend(client.resources)
        return all_resources
    
    async def read_resource(self, uri: str) -> str:
        """读取资源内容。"""
        # 根据 URI 找到对应的 client
        client = self._find_client_for_resource(uri)
        if not client:
            raise MCPResourceError(f"Resource not found: {uri}")
        
        content = await client.read_resource(uri)
        return content.text
    
    def _find_client_for_resource(self, uri: str) -> Optional["MCPClient"]:
        """根据 URI 找到对应的 client。"""
        for client in self._manager.clients:
            for resource in client.resources:
                if resource.uri == uri:
                    return client
        return None
```

- [ ] **Step 2: 创建 MCPManager**

```python
# hai_agent/mcp/manager.py
"""MCP Manager 总管理器。"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

from hai_agent.mcp.config import MCPConfig, MCPServerConfig
from hai_agent.mcp.client import MCPClient
from hai_agent.mcp.tool import MCPTool
from hai_agent.mcp.resource import MCPResourceManager
from hai_agent.mcp.errors import MCPError

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP 总管理器。"""
    
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._config: Optional[MCPConfig] = None
        self._resource_manager: Optional[MCPResourceManager] = None
    
    @property
    def clients(self) -> List[MCPClient]:
        """所有已连接的 client。"""
        return list(self._clients.values())
    
    @property
    def resource_manager(self) -> MCPResourceManager:
        """资源管理器。"""
        if self._resource_manager is None:
            self._resource_manager = MCPResourceManager(self)
        return self._resource_manager
    
    def load_config(self, path: str) -> None:
        """加载 YAML 配置文件。"""
        self._config = MCPConfig.from_yaml(path)
        logger.info(f"Loaded MCP config: {len(self._config.servers)} servers")
    
    def load_config_from_dict(self, data: dict) -> None:
        """从字典加载配置。"""
        self._config = MCPConfig.from_dict(data)
        logger.info(f"Loaded MCP config: {len(self._config.servers)} servers")
    
    async def start_all(self) -> None:
        """启动所有已启用的 MCP Server 连接。"""
        if not self._config:
            logger.warning("No MCP config loaded")
            return
        
        for server_config in self._config.servers:
            if not server_config.enabled:
                logger.debug(f"Skipping disabled server: {server_config.name}")
                continue
            
            try:
                client = MCPClient(server_config)
                await client.connect()
                self._clients[server_config.name] = client
            except Exception as e:
                logger.error(f"Failed to connect to {server_config.name}: {e}")
        
        logger.info(f"Started {len(self._clients)} MCP servers")
    
    def get_client(self, name: str) -> Optional[MCPClient]:
        """获取指定名称的 client。"""
        return self._clients.get(name)
    
    def get_tools(self) -> List[MCPTool]:
        """获取所有 MCP 工具（转换为 MCPTool）。"""
        tools = []
        for client in self._clients.values():
            for schema in client.tools:
                tools.append(MCPTool(client, schema))
        logger.debug(f"Collected {len(tools)} MCP tools")
        return tools
    
    async def stop_all(self) -> None:
        """关闭所有连接。"""
        for name, client in self._clients.items():
            try:
                await client.close()
            except Exception as e:
                logger.error(f"Failed to close {name}: {e}")
        self._clients.clear()
        logger.info("Stopped all MCP servers")
    
    def is_connected(self, name: str = None) -> bool:
        """检查连接状态。"""
        if name:
            client = self._clients.get(name)
            return client.is_connected() if client else False
        return all(c.is_connected() for c in self._clients.values())
```

- [ ] **Step 3: 更新 Agent 类**

在 `hai_agent/agent.py` 中添加 MCP 相关方法：

```python
# 在 Agent 类中添加以下方法

def load_mcp_config(self, path: str) -> None:
    """加载 MCP Server 配置文件。
    
    Args:
        path: 配置文件路径（YAML 格式）
    
    使用示例：
        agent.load_mcp_config("mcp_servers.yaml")
        # MCP 工具自动可用
    """
    from hai_agent.mcp import MCPManager
    
    if not hasattr(self, "_mcp_manager") or self._mcp_manager is None:
        self._mcp_manager = MCPManager()
    
    self._mcp_manager.load_config(path)
    
    # 同步启动（在事件循环中）
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(self._mcp_manager.start_all())
    
    # 自动注册 MCP 工具
    mcp_tools = self._mcp_manager.get_tools()
    if mcp_tools:
        self.add_tools(mcp_tools)
        logger.info(f"Registered {len(mcp_tools)} MCP tools")

def list_mcp_resources(self, server_name: str = None) -> List:
    """列出 MCP Resources。
    
    Args:
        server_name: 指定 server 名称（可选）
    
    Returns:
        资源列表
    """
    if not hasattr(self, "_mcp_manager") or self._mcp_manager is None:
        return []
    return self._mcp_manager.resource_manager.list_resources(server_name)

async def read_mcp_resource_async(self, uri: str) -> str:
    """异步读取 MCP Resource 内容。
    
    Args:
        uri: 资源 URI
    
    Returns:
        资源内容
    """
    if not hasattr(self, "_mcp_manager") or self._mcp_manager is None:
        raise ValueError("MCP not configured")
    return await self._mcp_manager.resource_manager.read_resource(uri)

def read_mcp_resource(self, uri: str) -> str:
    """读取 MCP Resource 内容（同步版本）。
    
    Args:
        uri: 资源 URI
    
    Returns:
        资源内容
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(self.read_mcp_resource_async(uri))

async def close_mcp(self) -> None:
    """关闭所有 MCP 连接。"""
    if hasattr(self, "_mcp_manager") and self._mcp_manager is not None:
        await self._mcp_manager.stop_all()
```

- [ ] **Step 4: 更新 hai_agent/__init__.py 导出 MCP**

```python
# 在 hai_agent/__init__.py 中添加
from hai_agent.mcp import (
    MCPManager,
    MCPClient,
    MCPTool,
    MCPError,
    MCPConnectionError,
)
```

- [ ] **Step 5: 提交**

```bash
git add hai_agent/mcp/resource.py hai_agent/mcp/manager.py hai_agent/agent.py hai_agent/__init__.py
git commit -m "feat(mcp): 添加 MCPManager 并集成到 Agent"
```

---

### Task 7: Demo 和测试

**Files:**
- Create: `demo/mcp_demo.py`
- Create: `demo/mcp_servers.yaml`

- [ ] **Step 1: 创建示例配置文件**

```yaml
# demo/mcp_servers.yaml
# 示例 MCP Server 配置

servers:
  # 文件系统 MCP Server（需要安装 mcp-server-filesystem）
  # filesystem:
  #   transport: stdio
  #   command: mcp-server-filesystem
  #   args:
  #     - "--root"
  #     - "./data"
  #   enabled: true
  
  # 示例 HTTP MCP Server
  # remote_tools:
  #   transport: http
  #   url: http://localhost:8080/mcp
  #   enabled: true
```

- [ ] **Step 2: 创建 Demo 脚本**

```python
# demo/mcp_demo.py
"""MCP Demo - 展示 MCP Client 功能。"""

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from hai_agent import Agent
from hai_agent.providers.builtins.ollama import OllamaProvider
from demo.config import get_config


def main():
    print("=" * 50)
    print("AgentForge MCP Demo")
    print("=" * 50)
    
    config = get_config()
    
    # 检查 MCP 配置文件
    mcp_config_path = Path(__file__).parent / "mcp_servers.yaml"
    if not mcp_config_path.exists():
        print("\n⚠️  MCP 配置文件不存在")
        print(f"   请创建: {mcp_config_path}")
        print("\n示例配置:")
        print("""
servers:
  filesystem:
    transport: stdio
    command: mcp-server-filesystem
    args:
      - "--root"
      - "./data"
    enabled: true
""")
        return
    
    # 创建 Agent
    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
    )
    agent = Agent(provider=provider)
    
    # 加载 MCP 配置
    print(f"\n📁 加载 MCP 配置: {mcp_config_path}")
    agent.load_mcp_config(str(mcp_config_path))
    
    # 显示已注册的 MCP 工具
    print("\n🔧 MCP 工具:")
    for tool in agent._mcp_manager.get_tools():
        print(f"   - {tool.name} (from {tool.mcp_server_name})")
    
    # 显示可用资源
    resources = agent.list_mcp_resources()
    if resources:
        print("\n📦 MCP 资源:")
        for res in resources:
            print(f"   - {res.uri}")
    
    print("\n" + "=" * 50)
    print("✅ MCP Demo 完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 提交**

```bash
git add demo/mcp_demo.py demo/mcp_servers.yaml
git commit -m "feat(demo): 添加 MCP Demo 示例"
```

---

### Task 8: 文档更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README 添加 MCP 说明**

在 README.md 中添加 MCP 使用说明章节。

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: 添加 MCP 使用说明"
```

---

## 实现完成检查

- [ ] 所有文件已创建
- [ ] 所有测试通过
- [ ] Demo 可运行
- [ ] 文档已更新
