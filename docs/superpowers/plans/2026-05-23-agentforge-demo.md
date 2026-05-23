# AgentForge Demo 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个完整的 CLI demo 验证 AgentForge 框架核心功能：流式响应、工具调用、记忆系统、委托系统。

**Architecture:** 主 REPL 支持多轮对话和内置命令，4 个独立场景脚本分别展示各核心功能。使用 Ollama 本地模型作为后端，无需外部 API Key。

**Tech Stack:** Python 3.9+, AgentForge, Ollama

---

## 文件结构

```
demo/
├── __init__.py              # 包初始化
├── run_repl.py              # 主交互式 REPL
├── tools/
│   ├── __init__.py          # 工具模块初始化
│   └── demo_tools.py        # 4 个演示工具
├── scenarios/
│   ├── __init__.py          # 场景模块初始化
│   ├── 01_streaming.py      # 流式响应演示
│   ├── 02_tools.py          # 工具调用演示
│   ├── 03_memory.py         # 记忆系统演示
│   └── 04_delegation.py     # 委托系统演示
└── README.md                # 使用说明
```

---

### Task 1: 创建 demo 目录结构和基础文件

**Files:**
- Create: `demo/__init__.py`
- Create: `demo/tools/__init__.py`
- Create: `demo/scenarios/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p demo/tools demo/scenarios
```

- [ ] **Step 2: 创建 `demo/__init__.py`**

```python
"""AgentForge Demo - 框架功能演示。

此包包含：
- run_repl.py: 交互式 REPL
- tools/: 演示用自定义工具
- scenarios/: 分场景演示脚本
"""

__version__ = "0.1.0"
```

- [ ] **Step 3: 创建 `demo/tools/__init__.py`**

```python
"""演示工具模块。"""

from demo.tools.demo_tools import (
    calculator,
    get_weather,
    read_file,
    search_web,
    get_all_demo_tools,
)

__all__ = [
    "calculator",
    "get_weather",
    "read_file",
    "search_web",
    "get_all_demo_tools",
]
```

- [ ] **Step 4: 创建 `demo/scenarios/__init__.py`**

```python
"""场景演示模块。

每个脚本独立运行，展示特定功能：
- 01_streaming.py: 流式响应
- 02_tools.py: 工具调用
- 03_memory.py: 记忆系统
- 04_delegation.py: 委托系统
"""
```

- [ ] **Step 5: 提交**

```bash
git add demo/
git commit -m "feat(demo): 创建 demo 目录结构

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 实现演示工具

**Files:**
- Create: `demo/tools/demo_tools.py`

- [ ] **Step 1: 创建 `demo/tools/demo_tools.py`**

```python
"""演示用自定义工具。

包含 4 个工具展示不同特性：
- calculator: 基础工具调用，单参数
- get_weather: 多参数，可选参数
- read_file: 文件操作，路径验证
- search_web: 模拟外部服务，整数参数
"""

from __future__ import annotations

import os
from typing import List

from agentforge import tool


@tool
def calculator(expression: str) -> str:
    """计算数学表达式。

    支持基本运算：加(+)、减(-)、乘(*)、除(/)。

    Args:
        expression: 数学表达式，如 "123 * 456" 或 "100 / 5"

    Returns:
        计算结果
    """
    try:
        # 安全计算：只允许数字和基本运算符
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含不允许的字符"

        result = eval(expression)
        return f"计算结果: {expression} = {result}"
    except ZeroDivisionError:
        return "错误：除数不能为零"
    except Exception as e:
        return f"计算错误: {e}"


@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """获取指定城市的天气信息（模拟）。

    这是一个模拟工具，返回预设的天气数据。

    Args:
        city: 城市名称，如 "北京"、"上海"
        unit: 温度单位，"celsius" 或 "fahrenheit"

    Returns:
        天气信息字符串
    """
    # 模拟天气数据
    weather_data = {
        "北京": {"temp": 25, "condition": "晴朗", "humidity": 45},
        "上海": {"temp": 28, "condition": "多云", "humidity": 65},
        "广州": {"temp": 32, "condition": "雷阵雨", "humidity": 80},
        "深圳": {"temp": 30, "condition": "晴朗", "humidity": 70},
        "成都": {"temp": 22, "condition": "阴天", "humidity": 55},
    }

    # 获取城市数据，默认返回通用数据
    data = weather_data.get(city, {"temp": 26, "condition": "晴朗", "humidity": 50})

    # 温度单位转换
    temp = data["temp"]
    if unit == "fahrenheit":
        temp = temp * 9 / 5 + 32
        unit_str = "°F"
    else:
        unit_str = "°C"

    return (
        f"📍 {city} 天气预报\n"
        f"  温度: {temp:.1f}{unit_str}\n"
        f"  天气: {data['condition']}\n"
        f"  湿度: {data['humidity']}%"
    )


@tool
def read_file(filepath: str) -> str:
    """读取本地文件内容。

    读取指定路径的文本文件内容。

    Args:
        filepath: 文件路径，可以是相对路径或绝对路径

    Returns:
        文件内容或错误信息
    """
    try:
        # 路径验证
        if not filepath:
            return "错误：文件路径不能为空"

        # 展开路径（支持 ~）
        expanded_path = os.path.expanduser(filepath)

        # 检查文件是否存在
        if not os.path.exists(expanded_path):
            return f"错误：文件不存在: {filepath}"

        # 检查是否是文件
        if not os.path.isfile(expanded_path):
            return f"错误：路径不是文件: {filepath}"

        # 读取文件
        with open(expanded_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 限制返回长度
        max_length = 2000
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n... (已截断，共 {len(content)} 字符)"

        return f"📄 文件: {filepath}\n\n{content}"

    except PermissionError:
        return f"错误：无权限读取文件: {filepath}"
    except UnicodeDecodeError:
        return f"错误：文件编码不支持（非文本文件）: {filepath}"
    except Exception as e:
        return f"读取错误: {e}"


@tool
def search_web(query: str, limit: int = 3) -> str:
    """模拟网络搜索。

    这是一个模拟工具，返回预设的搜索结果。

    Args:
        query: 搜索关键词
        limit: 返回结果数量，默认 3

    Returns:
        模拟的搜索结果
    """
    # 模拟搜索结果
    mock_results = [
        {
            "title": f"关于 {query} 的详细介绍",
            "url": f"https://example.com/article/{query}",
            "snippet": f"这是关于 {query} 的详细文章，包含相关知识和信息...",
        },
        {
            "title": f"{query} - 官方文档",
            "url": f"https://docs.example.com/{query}",
            "snippet": f"官方文档提供了 {query} 的完整使用指南...",
        },
        {
            "title": f"如何学习 {query}",
            "url": f"https://tutorial.example.com/{query}",
            "snippet": f"本教程将帮助你快速掌握 {query} 的核心概念...",
        },
        {
            "title": f"{query} 最佳实践",
            "url": f"https://bestpractices.example.com/{query}",
            "snippet": f"本文总结了 {query} 的最佳实践和常见问题...",
        },
        {
            "title": f"{query} 社区讨论",
            "url": f"https://forum.example.com/{query}",
            "snippet": f"社区成员分享了关于 {query} 的经验和见解...",
        },
    ]

    # 限制结果数量
    results = mock_results[:limit]

    # 格式化输出
    output = f"🔍 搜索: {query}\n"
    output += f"找到 {len(results)} 个结果:\n\n"

    for i, result in enumerate(results, 1):
        output += f"{i}. {result['title']}\n"
        output += f"   URL: {result['url']}\n"
        output += f"   {result['snippet']}\n\n"

    return output


def get_all_demo_tools() -> List:
    """获取所有演示工具。

    Returns:
        工具列表
    """
    return [calculator, get_weather, read_file, search_web]
```

- [ ] **Step 2: 提交**

```bash
git add demo/tools/demo_tools.py demo/tools/__init__.py
git commit -m "feat(demo): 添加 4 个演示工具

- calculator: 数学计算工具
- get_weather: 天气查询工具（模拟）
- read_file: 文件读取工具
- search_web: 网络搜索工具（模拟）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 实现流式响应演示脚本

**Files:**
- Create: `demo/scenarios/01_streaming.py`

- [ ] **Step 1: 创建 `demo/scenarios/01_streaming.py`**

```python
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
```

- [ ] **Step 2: 提交**

```bash
git add demo/scenarios/01_streaming.py
git commit -m "feat(demo): 添加流式响应演示脚本

展示同步流式、异步流式和 Token 增量流式

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 实现工具调用演示脚本

**Files:**
- Create: `demo/scenarios/02_tools.py`

- [ ] **Step 1: 创建 `demo/scenarios/02_tools.py`**

```python
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
```

- [ ] **Step 2: 提交**

```bash
git add demo/scenarios/02_tools.py
git commit -m "feat(demo): 添加工具调用演示脚本

展示工具定义、注册和 Agent 自动调用

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 实现记忆系统演示脚本

**Files:**
- Create: `demo/scenarios/03_memory.py`

- [ ] **Step 1: 创建 `demo/scenarios/03_memory.py`**

```python
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


def cleanup_memory_dir(memory_dir: str):
    """清理记忆目录。"""
    if os.path.exists(memory_dir):
        shutil.rmtree(memory_dir)


def main():
    """主函数。"""
    print("=" * 50)
    print("AgentForge 记忆系统演示")
    print("=" * 50)

    # 检查 Ollama
    if not check_ollama():
        print("\n❌ 错误: Ollama 服务未运行")
        print("请先启动 Ollama: ollama serve")
        sys.exit(1)

    print("\n✅ Ollama 服务已连接")

    # 记忆存储路径
    memory_dir = Path(__file__).parent.parent / "memory_store"

    # 清理旧的记忆数据
    cleanup_memory_dir(str(memory_dir))

    print(f"\n📁 记忆存储路径: {memory_dir}")

    # ========== 会话 1 ==========
    print("\n" + "=" * 50)
    print("=== 会话 1: 存储记忆 ===")
    print("=" * 50)

    # 创建 Agent-1
    provider1 = OllamaProvider(model="llama3.2")
    agent1 = Agent(provider=provider1)
    print(f"\n📦 创建 Agent-1, 模型: {provider1._model}")

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
    print("\n" + "=" * 50)
    print("=== 会话 2: 恢复记忆 ===")
    print("=" * 50)

    # 创建 Agent-2
    provider2 = OllamaProvider(model="llama3.2")
    agent2 = Agent(provider=provider2)
    print(f"\n📦 创建 Agent-2, 模型: {provider2._model}")

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
```

- [ ] **Step 2: 提交**

```bash
git add demo/scenarios/03_memory.py
git commit -m "feat(demo): 添加记忆系统演示脚本

展示跨会话记忆存储和恢复

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 实现委托系统演示脚本

**Files:**
- Create: `demo/scenarios/04_delegation.py`

- [ ] **Step 1: 创建 `demo/scenarios/04_delegation.py`**

```python
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
```

- [ ] **Step 2: 提交**

```bash
git add demo/scenarios/04_delegation.py
git commit -m "feat(demo): 添加委托系统演示脚本

展示单任务委托和批量并行委托

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 实现主 REPL

**Files:**
- Create: `demo/run_repl.py`

- [ ] **Step 1: 创建 `demo/run_repl.py`**

```python
"""AgentForge Demo - 交互式 REPL。

主交互界面，支持：
- 多轮对话
- 流式响应
- 内置命令
- 工具调用
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider
from demo.tools import get_all_demo_tools


def check_ollama(base_url: str = "http://localhost:11434") -> bool:
    """检查 Ollama 服务是否可用。"""
    import requests

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def list_available_models(base_url: str = "http://localhost:11434") -> list:
    """列出可用模型。"""
    import requests

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return []


class REPL:
    """交互式 REPL。"""

    COMMANDS = {
        "/help": "显示帮助信息",
        "/tools": "列出可用工具",
        "/clear": "清空对话历史",
        "/info": "显示 Agent 信息",
        "/quit": "退出 REPL",
    }

    def __init__(self, agent: Agent, model: str):
        self.agent = agent
        self.model = model
        self.tools = get_all_demo_tools()

    def show_welcome(self):
        """显示欢迎信息。"""
        print("\n" + "=" * 50)
        print("🤖 AgentForge Demo REPL")
        print("=" * 50)
        print(f"\n📦 模型: {self.model}")
        print(f"🔧 工具数量: {len(self.tools)}")
        print("\n输入 /help 查看可用命令")
        print("输入消息开始对话\n")

    def show_help(self):
        """显示帮助信息。"""
        print("\n📖 可用命令:")
        for cmd, desc in self.COMMANDS.items():
            print(f"  {cmd:<10} - {desc}")
        print()

    def show_tools(self):
        """显示工具列表。"""
        print("\n🔧 已注册工具:")
        for tool in self.tools:
            print(f"\n  📦 {tool.name}")
            desc = tool.description.split("\n")[0]
            print(f"     {desc[:60]}...")
        print()

    def show_info(self):
        """显示 Agent 信息。"""
        print("\n📊 Agent 信息:")
        print(f"  模型: {self.model}")
        print(f"  工具数量: {len(self.tools)}")

        # 消息数量
        if hasattr(self.agent, "_message_manager"):
            msg_count = len(self.agent._message_manager)
            print(f"  消息数量: {msg_count}")

        print()

    def clear_history(self):
        """清空对话历史。"""
        self.agent.clear()
        print("\n✅ 对话历史已清空\n")

    def process_command(self, user_input: str) -> bool:
        """处理命令。

        Returns:
            True 表示继续，False 表示退出
        """
        cmd = user_input.strip().lower()

        if cmd == "/help":
            self.show_help()
        elif cmd == "/tools":
            self.show_tools()
        elif cmd == "/clear":
            self.clear_history()
        elif cmd == "/info":
            self.show_info()
        elif cmd == "/quit":
            print("\n👋 再见！\n")
            return False
        else:
            print(f"\n❌ 未知命令: {cmd}")
            print("输入 /help 查看可用命令\n")

        return True

    def chat(self, user_input: str):
        """进行对话。"""
        print("\n🤖 Agent: ", end="", flush=True)

        try:
            # 使用流式响应
            for chunk in self.agent.stream(user_input):
                if chunk.content:
                    print(chunk.content, end="", flush=True)

            print("\n")

        except Exception as e:
            print(f"\n❌ 错误: {e}\n")

    def run(self):
        """运行 REPL。"""
        self.show_welcome()

        while True:
            try:
                user_input = input("👤 你: ").strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.startswith("/"):
                    if not self.process_command(user_input):
                        break
                else:
                    # 对话
                    self.chat(user_input)

            except KeyboardInterrupt:
                print("\n\n👋 再见！\n")
                break
            except EOFError:
                print("\n\n👋 再见！\n")
                break


def main():
    """主函数。"""
    parser = argparse.ArgumentParser(description="AgentForge Demo REPL")
    parser.add_argument(
        "--model",
        default="llama3.2",
        help="Ollama 模型名称 (默认: llama3.2)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434/v1",
        help="Ollama 服务地址 (默认: http://localhost:11434/v1)",
    )
    args = parser.parse_args()

    # 提取基础 URL（去掉 /v1）
    base_url = args.base_url
    if base_url.endswith("/v1"):
        check_url = base_url[:-3]
    else:
        check_url = base_url

    # 检查 Ollama
    if not check_ollama(check_url):
        print("\n❌ 错误: Ollama 服务未运行")
        print(f"   检查地址: {check_url}")
        print("\n请先启动 Ollama:")
        print("  ollama serve")
        sys.exit(1)

    # 列出可用模型
    models = list_available_models(check_url)
    if models and args.model not in [m.split(":")[0] for m in models]:
        print(f"\n⚠️  警告: 模型 '{args.model}' 可能未安装")
        print("可用模型:")
        for m in models[:5]:
            print(f"  - {m}")
        print()

    # 创建 Agent
    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    tools = get_all_demo_tools()
    agent = Agent(provider=provider, tools=tools)

    # 运行 REPL
    repl = REPL(agent, args.model)
    repl.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 提交**

```bash
git add demo/run_repl.py
git commit -m "feat(demo): 添加交互式 REPL

支持多轮对话、流式响应、内置命令

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: 创建 README 文档

**Files:**
- Create: `demo/README.md`

- [ ] **Step 1: 创建 `demo/README.md`**

```markdown
# AgentForge Demo

AgentForge 框架完整功能演示，验证核心功能可用性。

## 功能演示

- ✅ **流式响应** - 同步/异步流式输出，实时显示
- ✅ **工具调用** - 自定义工具定义和执行
- ✅ **记忆系统** - 跨会话记忆持久化和恢复
- ✅ **委托系统** - 子 Agent 创建和并行委托

## 前置要求

1. Python 3.9+
2. Ollama 服务运行中

```bash
# 启动 Ollama
ollama serve

# 拉取模型（如果未安装）
ollama pull llama3.2
```

## 运行方式

### 主 REPL

```bash
cd demo
python run_repl.py
```

可选参数：
```bash
python run_repl.py --model llama3.1
python run_repl.py --base-url http://192.168.1.100:11434/v1
```

### 场景脚本

```bash
# 流式响应演示
python scenarios/01_streaming.py

# 工具调用演示
python scenarios/02_tools.py

# 记忆系统演示
python scenarios/03_memory.py

# 委托系统演示
python scenarios/04_delegation.py
```

## REPL 命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/tools` | 列出可用工具 |
| `/clear` | 清空对话历史 |
| `/info` | 显示 Agent 信息 |
| `/quit` | 退出 REPL |

## 工具列表

| 工具 | 功能 |
|------|------|
| `calculator` | 数学计算 |
| `get_weather` | 天气查询（模拟） |
| `read_file` | 文件读取 |
| `search_web` | 网络搜索（模拟） |

## 示例对话

```
👤 你: 你好，请介绍一下你自己
🤖 Agent: 你好！我是由 AgentForge 框架驱动的 AI 助手...

👤 你: 帮我计算 123 * 456
🤖 Agent: [调用 calculator 工具] 计算结果是 56088

👤 你: 北京今天天气怎么样？
🤖 Agent: [调用 get_weather 工具] 北京今天天气晴朗，温度 25°C...
```
```

- [ ] **Step 2: 提交**

```bash
git add demo/README.md
git commit -m "docs(demo): 添加 README 使用说明

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: 最终验证和提交

- [ ] **Step 1: 验证文件结构**

```bash
ls -la demo/
ls -la demo/tools/
ls -la demo/scenarios/
```

- [ ] **Step 2: 验证 Python 语法**

```bash
python -m py_compile demo/__init__.py
python -m py_compile demo/tools/demo_tools.py
python -m py_compile demo/scenarios/01_streaming.py
python -m py_compile demo/scenarios/02_tools.py
python -m py_compile demo/scenarios/03_memory.py
python -m py_compile demo/scenarios/04_delegation.py
python -m py_compile demo/run_repl.py
```

- [ ] **Step 3: 最终提交**

```bash
git add demo/
git commit -m "feat(demo): 完成 AgentForge Demo

包含：
- 主交互式 REPL (run_repl.py)
- 4 个演示工具 (calculator, get_weather, read_file, search_web)
- 4 个场景脚本 (streaming, tools, memory, delegation)
- README 使用说明

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
