# 自定义 Provider 指南

AgentForge 支持通过配置文件定义自定义 Provider，兼容 OpenAI、Anthropic、Ollama 三种 API 格式。

## 快速开始

### 1. 创建配置文件

创建 `custom_providers.yaml`：

```yaml
providers:
  # OpenRouter 聚合网关
  openrouter:
    api_mode: chat_completions
    base_url: https://openrouter.ai/api/v1
    env_vars: [OPENROUTER_API_KEY]
    display_name: "OpenRouter"
    description: "OpenRouter 模型聚合网关"
    default_headers:
      HTTP-Referer: https://myapp.com
      X-Title: MyApp
    supports_tools: true
    supports_vision: true

  # 本地 Ollama 服务
  my-ollama:
    api_mode: chat_completions
    base_url: http://192.168.1.100:11434/v1
    display_name: "Remote Ollama"
    supports_tools: true
```

### 2. 加载配置

```python
from pathlib import Path
from hai_agent.providers import load_custom_providers

# 加载自定义 Provider
providers = load_custom_providers(Path("custom_providers.yaml"))

# 获取 Provider 实例
openrouter = providers["openrouter"]
```

### 3. 使用自定义 Provider

```python
from hai_agent import Agent

# 直接使用自定义 Provider
agent = Agent(provider=openrouter)
response = agent.run("你好")
```

## API 模式

### chat_completions (OpenAI 兼容)

适用于：
- OpenAI 官方 API
- OpenRouter、Together AI 等聚合网关
- vLLM、Ollama、LocalAI 等本地服务
- 其他 OpenAI 兼容服务

```yaml
providers:
  my-openai-compatible:
    api_mode: chat_completions
    base_url: https://api.example.com/v1
    env_vars: [MY_API_KEY]
    supports_tools: true
    supports_streaming: true
```

### anthropic_messages (Anthropic 兼容)

适用于：
- Anthropic 官方 API
- 自建的 Anthropic 代理服务

```yaml
providers:
  my-anthropic-proxy:
    api_mode: anthropic_messages
    base_url: https://my-proxy.example.com/anthropic
    env_vars: [MY_ANTHROPIC_KEY]
    supports_tools: true
    supports_caching: true
```

## 配置字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `api_mode` | str | 否 | API 模式，默认 `chat_completions` |
| `base_url` | str | 是 | API 基础 URL |
| `api_key` | str | 否 | API 密钥，支持 `${ENV_VAR}` 引用 |
| `env_vars` | list | 否 | 环境变量名列表 |
| `display_name` | str | 否 | 显示名称 |
| `description` | str | 否 | 描述 |
| `default_headers` | dict | 否 | 默认请求头 |
| `supports_tools` | bool | 否 | 是否支持工具调用，默认 true |
| `supports_streaming` | bool | 否 | 是否支持流式，默认 true |
| `supports_vision` | bool | 否 | 是否支持视觉，默认 false |
| `supports_caching` | bool | 否 | 是否支持缓存，默认 false |
| `supports_reasoning` | bool | 否 | 是否支持推理，默认 false |

## 认证配置

### 环境变量

推荐使用环境变量管理密钥：

```yaml
providers:
  my-provider:
    env_vars: [MY_PROVIDER_API_KEY]
```

```bash
export MY_PROVIDER_API_KEY=sk-xxx
```

### 直接配置密钥

支持环境变量引用：

```yaml
providers:
  my-provider:
    api_key: ${MY_PROVIDER_API_KEY}
```

### 无需认证

本地服务通常不需要 API Key：

```yaml
providers:
  local-llm:
    api_mode: chat_completions
    base_url: http://localhost:8080/v1
```

## 编程方式创建

除了 YAML 配置，也可以直接在代码中创建：

```python
from hai_agent.providers import create_custom_provider

# 创建 OpenAI 兼容的 Provider
provider = create_custom_provider(
    name="my-provider",
    api_mode="chat_completions",
    api_key="sk-xxx",
    base_url="https://api.example.com/v1",
    supports_vision=True,
)

# 使用
from hai_agent import Agent
agent = Agent(provider=provider)
```

## 自定义请求头

某些服务需要额外的请求头：

```yaml
providers:
  openrouter:
    api_mode: chat_completions
    base_url: https://openrouter.ai/api/v1
    env_vars: [OPENROUTER_API_KEY]
    default_headers:
      HTTP-Referer: https://myapp.com
      X-Title: MyApp
```

## 与 Agent 集成

```python
from pathlib import Path
from hai_agent import Agent
from hai_agent.providers import load_custom_providers

# 加载自定义 Provider
custom_providers = load_custom_providers(Path("custom_providers.yaml"))

# 创建 Agent
agent = Agent(
    provider=custom_providers["openrouter"],
    model="anthropic/claude-3-opus",  # OpenRouter 模型格式
)

# 运行
response = agent.run("分析这段代码")
print(response.content)
```

## 与 Profile 系统集成

自定义 Provider 会自动注册 Profile：

```python
from hai_agent.providers import load_custom_providers, get_profile

# 加载自定义 Provider
load_custom_providers(Path("custom_providers.yaml"))

# 获取注册的 Profile
profile = get_profile("my-provider")
print(profile.display_name)
print(profile.base_url)
```

## 示例配置

### OpenRouter

```yaml
providers:
  openrouter:
    api_mode: chat_completions
    base_url: https://openrouter.ai/api/v1
    env_vars: [OPENROUTER_API_KEY]
    display_name: "OpenRouter"
    default_headers:
      HTTP-Referer: https://your-app.com
      X-Title: Your App
    supports_tools: true
    supports_vision: true
```

### Together AI

```yaml
providers:
  together:
    api_mode: chat_completions
    base_url: https://api.together.xyz/v1
    env_vars: [TOGETHER_API_KEY]
    display_name: "Together AI"
    supports_tools: true
```

### vLLM 本地服务

```yaml
providers:
  vllm:
    api_mode: chat_completions
    base_url: http://localhost:8000/v1
    display_name: "vLLM Local"
    supports_tools: false
```

### 远程 Ollama

```yaml
providers:
  remote-ollama:
    api_mode: chat_completions
    base_url: http://192.168.1.100:11434/v1
    display_name: "Remote Ollama"
    supports_tools: true
```
