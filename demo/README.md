# AgentForge Demo

AgentForge 框架完整功能演示，验证核心功能可用性。

## 功能演示

- ✅ **流式响应** - 同步/异步流式输出，实时显示
- ✅ **工具调用** - 自定义工具定义和执行
- ✅ **记忆系统** - 跨会话记忆持久化和恢复
- ✅ **委托系统** - 子 Agent 创建和并行委托
- ✅ **配置管理** - YAML 配置文件支持

## 前置要求

1. Python 3.9+
2. Ollama 服务运行中

```bash
# 启动 Ollama
ollama serve

# 拉取模型（如果未安装）
ollama pull llama3.2
```

## 配置

Demo 使用 YAML 配置文件管理设置。复制并编辑 `config.yaml`：

```bash
cp config.yaml config.local.yaml
# 编辑 config.local.yaml 或直接修改 config.yaml
```

### 配置文件说明

```yaml
# Ollama 服务配置
ollama:
  base_url: "http://localhost:11434/v1"  # 服务地址
  model: "llama3.2"                       # 默认模型
  timeout: 600                            # 请求超时（秒）

# Agent 配置
agent:
  system_prompt: ""                       # 系统提示（可选）
  max_tokens: 4096                        # 最大 Token 数
  temperature: 0.7                        # 温度

# 记忆系统配置
memory:
  store_path: "./memory_store"            # 存储路径
  auto_extract: false                     # 自动提取

# 委托系统配置
delegation:
  max_concurrent: 3                       # 最大并发数
  max_depth: 2                            # 最大深度
```

## 运行方式

### 主 REPL

```bash
cd demo
python run_repl.py
```

可选参数（覆盖配置文件）：
```bash
python run_repl.py --config my_config.yaml
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
| `/config` | 显示当前配置 |
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

## 目录结构

```
demo/
├── __init__.py          # 包初始化
├── config.py            # 配置管理模块
├── config.yaml          # 默认配置文件
├── utils.py             # 公共工具函数
├── run_repl.py          # 主交互式 REPL
├── README.md            # 使用说明
├── tools/               # 自定义工具
│   ├── __init__.py
│   └── demo_tools.py
└── scenarios/           # 场景演示脚本
    ├── __init__.py
    ├── 01_streaming.py
    ├── 02_tools.py
    ├── 03_memory.py
    └── 04_delegation.py
```
