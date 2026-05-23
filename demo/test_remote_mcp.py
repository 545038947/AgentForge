"""测试远程 MCP Server 连接。"""

import asyncio
import sys

sys.path.insert(0, "D:/Projects/novel")

from agentforge.mcp import MCPManager, MCPConfig


async def test_remote_mcp():
    """测试连接远程 MCP Server。"""
    print("=" * 60)
    print("测试远程 MCP Server 连接")
    print("=" * 60)

    # 加载配置
    config_path = "D:/Projects/novel/demo/mcp_config.yaml"
    print(f"\n加载配置: {config_path}")
    config = MCPConfig.from_yaml(config_path)

    print(f"已配置 {len(config.servers)} 个 MCP Server:")
    for server in config.servers:
        print(f"  - {server.name}: {server.transport}")
        if server.url:
            print(f"    URL: {server.url}")

    # 创建 Manager 并初始化
    manager = MCPManager()

    print("\n连接 MCP Servers...")
    try:
        await manager.initialize(config)

        # 获取连接状态
        server_names = manager.get_server_names()
        print(f"已连接的 Server: {server_names}")

        # 获取工具列表
        tools = manager.get_all_tools()
        print(f"\n已注册的工具数量: {len(tools)}")

        for tool in tools:
            print(f"\n工具: {tool.name}")
            print(f"  描述: {tool.description[:100]}...")
            print(f"  参数: {tool.parameters}")

        # 测试调用工具（如果有）
        if tools:
            print("\n" + "=" * 60)
            print("尝试调用第一个工具...")
            first_tool = tools[0]
            print(f"工具名: {first_tool.name}")

            # 尝试获取工具 schema
            schema = first_tool.get_schema()
            print(f"Schema: {schema}")

        # 关闭连接
        await manager.shutdown()
        print("\nMCP Manager 已关闭")

    except Exception as e:
        print(f"\n连接失败: {e}")
        import traceback
        traceback.print_exc()
        await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(test_remote_mcp())