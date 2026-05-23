"""委托系统演示。

展示 AgentForge 的委托系统能力：
- 创建子 Agent
- 单任务委托
- 批量并行委托
- 结果聚合
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider
from agentforge.delegation import DelegationManager, DelegationStrategy


def check_ollama() -> bool:
    """检查 Ollama 服务是否可用。"""
    import requests

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def demo_single_delegation(manager: DelegationManager):
    """演示单任务委托。"""
    print("\n" + "=" * 50)
    print("=== 单任务委托 ===")
    print("=" * 50)

    goal = "解释什么是 REST API，用简单的语言描述"
    print(f"\n任务: {goal}")

    result = manager.delegate(goal=goal)

    print(f"\n状态: {result.status.value}")
    if result.results:
        for i, r in enumerate(result.results):
            print(f"\n--- 子 Agent {i + 1} ---")
            if r.summary:
                print(f"摘要: {r.summary[:200]}...")
            if r.error:
                print(f"错误: {r.error}")


def demo_batch_delegation(manager: DelegationManager):
    """演示批量并行委托。"""
    print("\n" + "=" * 50)
    print("=== 批量并行委托 ===")
    print("=" * 50)

    from agentforge.delegation.config import TaskSpec

    tasks = [
        TaskSpec(goal="简要介绍 Python 编程语言"),
        TaskSpec(goal="简要介绍 JavaScript 编程语言"),
        TaskSpec(goal="简要介绍 Go 编程语言"),
    ]

    print(f"\n任务数量: {len(tasks)}")
    for i, t in enumerate(tasks):
        print(f"  {i + 1}. {t.goal}")

    print("\n执行策略: PARALLEL")
    result = manager.delegate_batch(tasks, strategy=DelegationStrategy.PARALLEL)

    print(f"\n状态: {result.status.value}")
    print(f"总耗时: {result.total_duration:.2f}s")
    print(f"总 Token: 输入={result.total_tokens['input']}, 输出={result.total_tokens['output']}")

    if result.results:
        for i, r in enumerate(result.results):
            print(f"\n--- 任务 {i + 1} ---")
            print(f"状态: {r.status.value}")
            if r.summary:
                print(f"摘要: {r.summary[:150]}...")
            if r.error:
                print(f"错误: {r.error}")


def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 委托系统演示")
    print("=" * 50)

    # 检查 Ollama
    if not check_ollama():
        print("\n❌ 错误: Ollama 服务未运行")
        print("请先启动 Ollama: ollama serve")
        sys.exit(1)

    print("\n✅ Ollama 服务已连接")

    # 创建主 Agent
    provider = OllamaProvider(model="llama3.2")
    agent = Agent(provider=provider)
    print(f"\n📦 主 Agent, 模型: {provider._model}")

    # 创建委托管理器
    manager = DelegationManager(parent_agent=agent)
    print("✅ 委托管理器已创建")

    # 演示单任务委托
    demo_single_delegation(manager)

    # 演示批量并行委托
    demo_batch_delegation(manager)

    print("\n" + "=" * 50)
    print("✅ 委托系统演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
