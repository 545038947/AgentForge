"""自定义专家 Agent 演示。

展示 AgentForge 的专家 Agent 配置能力：
- 使用 AgentProfile 声明式定义专家角色
- ProfileRegistry 管理专家注册表
- 从 YAML 配置文件加载专家定义（含继承）
- DelegationManager + TaskSpec 委托任务给专家
- 多专家协作完成复杂任务
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
from hai_agent.profiles import AgentProfile, ProfileRegistry
from demo.utils import setup_demo, print_section
from demo.config import get_config


# ---------------------------------------------------------------------------
# 专家定义
# ---------------------------------------------------------------------------

def create_expert_profiles() -> ProfileRegistry:
    """创建专家 Agent 的 Profile 注册表。

    每个 Profile 定义了一个专家的角色、能力和行为约束。

    Returns:
        包含多个专家 Profile 的注册表
    """
    registry = ProfileRegistry()

    # 研究专家：擅长信息检索和整理
    registry.register(AgentProfile(
        name="researcher",
        description="研究专家，擅长信息检索、分析和整理",
        temperature=0.5,
        max_tokens=2048,
        system_prompt=(
            "你是一位专业的研究分析师。你的职责是：\n"
            "1. 深入分析问题，提取关键信息\n"
            "2. 从多个角度审视问题\n"
            "3. 提供结构化的分析报告\n"
            "请用清晰的标题和要点组织你的回答。"
        ),
    ))

    # 写作专家：擅长内容创作和润色
    registry.register(AgentProfile(
        name="writer",
        description="写作专家，擅长内容创作、润色和风格调整",
        temperature=0.8,
        max_tokens=2048,
        system_prompt=(
            "你是一位资深内容作家。你的职责是：\n"
            "1. 将研究结果转化为流畅的文章\n"
            "2. 注重文字表达和逻辑连贯\n"
            "3. 保持专业但易读的写作风格\n"
            "请用自然的段落组织内容，避免过于技术化。"
        ),
    ))

    # 代码专家：擅长编程和技术分析
    registry.register(AgentProfile(
        name="coder",
        description="代码专家，擅长编程、代码审查和技术方案设计",
        temperature=0.3,
        max_tokens=2048,
        system_prompt=(
            "你是一位高级软件工程师。你的职责是：\n"
            "1. 编写高质量、可维护的代码\n"
            "2. 进行代码审查并提出改进建议\n"
            "3. 设计合理的技术方案\n"
            "回答时请提供具体的代码示例和解释。"
        ),
    ))

    # 评审专家：擅长质量检查和风险识别
    registry.register(AgentProfile(
        name="reviewer",
        description="评审专家，擅长质量检查、风险识别和改进建议",
        temperature=0.2,
        max_tokens=1024,
        system_prompt=(
            "你是一位严谨的质量评审员。你的职责是：\n"
            "1. 审查内容的准确性和完整性\n"
            "2. 识别潜在的问题和风险\n"
            "3. 提出具体的改进建议\n"
            "请以清单形式列出发现的问题和建议。"
        ),
    ))

    return registry


def show_expert_profiles(registry: ProfileRegistry):
    """展示注册表中的专家 Profile。"""
    print_section("专家 Profile 注册表")

    profiles = registry.list_profiles()
    print(f"\n已注册 {len(profiles)} 个专家：\n")

    for name in profiles:
        profile = registry.get(name)
        if profile:
            print(f"  [{profile.name}] {profile.description}")
            print(f"    温度: {profile.temperature}, 最大 Token: {profile.max_tokens}")
            if profile.system_prompt:
                prompt_preview = profile.system_prompt[:80].replace("\n", " ")
                print(f"    提示: {prompt_preview}...")
            print()


# ---------------------------------------------------------------------------
# 演示场景
# ---------------------------------------------------------------------------

def demo_single_expert(manager: DelegationManager, registry: ProfileRegistry):
    """演示：单专家委托。"""
    print_section("场景 1: 委托研究专家")

    task = TaskSpec(
        goal="分析 Python 和 Rust 两种编程语言的优缺点，给出对比总结",
        agent_profile="researcher",
    )

    print(f"\n任务: {task.goal}")
    print(f"专家: {task.agent_profile}")

    result = manager.delegate(goal=task.goal)

    print(f"\n状态: {result.status.value}")
    if result.results:
        for r in result.results:
            if r.summary:
                print(f"\n{r.summary[:500]}")
            if r.error:
                print(f"错误: {r.error}")


def demo_sequential_experts(manager: DelegationManager):
    """演示：顺序多专家协作。

    研究专家先分析，写作专家再润色。
    """
    print_section("场景 2: 顺序多专家协作")

    tasks = [
        TaskSpec(
            goal="研究 Python 类型提示的核心概念和最佳实践",
            agent_profile="researcher",
            system_prompt="请重点关注类型提示的实际应用场景。",
        ),
        TaskSpec(
            goal="基于上一阶段的研究结果，写一篇关于 Python 类型提示的简明教程",
            agent_profile="writer",
            system_prompt="面向有基础 Python 经验的开发者，风格简洁实用。",
        ),
    ]

    print(f"\n工作流: researcher → writer")
    print(f"任务数量: {len(tasks)}")
    for i, t in enumerate(tasks):
        print(f"  {i + 1}. [{t.agent_profile}] {t.goal}")

    result = manager.delegate_batch(tasks, strategy=DelegationStrategy.SEQUENTIAL)

    print(f"\n状态: {result.status.value}")
    print(f"总耗时: {result.total_duration:.2f}s")
    if result.results:
        for i, r in enumerate(result.results):
            print(f"\n--- 阶段 {i + 1} ---")
            print(f"状态: {r.status.value}")
            if r.summary:
                print(f"{r.summary[:400]}")
            if r.error:
                print(f"错误: {r.error}")


def demo_parallel_experts(manager: DelegationManager):
    """演示：并行多专家分析。

    多个专家同时从不同角度分析同一问题。
    """
    print_section("场景 3: 并行多专家分析")

    tasks = [
        TaskSpec(
            goal="从架构设计角度，评估使用微服务架构开发一个电商平台的优劣",
            agent_profile="researcher",
        ),
        TaskSpec(
            goal="从代码实现角度，评估使用微服务架构开发一个电商平台的优劣",
            agent_profile="coder",
        ),
        TaskSpec(
            goal="从风险和质量角度，评估使用微服务架构开发一个电商平台的优劣",
            agent_profile="reviewer",
        ),
    ]

    print(f"\n并行分析: researcher | coder | reviewer")
    print(f"任务数量: {len(tasks)}")
    for i, t in enumerate(tasks):
        print(f"  {i + 1}. [{t.agent_profile}] {t.goal}")

    result = manager.delegate_batch(tasks, strategy=DelegationStrategy.PARALLEL)

    print(f"\n状态: {result.status.value}")
    print(f"总耗时: {result.total_duration:.2f}s")
    print(f"总 Token: 输入={result.total_tokens['input']}, 输出={result.total_tokens['output']}")

    if result.results:
        for i, r in enumerate(result.results):
            print(f"\n--- {tasks[i].agent_profile} 观点 ---")
            print(f"状态: {r.status.value}")
            if r.summary:
                print(f"{r.summary[:300]}")
            if r.error:
                print(f"错误: {r.error}")


def demo_expert_with_custom_prompt(manager: DelegationManager):
    """演示：自定义系统提示覆盖专家行为。"""
    print_section("场景 4: 自定义系统提示覆盖")

    task = TaskSpec(
        goal="为 Python 异步编程写一个快速入门指南",
        agent_profile="coder",
        system_prompt="请用中文回答，面向初学者，提供可运行的代码示例。",
        temperature=0.6,
    )

    print(f"\n任务: {task.goal}")
    print(f"专家: {task.agent_profile}")
    print(f"温度覆盖: {task.temperature}")
    print(f"自定义提示: {task.system_prompt}")

    result = manager.delegate(goal=task.goal)

    print(f"\n状态: {result.status.value}")
    if result.results:
        for r in result.results:
            if r.summary:
                print(f"\n{r.summary[:400]}")
            if r.error:
                print(f"错误: {r.error}")


# ---------------------------------------------------------------------------
# 从 YAML 配置文件加载专家
# ---------------------------------------------------------------------------

def create_yaml_registry() -> ProfileRegistry:
    """从 YAML 配置文件创建专家注册表。

    与代码定义不同，YAML 配置支持：
    - extends 继承：共享基础配置
    - 热重载：运行时更新专家定义
    - 外部管理：非开发者也可修改专家行为

    Returns:
        从 expert_profiles.yaml 加载的注册表
    """
    config_path = Path(__file__).parent.parent / "expert_profiles.yaml"
    if not config_path.exists():
        print(f"⚠️  配置文件未找到: {config_path}")
        return ProfileRegistry()

    registry = ProfileRegistry(config_paths=[config_path])
    return registry


def show_yaml_profiles(registry: ProfileRegistry):
    """展示从 YAML 加载的专家 Profile，包括继承关系。"""
    print_section("YAML 配置文件加载的专家")

    profiles = registry.list_profiles()
    print(f"\n从配置文件加载 {len(profiles)} 个专家：\n")

    for name in profiles:
        profile = registry.get(name)
        if not profile or name.startswith("_"):
            continue
        print(f"  [{profile.name}] {profile.description}")
        if profile.extends:
            print(f"    继承: {profile.extends}")
        print(f"    温度: {profile.temperature}, 最大 Token: {profile.max_tokens}")
        if profile.system_prompt:
            prompt_preview = profile.system_prompt[:60].replace("\n", " ")
            print(f"    提示: {prompt_preview}...")
        print()


def demo_yaml_inheritance():
    """演示：YAML 配置的继承机制。"""
    print_section("场景 5: YAML 继承与热重载")

    registry = create_yaml_registry()

    # 展示继承解析
    researcher = registry.get("researcher")
    if researcher:
        print("\nresearcher 的继承解析结果：")
        print(f"  温度: {researcher.temperature}（覆盖 _base-reasoner 的 0.3）")
        print(f"  最大 Token: {researcher.max_tokens}（继承 _base-reasoner 的 2048）")
        print(f"  extends 已清除: {researcher.extends}")

    # 展示基础模板（以 _ 开头，不参与委托）
    base = registry.get("_base-reasoner")
    if base:
        print(f"\n_base-reasoner 模板存在: {base.name}")
        print(f"  （下划线前缀表示仅供继承，不直接参与委托）")

    # 热重载演示
    print("\n热重载演示：")
    print(f"  重载前 translator: {registry.get('translator').description if registry.get('translator') else 'None'}")
    registry.reload("translator")
    print(f"  重载后 translator: {registry.get('translator').description if registry.get('translator') else 'None'}")
    print("  （运行时修改 YAML 文件后调用 reload 即可生效）")


def demo_yaml_expert_delegation(agent):
    """演示：使用 YAML 配置的专家执行任务。"""
    print_section("场景 6: 使用 YAML 专家执行任务")

    config_path = Path(__file__).parent.parent / "expert_profiles.yaml"
    if not config_path.exists():
        print("⚠️  配置文件未找到，跳过此场景")
        return

    # 从 YAML 创建注册表
    yaml_registry = ProfileRegistry(config_paths=[config_path])
    config = get_config()
    delegation_config = DelegationConfig(
        max_depth=config.delegation.max_depth,
        max_concurrent=config.delegation.max_concurrent,
    )
    manager = DelegationManager(
        config=delegation_config,
        parent_agent=agent,
        profile_registry=yaml_registry,
    )

    # 翻译专家
    task_translate = TaskSpec(
        goal="将以下内容翻译为英文：AgentForge 是一个灵活的 Agent 框架，支持多种大模型提供商。",
        agent_profile="translator",
    )
    print(f"\n任务: {task_translate.goal}")
    print(f"专家: {task_translate.agent_profile}")

    result = manager.delegate(goal=task_translate.goal)
    print(f"\n状态: {result.status.value}")
    if result.results:
        for r in result.results:
            if r.summary:
                print(f"翻译结果:\n{r.summary[:400]}")
            if r.error:
                print(f"错误: {r.error}")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 自定义专家 Agent 演示")
    print("=" * 50)
    print("""
本演示展示 AgentForge 的专家 Agent 配置能力：
- AgentProfile 声明式定义专家角色
- ProfileRegistry 管理专家注册表
- 从 YAML 配置文件加载专家定义（含继承）
- DelegationManager 委托任务给专家
- 多专家协作（顺序/并行）
- 自定义系统提示和参数覆盖
- YAML 继承机制与热重载
""")

    # 创建专家 Profile 注册表
    registry = create_expert_profiles()
    show_expert_profiles(registry)

    # 设置 Demo 环境
    agent, config = setup_demo()
    print(f"📦 主 Agent, 模型: {config.ollama.model}")

    # 创建委托管理器
    delegation_config = DelegationConfig(
        max_depth=config.delegation.max_depth,
        max_concurrent=config.delegation.max_concurrent,
    )
    manager = DelegationManager(
        config=delegation_config,
        parent_agent=agent,
        profile_registry=registry,
    )
    print("✅ 委托管理器已创建（含专家注册表）")

    try:
        # 场景 1：单专家委托
        demo_single_expert(manager, registry)

        # 场景 2：顺序多专家协作
        demo_sequential_experts(manager)

        # 场景 3：并行多专家分析
        demo_parallel_experts(manager)

        # 场景 4：自定义系统提示
        demo_expert_with_custom_prompt(manager)

        # 场景 5：YAML 继承与热重载
        demo_yaml_inheritance()

        # 场景 6：使用 YAML 专家执行任务
        demo_yaml_expert_delegation(agent)

    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        agent.shutdown()

    print("\n" + "=" * 50)
    print("✅ 自定义专家 Agent 演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
