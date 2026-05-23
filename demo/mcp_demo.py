"""
MCP (Model Context Protocol) Demo

演示如何使用 AgentForge 的 MCP 支持：
1. 配置 MCP Server
2. 连接 MCP Server
3. 使用 MCP 工具

使用方法：
    python demo/mcp_demo.py
"""

import asyncio
from pathlib import Path

from agentforge import Agent
from agentforge.mcp import (
    MCPManager,
    MCPConfig,
    MCPServerConfig,
)


def demo_mcp_config():
    """演示 MCP 配置。"""
    print("=" * 60)
    print("MCP 配置演示")
    print("=" * 60)

    # 方式 1: 从字典创建配置
    config_data = {
        "servers": {
            "example-server": {
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "example_mcp_server"],
                "enabled": True,
            },
            "remote-server": {
                "transport": "http",
                "url": "https://api.example.com/mcp",
                "api_key": "${EXAMPLE_API_KEY}",  # 从环境变量读取
                "enabled": True,
            },
        }
    }

    config = MCPConfig.from_dict(config_data)

    print(f"\n已配置 {len(config.servers)} 个 MCP Server:")
    for server in config.servers:
        print(f"  - {server.name}: {server.transport} transport")
        if server.transport == "stdio":
            print(f"    命令: {server.command} {' '.join(server.args)}")
        elif server.transport == "http":
            print(f"    URL: {server.url}")
            if server.api_key:
                print(f"    API Key: {'*' * 8} (已配置)")

    # 方式 2: 从 YAML 文件加载配置
    yaml_path = Path(__file__).parent / "mcp_config.yaml"
    if yaml_path.exists():
        print(f"\n从 YAML 文件加载配置: {yaml_path}")
        config = MCPConfig.from_yaml(str(yaml_path))
        print(f"已加载 {len(config.servers)} 个 MCP Server")


async def demo_mcp_manager():
    """演示 MCP Manager 使用。"""
    print("\n" + "=" * 60)
    print("MCP Manager 演示")
    print("=" * 60)

    # 创建 MCP Manager
    manager = MCPManager()

    # 配置示例 MCP Server（这里使用模拟配置）
    config_data = {
        "servers": {
            # 注意：这个配置需要实际的 MCP Server 才能连接
            # "my-server": {
            #     "transport": "stdio",
            #     "command": "python",
            #     "args": ["-m", "my_mcp_server"],
            # },
        }
    }

    # 初始化 MCP Servers
    print("\n初始化 MCP Servers...")
    await manager.initialize_from_dict(config_data)

    # 获取已连接的 Server
    server_names = manager.get_server_names()
    print(f"已连接的 Server: {server_names}")

    # 获取所有工具
    tools = manager.get_all_tools()
    print(f"已注册的工具数量: {len(tools)}")

    for tool in tools:
        print(f"  - {tool.name}: {tool.description[:50]}...")

    # 关闭连接
    await manager.shutdown()
    print("\nMCP Manager 已关闭")


def demo_agent_mcp():
    """演示 Agent 集成 MCP。"""
    print("\n" + "=" * 60)
    print("Agent 集成 MCP 演示")
    print("=" * 60)

    print("\n注意: 需要 API Key 才能创建 Agent")
    print("设置环境变量后可运行完整演示")

    # 演示代码（需要 API Key）
    # agent = Agent(model="gpt-4")
    #
    # # 方式 1: 从 YAML 配置文件添加 MCP Servers
    # yaml_path = Path(__file__).parent / "mcp_config.yaml"
    # if yaml_path.exists():
    #     print(f"\n从 YAML 文件添加 MCP Servers: {yaml_path}")
    #     agent.add_mcp_servers(str(yaml_path))
    #
    # # 方式 2: 从字典配置添加 MCP Servers
    # config_data = {
    #     "servers": {
    #         "my-server": {
    #             "transport": "stdio",
    #             "command": "python",
    #             "args": ["-m", "my_mcp_server"],
    #         },
    #     }
    # }
    # agent.add_mcp_servers_from_dict(config_data)
    #
    # # 获取 MCP 工具
    # mcp_tools = agent.get_mcp_tools()
    # print(f"\n已注册的 MCP 工具: {len(mcp_tools)}")

    print("\n提示: 要使用 MCP 工具，请配置实际的 MCP Server")
    print("参考: https://modelcontextprotocol.io")


def create_example_yaml():
    """创建示例 YAML 配置文件。"""
    yaml_content = """# MCP Server 配置示例
# 参考: https://modelcontextprotocol.io

servers:
  # Stdio Transport 示例
  # 通过进程 stdin/stdout 与 MCP Server 通信
  example-stdio:
    transport: stdio
    command: python
    args:
      - "-m"
      - "example_mcp_server"
    env:
      PYTHONPATH: "/path/to/mcp/server"
    enabled: true

  # HTTP Transport 示例
  # 通过 HTTP/SSE 与远程 MCP Server 通信
  example-http:
    transport: http
    url: https://api.example.com/mcp
    api_key: ${EXAMPLE_API_KEY}  # 从环境变量读取
    headers:
      X-Custom-Header: custom-value
    enabled: true

  # 禁用的 Server 示例
  disabled-server:
    transport: stdio
    command: python
    args:
      - "-m"
      - "disabled_server"
    enabled: false  # 不会连接
"""

    yaml_path = Path(__file__).parent / "mcp_config.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    print(f"\n已创建示例配置文件: {yaml_path}")


def main():
    """运行演示。"""
    print("AgentForge MCP 支持 Demo")
    print("=" * 60)

    # 创建示例 YAML 配置
    create_example_yaml()

    # 演示配置
    demo_mcp_config()

    # 演示 MCP Manager
    asyncio.run(demo_mcp_manager())

    # 演示 Agent 集成
    demo_agent_mcp()

    print("\n" + "=" * 60)
    print("Demo 完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
