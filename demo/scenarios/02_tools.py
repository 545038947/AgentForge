"""工具调用演示。

展示 AgentForge 的工具系统能力：
- 工具定义和注册
- Agent 自动选择调用工具
- 工具执行和结果展示
"""

import sys
from pathlib import Path

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demo.utils import setup_demo, print_section, create_agent
from demo.tools import get_all_demo_tools


def demo_single_tool_call(agent):
    """演示单工具调用。"""
    print_section("单工具调用")

    prompt = "帮我计算 123 * 456 等于多少？"
    print(f"\n问题: {prompt}")

    response = agent.run(prompt)
    print(f"\n回答: {response.content}")


def demo_weather_tool(agent):
    """演示天气工具调用。"""
    print_section("天气查询工具")

    prompt = "北京今天天气怎么样？"
    print(f"\n问题: {prompt}")

    response = agent.run(prompt)
    print(f"\n回答: {response.content}")


def demo_search_tool(agent):
    """演示搜索工具调用。"""
    print_section("搜索工具")

    prompt = "帮我搜索一下 Python 教程"
    print(f"\n问题: {prompt}")

    response = agent.run(prompt)
    print(f"\n回答: {response.content}")


def demo_tool_info():
    """显示工具信息。"""
    print_section("已注册工具")

    tools = get_all_demo_tools()
    for t in tools:
        print(f"\n📦 {t.name}")
        print(f"   描述: {t.description[:50]}...")


def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 工具调用演示")
    print("=" * 50)

    # 显示工具信息
    demo_tool_info()

    # 设置 Demo 环境（带工具）
    agent, config = create_agent(tools=get_all_demo_tools())
    print(f"\n📦 模型: {config.ollama.model}")
    print(f"🔧 工具数量: {len(get_all_demo_tools())}")

    # 演示单工具调用
    demo_single_tool_call(agent)
    agent.clear()

    # 演示天气工具
    demo_weather_tool(agent)
    agent.clear()

    # 演示搜索工具
    demo_search_tool(agent)

    print("\n" + "=" * 50)
    print("✅ 工具调用演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()