"""Agent 集成 MCP 测试。

演示 Agent 如何使用 MCP 工具进行对话。
"""

import asyncio
import os
import sys

sys.path.insert(0, "D:/Projects/novel")

from agentforge import Agent
from agentforge.providers.builtins import OllamaProvider


async def test_agent_with_mcp():
    """测试 Agent 集成 MCP。"""
    print("=" * 60)
    print("Agent 集成 MCP 测试")
    print("=" * 60)

    # 使用 Ollama Provider
    print("\n创建 Agent (Ollama: gemma4:31b-cloud)...")

    provider = OllamaProvider(
        model="gemma4:31b-cloud",
        base_url="http://localhost:11434/v1",
    )

    agent = Agent(
        provider=provider,
    )

    # 添加 MCP Servers
    print("添加 MCP Servers...")
    config_path = "D:/Projects/novel/demo/mcp_config.yaml"
    agent.add_mcp_servers(config_path)

    # 获取 MCP 工具
    mcp_tools = agent.get_mcp_tools()
    print(f"\n已注册的 MCP 工具: {len(mcp_tools)}")
    for tool in mcp_tools:
        print(f"  - {tool.name}: {tool.description[:50]}...")

    # 获取 MCP Manager 状态
    mcp_manager = agent.get_mcp_manager()
    if mcp_manager:
        print(f"\n已连接的 MCP Server: {mcp_manager.get_server_names()}")

    # 运行对话
    print("\n" + "=" * 60)
    print("开始对话测试")
    print("=" * 60)

    # 预取（初始化 Agent 状态）
    agent.prefetch()

    # 测试问题（需要使用搜索工具）
    question = "帮我搜索一下 Python 异步编程的最新教程"
    print(f"\n用户: {question}")
    print("-" * 40)

    try:
        response = agent.run(question, max_iterations=10)
        print(f"\n助手: {response.content}")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

    # 关闭 Agent
    print("\n" + "=" * 60)
    print("关闭 Agent...")
    agent.shutdown()
    print("测试完成")


if __name__ == "__main__":
    # 设置 UTF-8 编码
    if sys.platform == "win32":
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

    asyncio.run(test_agent_with_mcp())