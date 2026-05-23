"""记忆系统演示。

展示 AgentForge 的记忆系统能力：
- 启用记忆存储
- 存储用户信息
- 跨会话恢复
"""

import os
import shutil
import sys
from pathlib import Path

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demo.utils import setup_demo, print_section, create_agent
from demo.config import get_config


def cleanup_memory_dir(memory_dir: str):
    """清理记忆目录。"""
    if os.path.exists(memory_dir):
        shutil.rmtree(memory_dir)


def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 记忆系统演示")
    print("=" * 50)

    # 加载配置
    config = get_config()

    # 记忆存储路径（从配置获取）
    memory_dir = Path(config.memory.store_path)
    if not memory_dir.is_absolute():
        memory_dir = Path(__file__).parent.parent / memory_dir

    # 清理旧的记忆数据
    cleanup_memory_dir(str(memory_dir))

    print(f"\n📁 记忆存储路径: {memory_dir}")

    # ========== 会话 1 ==========
    print_section("会话 1: 存储记忆")

    # 创建 Agent-1
    agent1, config = create_agent()
    print(f"\n📦 创建 Agent-1, 模型: {config.ollama.model}")

    # 启用记忆存储
    agent1.enable_memory_store(str(memory_dir))
    print("✅ 已启用记忆存储")

    # 预取记忆（首次为空）
    agent1.prefetch()

    # 对话，存储用户信息
    print("\n--- 对话 1 ---")
    prompt1 = "请记住：我叫张三，我是一名 Python 开发者，我喜欢使用 FastAPI 框架。"
    print(f"用户: {prompt1}")

    response1 = agent1.run(prompt1)
    print(f"Agent: {response1.content}")

    # 同步记忆到存储
    agent1.sync()
    print("\n💾 记忆已同步到存储")

    # 查看存储内容
    memory_file = memory_dir / "MEMORY.md"
    if memory_file.exists():
        print("\n📄 存储内容:")
        print("-" * 30)
        print(memory_file.read_text(encoding="utf-8")[:500])
        print("-" * 30)

    # ========== 会话 2 ==========
    print_section("会话 2: 恢复记忆")

    # 创建 Agent-2
    agent2, config = create_agent()
    print(f"\n📦 创建 Agent-2, 模型: {config.ollama.model}")

    # 启用记忆存储
    agent2.enable_memory_store(str(memory_dir))
    print("✅ 已启用记忆存储")

    # 预取记忆（恢复之前的记忆）
    agent2.prefetch()
    print("✅ 已预取记忆")

    # 测试记忆恢复
    print("\n--- 测试记忆恢复 ---")
    prompt2 = "我叫什么名字？"
    print(f"用户: {prompt2}")

    response2 = agent2.run(prompt2)
    print(f"Agent: {response2.content}")

    # 继续测试
    print("\n--- 继续测试 ---")
    prompt3 = "我做什么工作？我喜欢用什么框架？"
    print(f"用户: {prompt3}")

    response3 = agent2.run(prompt3)
    print(f"Agent: {response3.content}")

    # 清理（可选）
    # cleanup_memory_dir(str(memory_dir))

    print("\n" + "=" * 50)
    print("✅ 记忆系统演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
