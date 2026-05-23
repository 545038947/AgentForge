"""委托系统演示。

展示 AgentForge 的委托系统能力：
- 创建子 Agent
- 单任务委托
- 批量并行委托
- 结果聚合
"""

import sys
from pathlib import Path

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hai_agent.delegation import DelegationManager, DelegationStrategy
from hai_agent.delegation.config import TaskSpec, DelegationConfig
from demo.utils import setup_demo, print_section, create_agent
from demo.config import get_config


def demo_single_delegation(manager: DelegationManager):
    """演示单任务委托。"""
    print_section("单任务委托")

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


def demo_batch_delegation(manager: DelegationManager, config):
    """演示批量并行委托。"""
    print_section("批量并行委托")

    tasks = [
        TaskSpec(goal="简要介绍 Python 编程语言"),
        TaskSpec(goal="简要介绍 JavaScript 编程语言"),
        TaskSpec(goal="简要介绍 Go 编程语言"),
    ]

    print(f"\n任务数量: {len(tasks)}")
    for i, t in enumerate(tasks):
        print(f"  {i + 1}. {t.goal}")

    print("\n执行策略: PARALLEL")
    print(f"最大并发: {config.delegation.max_concurrent}")

    result = manager.delegate_batch(
        tasks,
        strategy=DelegationStrategy.PARALLEL,
    )

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

    # 加载配置
    config = get_config()

    # 设置 Demo 环境
    agent, config = setup_demo()
    print(f"📦 主 Agent, 模型: {config.ollama.model}")

    # 创建委托管理器（使用配置）
    delegation_config = DelegationConfig(
        max_depth=config.delegation.max_depth,
        max_concurrent=config.delegation.max_concurrent,
    )
    manager = DelegationManager(
        config=delegation_config,
        parent_agent=agent,
    )
    print("✅ 委托管理器已创建")

    # 演示单任务委托
    demo_single_delegation(manager)

    # 演示批量并行委托
    demo_batch_delegation(manager, config)

    print("\n" + "=" * 50)
    print("✅ 委托系统演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()