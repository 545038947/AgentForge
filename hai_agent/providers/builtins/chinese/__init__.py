"""中国大模型 Provider 模块。"""

from hai_agent.providers.builtins.chinese.moonshot import MoonshotProvider
from hai_agent.providers.builtins.chinese.qwen import QwenProvider
from hai_agent.providers.builtins.chinese.deepseek import DeepSeekProvider

__all__ = [
    "MoonshotProvider",
    "QwenProvider",
    "DeepSeekProvider",
]