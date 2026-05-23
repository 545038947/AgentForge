# MCP Client 支持设计文档

> **目标：** 为 AgentForge 添加 MCP (Model Context Protocol) Client 支持，使其能够连接外部 MCP Server 并使用其提供的 Tools 和 Resources。

---

## 概述

MCP (Model Context Protocol) 是 Anthropic 推出的协议，用于标准化 LLM 与外部工具和资源的交互。本设计实现 MCP Client 功能，让 AgentForge 可以：

- 连接外部 MCP Server（通过 Stdio 或 HTTP/SSE）
- 自动发现并使用 MCP Server 提供的工具
- 访问 MCP Server 提供的资源
- 支持 API Key 认证

**不实现的功能：**
- MCP Prompts（预定义提示模板）
- MCP Server 角色（作为服务端暴露工具）

---

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                        Agent                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   Tools     │  │ MemoryStore │  │   MCPManager    │ │
│  │  (现有)     │  │  (现有)     │  │    (新增)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────┘ │
│                              │                          │
│                              │ 自动注册工具             │
│                              ▼                          │
│                    ┌─────────────────┐                  │
│                    │  MCPTool(s)     │                  │
│                    │  (新增)         │                  │
│                    └─────────────────┘                  │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                     MCPManager                           │
│  - 加载配置文件                                          │
│  - 管理多个 MCP Server 连接                              │
│  - 提供 ResourceManager 接口                             │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                     MCPClient                            │
│  - 实现 JSON-RPC 2.0 协议                                │
│  - 管理单个 MCP Server 连接                              │
│  - 工具发现、资源访问                                     │
└─────────────────────────────────────────────────────────┘
              │                           │
              ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐
│   StdioTransport    │     │    HTTPTransport    │
│   (新增)            │     │    (新增)           │
│   - 进程启动         │     │    - HTTP/SSE      │
│   - stdin/stdout    │     │    - API Key 认证   │
└─────────────────────┘     └─────────────────────┘
              │                           │
              ▼                           ▼
        ┌───────────┐             ┌───────────┐
        │ 本地 MCP  │             │ 远程 MCP  │
        │  Server   │             │  Server   │
        └───────────┘             └───────────┘
```

---

## 核心组件

### 1. MCPClient

单个 MCP Server 的客户端，负责协议通信。

```python
class MCPClient:
    """MCP Server 客户端。"""
    
    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._transport: MCPTransport = None
        self._tools: List[MCPToolSchema] = []
        self._resources: List[MCPResourceSchema] = []
    
    async def connect(self) -> None:
        """连接 MCP Server。"""
        self._transport = self._create_transport()
        await self._transport.connect()
        await self._initialize()
    
    async def list_tools(self) -> List[MCPToolSchema]:
        """获取服务器提供的工具列表。"""
        return self._tools
    
    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """调用工具。"""
        return await self._transport.request("tools/call", {
            "name": name,
            "arguments": arguments
        })
    
    async def list_resources(self) -> List[MCPResourceSchema]:
        """获取服务器提供的资源列表。"""
        return self._resources
    
    async def read_resource(self, uri: str) -> MCPResourceContent:
        """读取资源内容。"""
        return await self._transport.request("resources/read", {"uri": uri})
    
    async def close(self) -> None:
        """关闭连接。"""
        await self._transport.close()
```

### 2. MCPTransport

传输层抽象，支持 Stdio 和 HTTP/SSE。

```python
class MCPTransport(ABC):
    """MCP 传输层抽象基类。"""
    
    @abstractmethod
    async def connect(self) -> None:
        """建立连接。"""
    
    @abstractmethod
    async def request(self, method: str, params: dict) -> dict:
        """发送 JSON-RPC 请求。"""
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接。"""
```

#### StdioTransport

通过进程间通信连接本地 MCP Server。

```python
class StdioTransport(MCPTransport):
    """Stdio 传输层。"""
    
    def __init__(self, command: str, args: List[str] = None):
        self._command = command
        self._args = args or []
        self._process: asyncio.subprocess.Process = None
    
    async def connect(self) -> None:
        """启动 MCP Server 进程。"""
        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
    
    async def request(self, method: str, params: dict) -> dict:
        """通过 stdin/stdout 发送请求。"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params
        }
        self._process.stdin.write(json.dumps(request).encode() + b"\n")
        await self._process.stdin.drain()
        
        response_line = await self._process.stdout.readline()
        response = json.loads(response_line)
        return response.get("result", {})
```

#### HTTPTransport

通过 HTTP/SSE 连接远程 MCP Server，支持 API Key 认证。

```python
class HTTPTransport(MCPTransport):
    """HTTP/SSE 传输层。"""
    
    def __init__(self, url: str, api_key: str = None):
        self._url = url
        self._api_key = api_key
        self._headers: Dict[str, str] = {}
    
    async def connect(self) -> None:
        """初始化 HTTP 连接。"""
        if self._api_key:
            self._headers["Authorization"] = f"Bearer {self._api_key}"
    
    async def request(self, method: str, params: dict) -> dict:
        """发送 HTTP 请求。"""
        response = await aiohttp.post(
            f"{self._url}/rpc",
            json={
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params
            },
            headers=self._headers
        )
        data = await response.json()
        return data.get("result", {})
```

### 3. MCPTool

包装 MCP 工具为 AgentForge Tool，保留 MCP 元数据。

```python
class MCPTool(Tool):
    """MCP 工具包装器。"""
    
    def __init__(self, client: MCPClient, schema: MCPToolSchema):
        self._client = client
        self._mcp_schema = schema  # 保留原始 MCP schema
    
    @property
    def name(self) -> str:
        return self._mcp_schema.name
    
    @property
    def description(self) -> str:
        return self._mcp_schema.description
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return self._mcp_schema.inputSchema
    
    @property
    def mcp_server_name(self) -> str:
        """MCP Server 名称（用于调试）。"""
        return self._client.config.name
    
    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        """执行 MCP 工具调用。"""
        result = await self._client.call_tool(self.name, kwargs)
        
        return ToolResult(
            tool_call_id=tool_call_id,
            content=result.get("content", ""),
            is_error=result.get("isError", False),
        )
```

### 4. MCPResourceManager

管理 MCP Resources，提供统一访问接口。

```python
class MCPResourceManager:
    """MCP 资源管理器。"""
    
    def __init__(self, manager: MCPManager):
        self._manager = manager
    
    async def list_resources(self, server_name: str = None) -> List[MCPResourceInfo]:
        """列出可用资源。"""
        if server_name:
            client = self._manager.get_client(server_name)
            return await client.list_resources()
        
        # 收集所有 server 的资源
        all_resources = []
        for client in self._manager.clients:
            resources = await client.list_resources()
            all_resources.extend(resources)
        return all_resources
    
    async def read_resource(self, uri: str) -> str:
        """读取资源内容。"""
        # 根据 URI 找到对应的 client
        client = self._manager.find_client_for_resource(uri)
        if not client:
            raise ValueError(f"Resource not found: {uri}")
        
        content = await client.read_resource(uri)
        return content.text
```

### 5. MCPManager

MCP 总管理器，集成到 Agent。

```python
class MCPManager:
    """MCP 管理器。"""
    
    def __init__(self, config_path: str = None):
        self._clients: Dict[str, MCPClient] = {}
        self._resource_manager: MCPResourceManager = None
        self._config: MCPConfig = None
    
    def load_config(self, path: str) -> None:
        """加载 YAML 配置文件。"""
        self._config = MCPConfig.from_yaml(path)
    
    async def start_all(self) -> None:
        """启动所有已启用的 MCP Server 连接。"""
        for server_config in self._config.servers:
            if server_config.enabled:
                client = MCPClient(server_config)
                await client.connect()
                self._clients[server_config.name] = client
    
    def get_tools(self) -> List[MCPTool]:
        """获取所有 MCP 工具（转换为 MCPTool）。"""
        tools = []
        for client in self._clients.values():
            for schema in client._tools:
                tools.append(MCPTool(client, schema))
        return tools
    
    async def stop_all(self) -> None:
        """关闭所有连接。"""
        for client in self._clients.values():
            await client.close()
```

---

## 配置文件格式

```yaml
# mcp_servers.yaml
servers:
  # 本地 Stdio MCP Server
  filesystem:
    transport: stdio
    command: mcp-server-filesystem
    args:
      - "--root"
      - "/data"
    enabled: true
  
  # 远程 HTTP MCP Server（无认证）
  web_tools:
    transport: http
    url: http://localhost:8080/mcp
    enabled: true
  
  # 远程 HTTP MCP Server（API Key 认证）
  external_api:
    transport: http
    url: https://api.example.com/mcp
    api_key: ${EXTERNAL_API_KEY}  # 从环境变量读取
    enabled: true
```

**配置字段说明：**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `transport` | string | 是 | `stdio` 或 `http` |
| `command` | string | stdio 必需 | MCP Server 命令 |
| `args` | list | 否 | 命令参数 |
| `url` | string | http 必需 | MCP Server URL |
| `api_key` | string | 否 | API Key，支持 `${VAR}` 环境变量引用 |
| `enabled` | bool | 否 | 是否启用，默认 true |

---

## Agent 集成

### 使用方式

```python
from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider

# 创建 Agent
provider = OllamaProvider(model="gpt-4")
agent = Agent(provider=provider)

# 加载 MCP 配置
agent.load_mcp_config("mcp_servers.yaml")

# MCP 工具自动注册，可以直接使用
agent.run("读取 /data/report.txt 的内容")

# 访问 MCP Resources
resources = agent.list_mcp_resources()
content = agent.read_mcp_resource("file:///data/config.json")
```

### Agent 新增方法

```python
class Agent:
    # 新增 MCP 相关方法
    
    def load_mcp_config(self, path: str) -> None:
        """加载 MCP Server 配置文件。"""
        self._mcp_manager = MCPManager()
        self._mcp_manager.load_config(path)
        await self._mcp_manager.start_all()
        
        # 自动注册 MCP 工具
        mcp_tools = self._mcp_manager.get_tools()
        self.add_tools(mcp_tools)
    
    def list_mcp_resources(self, server_name: str = None) -> List[MCPResourceInfo]:
        """列出 MCP Resources。"""
        return self._mcp_manager.resource_manager.list_resources(server_name)
    
    def read_mcp_resource(self, uri: str) -> str:
        """读取 MCP Resource 内容。"""
        return self._mcp_manager.resource_manager.read_resource(uri)
    
    async def close_mcp(self) -> None:
        """关闭所有 MCP 连接。"""
        await self._mcp_manager.stop_all()
```

---

## 文件结构

```
agentforge/
├── mcp/
│   ├── __init__.py          # MCP 模块入口
│   ├── client.py            # MCPClient
│   ├── transport.py         # MCPTransport 抽象基类
│   ├── transports/
│   │   ├── __init__.py
│   │   ├── stdio.py         # StdioTransport
│   │   └── http.py          # HTTPTransport
│   ├── tool.py              # MCPTool
│   ├── resource.py          # MCPResource 相关类型
│   ├── manager.py           # MCPManager
│   ├── config.py            # 配置解析
│   └── types.py             # MCP 类型定义
```

---

## 错误处理

```python
class MCPError(AgentForgeError):
    """MCP 相关错误基类。"""

class MCPConnectionError(MCPError):
    """MCP Server 连接失败。"""

class MCPToolCallError(MCPError):
    """MCP 工具调用失败。"""

class MCPResourceError(MCPError):
    """MCP Resource 访问失败。"""
```

---

## 测试计划

1. **单元测试**
   - MCPConfig 配置解析
   - StdioTransport 进程通信
   - HTTPTransport HTTP 请求
   - MCPTool 工具转换

2. **集成测试**
   - 使用官方 MCP Server（如 filesystem）测试
   - 测试工具调用流程
   - 测试资源访问

3. **错误处理测试**
   - 连接失败场景
   - 工具调用失败
   - 认证失败

---

## 实现优先级

1. **P0 - 核心功能**
   - MCPTransport 抽象和实现（Stdio + HTTP）
   - MCPClient 协议实现
   - MCPTool 工具转换
   - 配置文件解析

2. **P1 - Agent 集成**
   - MCPManager 管理
   - Agent 新增方法
   - 自动工具注册

3. **P2 - 资源支持**
   - MCPResourceManager
   - 资源列表和读取接口

4. **P3 - 完善功能**
   - 错误类型定义
   - 日志记录
   - Demo 示例