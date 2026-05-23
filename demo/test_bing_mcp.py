"""测试 Bing Search MCP Server。"""

import asyncio
import sys

sys.path.insert(0, "D:/Projects/novel")

from agentforge.mcp import MCPManager, MCPServerConfig, MCPConfig


async def test_bing_mcp():
    """测试 Bing Search MCP Server。"""
    print("=" * 60)
    print("测试 Bing Search MCP Server")
    print("=" * 60)

    # 创建配置
    config = MCPConfig(servers=[
        MCPServerConfig(
            name="bing-search",
            transport="stdio",
            command="cmd",
            args=["/c", "npx", "-y", "bing-cn-mcp"],
            enabled=True,
        )
    ])

    print(f"\n配置: {config.servers[0].name}")
    print(f"命令: {config.servers[0].command} {' '.join(config.servers[0].args)}")

    # 创建 Manager 并初始化
    manager = MCPManager()

    print("\n连接 MCP Server...")
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
            print(f"  描述: {tool.description[:200]}...")
            if tool.parameters:
                props = tool.parameters.get("properties", {})
                required = tool.parameters.get("required", [])
                print(f"  参数: {list(props.keys())}")
                print(f"  必填: {required}")

        # 测试调用工具
        if tools:
            print("\n" + "=" * 60)
            print("测试调用 bing_search 工具...")

            # 找到搜索工具
            search_tool = None
            for tool in tools:
                if "search" in tool.name.lower():
                    search_tool = tool
                    break

            if search_tool:
                try:
                    result = await manager.call_tool(
                        search_tool.name,
                        {"query": "Python 编程"}
                    )
                    # 安全输出（处理编码问题）
                    safe_result = result.encode('utf-8', errors='replace').decode('utf-8')
                    print(f"搜索结果: {safe_result[:500]}...")
                except Exception as e:
                    print(f"调用失败: {e}")
            else:
                print("未找到搜索工具")

        # 关闭连接
        await manager.shutdown()
        print("\nMCP Manager 已关闭")

    except Exception as e:
        print(f"\n连接失败: {e}")
        import traceback
        traceback.print_exc()
        await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(test_bing_mcp())