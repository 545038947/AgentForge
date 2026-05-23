# AgentForge Demo

AgentForge 框架完整功能演示，验证核心功能可用性。

## 功能演示

### 基础功能
- ✅ **流式响应** - 同步/异步流式输出，实时显示
- ✅ **工具调用** - 自定义工具定义和执行
- ✅ **记忆系统** - 跨会话记忆持久化和恢复
- ✅ **委托系统** - 子 Agent 创建和并行委托
- ✅ **MCP 支持** - Model Context Protocol 集成

### 真实场景
- ✅ **智能代码助手** - 代码分析、项目检查、问题排查
- ✅ **研究助手** - 网络搜索、信息整合、报告生成
- ✅ **知识管理** - 记忆保存、知识查询、个性化推荐
- ✅ **多 Agent 协作** - 任务分解、委托执行、文档生成

## 前置要求

1. Python 3.9+
2. Ollama 服务运行中

```bash
# 启动 Ollama
ollama serve

# 拉取模型（如果未安装）
ollama pull gemma4:31b-cloud
```

### MCP 支持（可选）

如需使用 MCP 功能（如 Bing 搜索）：

```bash
# 安装 Node.js 和 npx
# 然后测试 MCP Server
npx -y bing-cn-mcp --help
```

## 配置

Demo 使用 YAML 配置文件管理设置：

```yaml
# Ollama 服务配置
ollama:
  base_url: "http://localhost:11434/v1"
  model: "gemma4:31b-cloud"
  timeout: 600

# Agent 配置
agent:
  temperature: 0.7
  max_tokens: 4096

# 记忆系统配置
memory:
  store_path: "./memory_store"

# MCP 配置
mcp:
  enabled: true
  config_path: "mcp_config.yaml"
```

## 运行方式

### 主 REPL

```bash
cd demo
python run_repl.py
```

可选参数：
```bash
python run_repl.py --model gemma4:31b-cloud
python run_repl.py --base-url http://192.168.1.100:11434/v1
python run_repl.py --mcp-config mcp_config.yaml
python run_repl.py --no-mcp
```

### 基础场景演示

```bash
python scenarios/01_streaming.py      # 流式响应
python scenarios/02_tools.py          # 工具调用
python scenarios/03_memory.py         # 记忆系统
python scenarios/04_delegation.py     # 委托系统
```

### 真实场景演示

```bash
python scenarios/05_code_assistant.py      # 智能代码助手
python scenarios/06_research_assistant.py  # 研究助手
python scenarios/07_knowledge_management.py # 个人知识管理
python scenarios/08_multi_agent.py         # 多 Agent 协作
```

## REPL 命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/tools` | 列出可用工具（内置 + MCP） |
| `/mcp` | 显示 MCP Server 状态 |
| `/clear` | 清空对话历史 |
| `/info` | 显示 Agent 信息 |
| `/config` | 显示当前配置 |
| `/quit` | 退出 REPL |

## 场景说明

### 05_code_assistant.py - 智能代码助手

展示开发者日常使用场景：
- 读取和分析代码文件
- 执行 Shell 命令检查项目状态
- 结合 MCP 搜索解决问题
- 多工具协作完成复杂任务

### 06_research_assistant.py - 研究助手

展示信息收集和整理场景：
- 使用 MCP Bing 搜索获取信息
- 多次搜索整合信息
- 生成结构化研究报告
- 对比分析和总结

**注意：** 需要配置 MCP Bing Search

### 07_knowledge_management.py - 个人知识管理

展示知识管理场景：
- 使用记忆工具保存用户偏好
- 查询记忆获取历史信息
- 基于记忆进行个性化推荐
- 知识积累和应用

### 08_multi_agent.py - 多 Agent 协作

展示复杂工作流场景：
- 任务分解和委托
- 专业 Agent 协作
- 文件读写操作
- 研究并生成文档

## 目录结构

```
demo/
├── __init__.py
├── config.py            # 配置管理模块
├── config.yaml          # 主配置文件
├── mcp_config.yaml      # MCP Server 配置
├── utils.py             # 公共工具函数
├── run_repl.py          # 主交互式 REPL
├── README.md
├── tools/               # 自定义工具
│   ├── __init__.py
│   └── demo_tools.py
├── scenarios/           # 场景演示脚本
│   ├── __init__.py
│   ├── 01_streaming.py
│   ├── 02_tools.py
│   ├── 03_memory.py
│   ├── 04_delegation.py
│   ├── 05_code_assistant.py
│   ├── 06_research_assistant.py
│   ├── 07_knowledge_management.py
│   └── 08_multi_agent.py
├── memory_store/        # 记忆存储
└── output/              # 场景输出文件
```

## 示例对话

```
👤 你: 你好，请介绍一下你自己
🤖 Agent: 你好！我是由 AgentForge 框架驱动的 AI 助手...

👤 你: 帮我计算 123 * 456
🤖 Agent: [调用 calculator 工具] 计算结果是 56088

👤 你: 帮我搜索 Python 异步编程的最新教程
🤖 Agent: [调用 bing_search 工具] 我找到了以下教程...

👤 你: 请记住我喜欢用 VS Code
🤖 Agent: [调用 save_memory 工具] 已记住您的偏好...
```
