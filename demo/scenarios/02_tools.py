"""工具调用演示。

展示 AgentForge 的工具系统能力：
- 工具定义和注册
- Agent 自动选择调用工具
- 工具执行和结果展示
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider
from demo.tools import get_all_demo_tools


def check_ollama() -> bool:
    """检查 Ollama 服务是否可用。"""
    import requests

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def demo_single_tool_call(agent: Agent):
    """演示单工具调用。"""
    print("\n" + "=" * 50)
    print("=== 单工具调用 ===")
    print("=" * 50)

    # 使用 calculator 工具的问题
    prompt = "帮我计算 123 * 456 等于多少？"
    print(f"\n问题: {prompt}")

    response = agent.run(prompt)
    print(f"\n回答: {response.content}")


def demo_weather_tool(agent: Agent):
    """演示天气工具调用。"""
    print("\n" + "=" * 50)
    print("=== 天气查询工具 ===")
    print("=" * 50)

    prompt = "北京今天天气怎么样？"
    print(f"\n问题: {prompt}")

    response = agent.run(prompt)
    print(f"\n回答: {response.content}")


def demo_search_tool(agent: Agent):
    """演示搜索工具调用。"""
    print("\n" + "=" * 50)
    print("=== 搜索工具 ===")
    print("=" * 50)

    prompt = "帮我搜索一下 Python 教程"
    print(f"\n问题: {prompt}")

    response = agent.run(prompt)
    print(f"\n回答: {response.content}")


def demo_tool_info():
    """显示工具信息。"""
    print("\n" + "=" * 50)
    print("=== 已注册工具 ===")
    print("=" * 50)

    tools = get_all_demo_tools()
    for t in tools:
        print(f"\n📦 {t.name}")
        print(f"   描述: {t.description[:50]}...")


def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 工具调用演示")
    print("=" * 50)

    # 检查 Ollama
    if not check_ollama():
        print("\n❌ 错误: Ollama 服务未运行")
        print("请先启动 Ollama: ollama serve")
        sys.exit(1)

    print("\n✅ Ollama 服务已连接")

    # 显示工具信息
    demo_tool_info()

    # 创建带工具的 Agent
    provider = OllamaProvider(model="llama3.2")
    tools = get_all_demo_tools()
    agent = Agent(provider=provider, tools=tools)
    print(f"\n📦 模型: {provider._model}")
    print(f"🔧 工具数量: {len(tools)}")

    # 演示单工具调用
    demo_single_tool_call(agent)

    # 清空上下文
    agent.clear()

    # 演示天气工具
    demo_weather_tool(agent)

    # 清空上下文
    agent.clear()

    # 演示搜索工具
    demo_search_tool(agent)

    print("\n" + "=" * 50)
    print("✅ 工具调用演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
