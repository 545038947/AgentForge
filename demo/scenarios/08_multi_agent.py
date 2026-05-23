"""多 Agent 协作场景。

真实使用场景：多个专业 Agent 协作完成复杂任务。
展示能力：
- Agent 委托机制
- 专业 Agent 配置
- 任务分解和协作
"""

import sys
from pathlib import Path

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hai_agent import Agent
from hai_agent.tools.builtins import DelegateTool, FileReadTool, FileWriteTool
from demo.config import reload_config
from demo.utils import print_section


def create_coordinator_agent():
    """创建协调者 Agent。"""
    config = reload_config()

    from hai_agent.providers.builtins import OllamaProvider

    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
        timeout=config.ollama.timeout,
    )

    # 协调者拥有委托工具
    tools = [
        DelegateTool(),
        FileReadTool(),
        FileWriteTool(),
    ]

    agent = Agent(
        provider=provider,
        tools=tools,
    )

    # 加载 MCP
    if config.mcp.enabled and config.mcp.config_path:
        mcp_config_path = Path(__file__).parent.parent / config.mcp.config_path
        if mcp_config_path.exists():
            agent.add_mcp_servers(str(mcp_config_path))

    return agent, config


def demo_simple_delegation(agent):
    """演示：简单任务委托。"""
    print_section("场景 1: 任务分解和委托")

    prompt = """
我需要完成一个项目分析任务，请帮我：
1. 分析项目的目录结构
2. 统计 Python 文件数量
3. 找出主要的模块

你可以使用 delegate 工具委托子任务给专业 Agent。
"""
    print(f"\n用户请求: {prompt.strip()}")

    response = agent.run(prompt, max_iterations=15)
    print(f"\n助手回答:\n{response.content}")


def demo_code_review_workflow(agent):
    """演示：代码审查工作流。"""
    print_section("场景 2: 代码审查工作流")

    prompt = """
请帮我完成一个简单的代码审查：
1. 读取 agentforge/tools/base.py 文件
2. 分析代码结构和方法
3. 提出改进建议

你可以使用委托来分解这个任务。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=20)
    print(f"\n助手回答:\n{response.content}")


def demo_documentation_workflow(agent):
    """演示：文档生成工作流。"""
    print_section("场景 3: 文档生成工作流")

    prompt = """
请帮我为 agentforge/mcp/client.py 生成文档：
1. 读取源代码
2. 分析主要类和方法
3. 生成 Markdown 格式的文档

请将生成的文档写入 output/mcp_client_doc.md 文件。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=25)
    print(f"\n助手回答:\n{response.content}")


def demo_research_and_write(agent):
    """演示：研究并写作。"""
    print_section("场景 4: 研究并写作")

    # 检查 MCP
    mcp_tools = agent.get_mcp_tools()
    search_tools = [t for t in mcp_tools if "search" in t.name.lower()]

    if not search_tools:
        print("\n⚠️  MCP 搜索工具未加载，使用简化场景")
        prompt = """
请帮我写一份关于 Python 上下文管理器的学习笔记：
1. 解释什么是上下文管理器
2. 说明 __enter__ 和 __exit__ 方法
3. 给出使用 with 语句的示例
4. 列出常见的使用场景

请将笔记写入 output/context_manager.md 文件。
"""
    else:
        prompt = """
请帮我研究并写一份关于 Python 类型提示的学习笔记：
1. 使用搜索工具查找 Python 类型提示的最新信息
2. 整理类型提示的基本语法
3. 介绍 typing 模块的常用类型
4. 给出最佳实践建议

请将笔记写入 output/type_hints.md 文件。
"""

    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=30)
    print(f"\n助手回答:\n{response.content}")


def show_output_files():
    """显示生成的输出文件。"""
    print_section("生成的文件")

    output_dir = Path(__file__).parent.parent / "output"
    if not output_dir.exists():
        print("\n(无输出文件)")
        return

    for file in output_dir.glob("*.md"):
        print(f"\n📄 {file.name}:")
        print("-" * 40)
        content = file.read_text(encoding="utf-8")
        print(content[:500] if content else "(空)")
        if len(content) > 500:
            print(f"\n... 共 {len(content)} 字符")


def main():
    """主函数。"""
    print("=" * 60)
    print("🤝 多 Agent 协作 - 真实场景演示")
    print("=" * 60)
    print("""
本演示展示 AgentForge 的多 Agent 协作能力：
- 任务分解和委托
- 专业 Agent 协作
- 文件读写操作
- 复杂工作流执行
""")

    # 创建输出目录
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    print("\n正在初始化协调者 Agent...")
    agent, config = create_coordinator_agent()

    print(f"📦 模型: {config.ollama.model}")
    print(f"🔧 工具: Delegate, FileRead, FileWrite")

    mcp_tools = agent.get_mcp_tools()
    if mcp_tools:
        print(f"🔌 MCP 工具: {[t.name for t in mcp_tools]}")

    # 运行演示
    try:
        demo_simple_delegation(agent)
        demo_code_review_workflow(agent)
        demo_documentation_workflow(agent)
        demo_research_and_write(agent)

        # 显示输出文件
        show_output_files()

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