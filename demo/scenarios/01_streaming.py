"""流式响应演示。

展示 AgentForge 的流式响应能力：
- 同步流式响应 (stream)
- 异步流式响应 (stream_async)
- Token 级别增量 (stream_deltas)
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider


def check_ollama() -> bool:
    """检查 Ollama 服务是否可用。"""
    import requests

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def demo_sync_streaming(agent: Agent):
    """演示同步流式响应。"""
    print("\n" + "=" * 50)
    print("=== 同步流式响应 ===")
    print("=" * 50)

    prompt = "请用简短的几句话介绍一下 Python 编程语言的特点。"
    print(f"\n问题: {prompt}\n")
    print("回答: ", end="", flush=True)

    start_time = time.time()
    total_content = ""

    for chunk in agent.stream(prompt):
        if chunk.content:
            print(chunk.content, end="", flush=True)
            total_content += chunk.content

    duration = time.time() - start_time
    print(f"\n\n⏱️  耗时: {duration:.2f}s")
    print(f"📝 内容长度: {len(total_content)} 字符")


async def demo_async_streaming(agent: Agent):
    """演示异步流式响应。"""
    print("\n" + "=" * 50)
    print("=== 异步流式响应 ===")
    print("=" * 50)

    prompt = "请用一句话解释什么是机器学习。"
    print(f"\n问题: {prompt}\n")
    print("回答: ", end="", flush=True)

    start_time = time.time()
    total_content = ""

    async for chunk in agent.stream_async(prompt):
        if chunk.content:
            print(chunk.content, end="", flush=True)
            total_content += chunk.content

    duration = time.time() - start_time
    print(f"\n\n⏱️  耗时: {duration:.2f}s")
    print(f"📝 内容长度: {len(total_content)} 字符")


def demo_delta_streaming(agent: Agent):
    """演示 Token 级别增量流式。"""
    print("\n" + "=" * 50)
    print("=== Token 增量流式 ===")
    print("=" * 50)

    prompt = "请列出 3 个 Python 的应用领域。"
    print(f"\n问题: {prompt}\n")
    print("回答: ", end="", flush=True)

    start_time = time.time()
    total_tokens = 0

    for delta in agent.stream_deltas(prompt):
        if delta.has_content:
            print(delta.content, end="", flush=True)
            total_tokens += 1

        # 显示完成信息
        if delta.is_final and delta.usage:
            print(f"\n\n📊 Token 统计:")
            print(f"   输入: {delta.usage.prompt_tokens}")
            print(f"   输出: {delta.usage.completion_tokens}")
            print(f"   总计: {delta.usage.total_tokens}")

    duration = time.time() - start_time
    print(f"\n⏱️  耗时: {duration:.2f}s")


def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 流式响应演示")
    print("=" * 50)

    # 检查 Ollama
    if not check_ollama():
        print("\n❌ 错误: Ollama 服务未运行")
        print("请先启动 Ollama: ollama serve")
        sys.exit(1)

    print("\n✅ Ollama 服务已连接")

    # 创建 Agent
    provider = OllamaProvider(model="llama3.2")
    agent = Agent(provider=provider)
    print(f"📦 模型: {provider._model}")

    # 演示同步流式
    demo_sync_streaming(agent)

    # 清空上下文
    agent.clear()

    # 演示异步流式
    asyncio.run(demo_async_streaming(agent))

    # 清空上下文
    agent.clear()

    # 演示 Token 增量流式
    demo_delta_streaming(agent)

    print("\n" + "=" * 50)
    print("✅ 流式响应演示完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
