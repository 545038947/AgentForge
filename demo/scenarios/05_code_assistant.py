"""智能代码助手场景。

真实使用场景：辅助开发者进行代码分析和问题排查。
展示能力：
- 多工具协作（文件读取 + Shell 命令）
- 工具链式调用
- 结果整合和推理
"""

import sys
from pathlib import Path

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentforge import Agent
from agentforge.tools.builtins import FileReadTool, ShellTool
from demo.config import reload_config
from demo.utils import print_section


def create_code_assistant():
    """创建代码助手 Agent。"""
    config = reload_config()

    # 使用内置工具 + MCP 工具
    from agentforge.providers.builtins import OllamaProvider

    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
        timeout=config.ollama.timeout,
    )

    # 注册内置工具
    tools = [
        FileReadTool(),
        ShellTool(),
    ]

    agent = Agent(provider=provider, tools=tools)

    # 加载 MCP Servers（如 bing-search）
    if config.mcp.enabled and config.mcp.config_path:
        mcp_config_path = Path(__file__).parent.parent / config.mcp.config_path
        if mcp_config_path.exists():
            agent.add_mcp_servers(str(mcp_config_path))

    return agent, config


def demo_analyze_code(agent):
    """演示：分析代码文件。"""
    print_section("场景 1: 分析代码文件")

    prompt = """
请帮我分析 agentforge/agent.py 文件的主要结构：
1. 读取这个文件
2. 找出主要的类和方法
3. 总结这个文件的核心职责

请用中文回答。
"""
    print(f"\n用户请求: {prompt.strip()}")

    response = agent.run(prompt, max_iterations=10)
    print(f"\n助手回答:\n{response.content}")


def demo_check_project(agent):
    """演示：检查项目状态。"""
    print_section("场景 2: 检查项目状态")

    prompt = """
请帮我检查当前项目的状态：
1. 列出项目根目录的文件结构
2. 查看 README.md 的内容
3. 检查是否有测试文件

请用中文总结项目概况。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=10)
    print(f"\n助手回答:\n{response.content}")


def demo_find_and_fix(agent):
    """演示：查找和理解问题。"""
    print_section("场景 3: 查找和理解代码")

    prompt = """
我想了解 AgentForge 框架中工具是如何被调用的：
1. 找到工具调用的相关代码
2. 解释工具调用的流程
3. 说明如何添加自定义工具

请详细说明。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=15)
    print(f"\n助手回答:\n{response.content}")


def demo_with_mcp_search(agent):
    """演示：结合 MCP 搜索。"""
    print_section("场景 4: 结合网络搜索解决问题")

    # 检查 MCP 是否可用
    mcp_tools = agent.get_mcp_tools()
    if not mcp_tools:
        print("\n⚠️  MCP 工具未加载，跳过此场景")
        print("   请确保 demo/config.yaml 中 mcp.enabled: true")
        return

    print(f"\n已连接 MCP 工具: {[t.name for t in mcp_tools]}")

    prompt = """
我想了解 Python 异步编程的最佳实践：
1. 使用 bing_search 工具搜索 "Python asyncio 最佳实践 2024"
2. 总结搜索结果中的关键建议
3. 给出学习建议

请用中文回答。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=15)
    print(f"\n助手回答:\n{response.content}")


def main():
    """主函数。"""
    print("=" * 60)
    print("🤖 智能代码助手 - 真实场景演示")
    print("=" * 60)
    print("""
本演示展示 AgentForge 在真实开发场景中的应用：
- 读取和分析代码文件
- 执行 Shell 命令检查项目状态
- 结合 MCP 搜索获取网络信息
- 多工具协作完成复杂任务
""")

    print("\n正在初始化代码助手...")
    agent, config = create_code_assistant()

    print(f"📦 模型: {config.ollama.model}")
    print(f"🌐 服务: {config.ollama.base_url}")
    print(f"🔧 内置工具: FileRead, Shell")

    mcp_tools = agent.get_mcp_tools()
    if mcp_tools:
        print(f"🔌 MCP 工具: {[t.name for t in mcp_tools]}")

    # 运行演示
    try:
        demo_analyze_code(agent)
        demo_check_project(agent)
        demo_find_and_fix(agent)
        demo_with_mcp_search(agent)
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        agent.shutdown()

    print("\n" + "=" * 60)
    print("✅ 演示完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
