"""内置 Provider 模块。

导入时自动注册所有内置 Provider 到 ProviderRegistry。
"""

from hai_agent.providers.registry import ProviderRegistry
from hai_agent.providers.builtins.openai import OpenAIProvider
from hai_agent.providers.builtins.anthropic import AnthropicProvider
from hai_agent.providers.builtins.moonshot import MoonshotProvider
from hai_agent.providers.builtins.qwen import QwenProvider
from hai_agent.providers.builtins.deepseek import DeepSeekProvider
from hai_agent.providers.builtins.ollama import OllamaProvider


# 自动注册内置 Provider
ProviderRegistry.register("openai", OpenAIProvider)
ProviderRegistry.register("anthropic", AnthropicProvider)
ProviderRegistry.register("moonshot", MoonshotProvider)
ProviderRegistry.register("qwen", QwenProvider)
ProviderRegistry.register("deepseek", DeepSeekProvider)
ProviderRegistry.register("ollama", OllamaProvider)

# 注册常用别名
ProviderRegistry.register("kimi", MoonshotProvider)  # Kimi 是 Moonshot 的产品名
ProviderRegistry.register("通义千问", QwenProvider)  # 中文名称支持
ProviderRegistry.register("local", OllamaProvider)   # 本地模型别名

__all__ = [
    "OpenAIProvider",
    "AnthropicProvider",
    "MoonshotProvider",
    "QwenProvider",
    "DeepSeekProvider",
    "OllamaProvider",
]