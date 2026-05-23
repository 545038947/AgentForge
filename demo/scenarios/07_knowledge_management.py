"""个人知识管理场景。

真实使用场景：帮助用户管理个人知识和记忆。
展示能力：
- 记忆系统（长期记忆 + 工具调用记忆）
- 信息提取和保存
- 知识查询和检索
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
from agentforge.tools.builtins import FileWriteTool, SaveMemoryTool, QueryMemoryTool
from demo.config import reload_config
from demo.utils import print_section


def create_knowledge_assistant():
    """创建知识管理助手 Agent。"""
    config = reload_config()

    from agentforge.providers.builtins import OllamaProvider

    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
        timeout=config.ollama.timeout,
    )

    # 注册文件和记忆工具
    tools = [
        FileWriteTool(),
    ]

    agent = Agent(provider=provider, tools=tools)

    # 启用记忆系统
    memory_path = Path(__file__).parent.parent / "memory_store"
    agent.enable_memory_store(str(memory_path))

    # 添加记忆工具
    memory_tools = agent.get_memory_tools()
    agent.add_tools(memory_tools)

    # 加载 MCP Servers（可选）
    if config.mcp.enabled and config.mcp.config_path:
        mcp_config_path = Path(__file__).parent.parent / config.mcp.config_path
        if mcp_config_path.exists():
            agent.add_mcp_servers(str(mcp_config_path))

    return agent, config


def demo_save_user_info(agent):
    """演示：保存用户信息。"""
    print_section("场景 1: 学习并记住用户偏好")

    prompt = """
请记住以下信息：
- 用户名：张三
- 职业：软件工程师
- 主要使用 Python 和 JavaScript
- 兴趣领域：机器学习、Web 开发
- 常用 IDE：VS Code

使用 save_memory 工具保存这些信息。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.prefetch()
    response = agent.run(prompt, max_iterations=10)
    print(f"\n助手回答:\n{response.content}")


def demo_query_memory(agent):
    """演示：查询记忆。"""
    print_section("场景 2: 回忆用户信息")

    prompt = """
请查询我们之前保存的记忆，告诉我：
1. 用户的名字是什么？
2. 用户擅长哪些编程语言？
3. 用户感兴趣的领域有哪些？

使用 query_memory 工具查询。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=10)
    print(f"\n助手回答:\n{response.content}")


def demo_personalized_response(agent):
    """演示：基于记忆的个性化回答。"""
    print_section("场景 3: 个性化推荐")

    prompt = """
基于我之前告诉你的信息，请推荐：
1. 适合我学习的机器学习课程
2. 适合我使用的 Python Web 框架
3. VS Code 中值得安装的插件

请先查询我的偏好，然后给出个性化建议。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=15)
    print(f"\n助手回答:\n{response.content}")


def demo_save_knowledge(agent):
    """演示：保存学习笔记。"""
    print_section("场景 4: 保存学习笔记")

    prompt = """
我学习了 Python asyncio 的基础知识，请帮我保存以下笔记：

核心概念：
1. async/await - 定义协程
2. asyncio.run() - 运行协程
3. asyncio.gather() - 并发执行多个任务
4. TaskGroup (Python 3.11+) - 结构化并发

最佳实践：
- 使用 await asyncio.sleep() 而非 time.sleep()
- 使用 asyncio.to_thread() 处理同步 IO
- 避免在协程中使用阻塞操作

请使用 save_memory 工具保存到 memory 类别。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=10)
    print(f"\n助手回答:\n{response.content}")


def demo_recall_and_apply(agent):
    """演示：回忆并应用知识。"""
    print_section("场景 5: 回忆知识解决问题")

    prompt = """
我需要编写一个异步下载多个网页的程序。
请：
1. 先查询我之前保存的 asyncio 笔记
2. 基于笔记中的知识给出代码示例
3. 使用 httpx 库实现

请详细说明。
"""
    print(f"\n用户请求: {prompt.strip()}")

    agent.clear()
    response = agent.run(prompt, max_iterations=15)
    print(f"\n助手回答:\n{response.content}")


def show_memory_files():
    """显示记忆文件内容。"""
    print_section("记忆文件内容")

    memory_path = Path(__file__).parent.parent / "memory_store"

    print(f"\n记忆存储路径: {memory_path}")

    for file in ["MEMORY.md", "USER.md"]:
        filepath = memory_path / file
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            print(f"\n📄 {file}:")
            print("-" * 40)
            print(content[:500] if content else "(空)")
            if len(content) > 500:
                print(f"\n... 共 {len(content)} 字符")
        else:
            print(f"\n📄 {file}: (不存在)")


def main():
    """主函数。"""
    print("=" * 60)
    print("🧠 个人知识管理 - 真实场景演示")
    print("=" * 60)
    print("""
本演示展示 AgentForge 在个人知识管理场景中的应用：
- 使用记忆工具保存用户偏好和知识
- 查询记忆获取历史信息
- 基于记忆进行个性化推荐
- 知识积累和应用
""")

    print("\n正在初始化知识管理助手...")
    agent, config = create_knowledge_assistant()

    print(f"📦 模型: {config.ollama.model}")
    print(f"🧠 记忆系统: 已启用")

    # 运行演示
    try:
        demo_save_user_info(agent)
        demo_query_memory(agent)
        demo_personalized_response(agent)
        demo_save_knowledge(agent)
        demo_recall_and_apply(agent)

        # 同步记忆
        agent.sync()

        # 显示记忆文件
        show_memory_files()

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