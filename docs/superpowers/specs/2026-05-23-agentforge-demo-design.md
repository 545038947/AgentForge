---
name: agentforge-demo
description: AgentForge 框架完整功能演示 Demo 设计
---

# AgentForge Demo 设计文档

## 概述

创建一个完整的 CLI demo，验证 AgentForge 框架的核心功能可用性。使用 Ollama 本地模型作为后端，展示流式响应、工具调用、记忆系统、委托系统。

## 目标

- 验证框架基础功能：Agent 创建、对话、上下文维护
- 验证流式响应：同步/异步流式输出，实时显示
- 验证工具系统：自定义工具定义、参数解析、执行
- 验证记忆系统：跨会话持久化、记忆恢复
- 验证委托系统：子 Agent 创建、并行委托、结果聚合

## 项目结构

```
demo/
├── __init__.py
├── run_repl.py              # 主交互式 REPL
├── tools/                   # 自定义工具定义
│   ├── __init__.py
│   └── demo_tools.py        # 演示用工具
├── scenarios/               # 分场景演示脚本
│   ├── __init__.py
│   ├── 01_streaming.py      # 流式响应演示
│   ├── 02_tools.py          # 工具调用演示
│   ├── 03_memory.py         # 记忆系统演示
│   └── 04_delegation.py     # 委托系统演示
└── README.md                # Demo 使用说明
```

## 模块设计

### 1. 主 REPL (run_repl.py)

**核心功能**：
- 多轮对话，自动维护上下文
- 流式响应实时显示
- 内置命令处理

**内置命令**：
| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/tools` | 列出可用工具 |
| `/clear` | 清空对话历史 |
| `/memory` | 显示当前记忆状态 |
| `/quit` | 退出 REPL |

**交互流程**：
1. 启动时显示欢迎信息和当前配置
2. 用户输入消息或命令
3. 消息：流式显示 Agent 响应
4. 命令：执行对应操作
5. 循环直到 `/quit`

**错误处理**：
- Ollama 连接失败时提示用户检查服务
- 工具执行失败时显示友好错误信息

### 2. 自定义工具 (demo_tools.py)

定义 4 个演示工具：

#### calculator
```python
@tool
def calculator(expression: str) -> str:
    """计算数学表达式。支持基本运算 (+, -, *, /)。

    Args:
        expression: 数学表达式，如 "123 * 456"
    """
```
展示点：基础工具调用，单参数

#### get_weather
```python
@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """获取指定城市的天气信息（模拟）。

    Args:
        city: 城市名称
        unit: 温度单位，celsius 或 fahrenheit
    """
```
展示点：多参数，可选参数

#### read_file
```python
@tool
def read_file(filepath: str) -> str:
    """读取本地文件内容。

    Args:
        filepath: 文件路径
    """
```
展示点：文件操作，路径验证

#### search_web
```python
@tool
def search_web(query: str, limit: int = 3) -> str:
    """模拟网络搜索（返回模拟结果）。

    Args:
        query: 搜索关键词
        limit: 返回结果数量
    """
```
展示点：模拟外部服务，整数参数

### 3. 场景脚本

#### 01_streaming.py - 流式响应演示

**演示内容**：
- 同步流式响应 (`stream()`)
- 异步流式响应 (`stream_async()`)
- Token 级别增量 (`stream_deltas()`)
- 使用统计信息显示

**输出示例**：
```
=== 同步流式响应 ===
讲一个简短的故事...
[实时显示故事内容]

使用 156 tokens, 耗时 2.3s

=== 异步流式响应 ===
继续上面的故事...
[实时显示]

=== Token 增量流式 ===
[逐 token 显示，包含推理内容]
```

#### 02_tools.py - 工具调用演示

**演示内容**：
- 单工具调用
- 多工具并发调用
- 工具结果展示
- 错误处理

**演示流程**：
1. 定义问题需要工具解决
2. Agent 自动选择调用工具
3. 显示工具调用过程和结果
4. Agent 整合结果回答

#### 03_memory.py - 记忆系统演示

**演示内容**：
- 启用记忆存储
- 存储用户信息
- 跨会话恢复
- 自动记忆提取

**演示流程**：
```
步骤 1: 创建 Agent-1，启用记忆存储
步骤 2: 对话，告诉 Agent 用户信息
        "我叫张三，我是一名 Python 开发者"
步骤 3: 同步记忆到存储
步骤 4: 查看存储内容

步骤 5: 创建 Agent-2，恢复记忆
步骤 6: 询问 "我叫什么名字？"
        Agent 回答: "你叫张三"
步骤 7: 询问 "我做什么工作？"
        Agent 回答: "你是一名 Python 开发者"
```

**Why**: 跨会话记忆是 Agent 框架的重要能力，需要验证持久化和恢复机制是否正常工作。

#### 04_delegation.py - 委托系统演示

**演示内容**：
- 创建子 Agent
- 单任务委托
- 批量并行委托
- 结果聚合

**演示流程**：
```
步骤 1: 创建主 Agent
步骤 2: 定义任务列表:
        - 任务 1: 搜索 Python 教程
        - 任务 2: 搜索 JavaScript 教程
        - 任务 3: 搜索 Go 教程
步骤 3: 使用 PARALLEL 策略并行委托
步骤 4: 显示各子 Agent 执行结果
步骤 5: 主 Agent 聚合总结
```

**Why**: 委托系统支持复杂任务的分解和并行处理，是 Agent 框架的核心扩展能力。

## 技术细节

### Provider 配置

使用 Ollama Provider，默认配置：
```python
from hai_agent import Agent
from hai_agent.providers import OllamaProvider

provider = OllamaProvider(
    model="llama3.2",  # 或其他本地模型
    base_url="http://localhost:11434/v1"
)
agent = Agent(provider=provider)
```

### 错误处理策略

1. **Ollama 连接检查**：启动时尝试连接，失败则提示用户启动 Ollama 服务
2. **工具执行错误**：捕获 ToolExecutionError，显示友好信息
3. **记忆存储错误**：文件权限问题提示用户检查路径

### 依赖要求

- Python 3.9+
- agentforge 核心库
- Ollama 服务运行中（localhost:11434）

### 运行方式

```bash
# 进入 demo 目录
cd demo

# 运行主 REPL
python run_repl.py

# 运行单独场景
python scenarios/01_streaming.py
python scenarios/02_tools.py
python scenarios/03_memory.py
python scenarios/04_delegation.py

# 指定模型
python run_repl.py --model llama3.1

# 指定 Ollama 地址
python run_repl.py --base-url http://192.168.1.100:11434/v1
```

## 验收标准

1. **REPL 可正常启动**：显示欢迎信息，进入交互模式
2. **流式响应正常**：响应实时显示，无卡顿
3. **工具调用成功**：Agent 能正确识别并调用工具
4. **记忆系统工作**：跨会话能恢复之前存储的信息
5. **委托系统工作**：子 Agent 能创建并执行任务，结果能聚合
6. **错误处理友好**：连接失败等异常有清晰提示

## How to apply

此设计用于创建 demo 验证框架可用性。实现时按模块逐一开发，每个模块完成后独立测试，最后整体集成测试。