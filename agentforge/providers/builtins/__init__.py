"""内置 Provider 模块。

导入时自动注册所有内置 Provider 到 ProviderRegistry。
"""

from agentforge.providers.registry import ProviderRegistry
from agentforge.providers.builtins.openai import OpenAIProvider
from agentforge.providers.builtins.anthropic import AnthropicProvider
from agentforge.providers.builtins.moonshot import MoonshotProvider
from agentforge.providers.builtins.qwen import QwenProvider
from agentforge.providers.builtins.deepseek import DeepSeekProvider


# 自动注册内置 Provider
ProviderRegistry.register("openai", OpenAIProvider)
ProviderRegistry.register("anthropic", AnthropicProvider)
ProviderRegistry.register("moonshot", MoonshotProvider)
ProviderRegistry.register("qwen", QwenProvider)
ProviderRegistry.register("deepseek", DeepSeekProvider)

# 注册常用别名
ProviderRegistry.register("kimi", MoonshotProvider)  # Kimi 是 Moonshot 的产品名
ProviderRegistry.register("通义千问", QwenProvider)  # 中文名称支持

__all__ = [
    "OpenAIProvider",
    "AnthropicProvider",
    "MoonshotProvider",
    "QwenProvider",
    "DeepSeekProvider",
]