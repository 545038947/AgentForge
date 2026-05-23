"""研究助手场景。

真实使用场景：辅助用户进行信息收集和整理。
展示能力：
- MCP 工具调用（Bing 搜索 + 网页抓取）
- 信息整合和总结
- 多步骤任务完成
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
from agentforge.tools.builtins import WebFetchTool
from demo.config import reload_config
from demo.utils import print_section


def create_research_assistant():
    """创建研究助手 Agent。"""
    config = reload_config()

    from agentforge.providers.builtins import OllamaProvider

    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
        timeout=config.ollama.timeout,
    )

    # 注册网页抓取工具
    tools = [WebFetchTool()]

    agent = Agent(provider=provider, tools=tools)

    # 加载 MCP Servers（必须包含 bing-search）
    if config.mcp.enabled and config.mcp.config_path:
        mcp_config_path = Path(__file__).parent.parent / config.mcp.config_path
        if mcp_config_path.exists():
            agent.add_mcp_servers(str(mcp_config_path))

    return agent, config


def check_mcp_available(agent):
    """检查 MCP 工具是否可用。"""
    mcp_tools = agent.get_mcp_tools()
    search_tools = [t for t in mcp_tools if "search" in t.name.lower()]

    if not search_tools:
        print("⚠️  警告: MCP 搜索工具未加载")
        print("   请确保:")
        print("   1. demo/config.yaml 中 mcp.enabled: true")
        print("   2. demo/mcp_config.yaml 包含 bing-search 配置")
        print("   3. 已安装 npx 和 bing-cn-mcp 包")
        return False

    print(f"✅ 已加载 MCP 搜索工具: {search_tools[0].name}")
    return True


def demo_simple_search(agent):
    """演示：简单搜索并总结。"""
    print_section("场景 1: 搜索并总结信息")

    prompt = """
请帮我搜索关于 "Python 机器学习库" 的信息：
1. 使用搜索工具查找相关内容
2. 列出主要的机器学习库
3. 简要介绍每个库的特点

请用中文回答。
"""
    print(f"\n用户请求: {prompt.strip()}")

    response = agent.run(prompt, max_iterations=10)
    print(f"\n助手回答:\n{response.content}")


def demo_deep_research(agent):
    """演示：深度研究流程。"""
    print_section("场景 2: 深度研究流程")

    prompt = """
我想深入了解 "LangChain 框架"：
1. 搜索 LangChain 的基本介绍
2. 找出它的核心功能和特点
3. 了解它的应用场景
4. 总结学习路径建议

请详细回答。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=15)
    print(f"\n助手回答:\n{response.content}")


def demo_compare_research(agent):
    """演示：对比研究。"""
    print_section("场景 3: 对比研究")

    prompt = """
请帮我对比研究两个 Python Web 框架：
1. 搜索 "FastAPI 框架特点"
2. 搜索 "Flask 框架特点"
3. 从性能、易用性、适用场景等方面对比
4. 给出选择建议

请用表格形式展示对比结果。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=20)
    print(f"\n助手回答:\n{response.content}")


def demo_topic_summary(agent):
    """演示：主题总结。"""
    print_section("场景 4: 生成研究报告")

    prompt = """
请帮我生成一份关于 "AI Agent 开发" 的简要研究报告：
1. 搜索什么是 AI Agent
2. 了解主流的 Agent 框架
3. 分析 Agent 开发的关键技术
4. 总结当前发展趋势

报告格式：
- 标题
- 概述
- 关键技术
- 主流框架
- 发展趋势
- 参考资料

请用中文撰写。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=25)
    print(f"\n助手回答:\n{response.content}")


def main():
    """主函数。"""
    print("=" * 60)
    print("📚 研究助手 - 真实场景演示")
    print("=" * 60)
    print("""
本演示展示 AgentForge 在信息收集和研究场景中的应用：
- 使用 MCP Bing 搜索获取信息
- 多次搜索整合信息
- 生成结构化研究报告
- 对比分析和总结
""")

    print("\n正在初始化研究助手...")
    agent, config = create_research_assistant()

    print(f"📦 模型: {config.ollama.model}")
    print(f"🌐 服务: {config.ollama.base_url}")

    # 检查 MCP
    if not check_mcp_available(agent):
        print("\n❌ 无法运行演示，请先配置 MCP")
        return

    # 运行演示
    try:
        demo_simple_search(agent)
        demo_deep_research(agent)
        demo_compare_research(agent)
        demo_topic_summary(agent)
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