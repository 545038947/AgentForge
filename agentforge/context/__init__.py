"""上下文管理模块。"""

from agentforge.context.estimator import TokenEstimator
from agentforge.context.compressor import ContextCompressor
from agentforge.context.prompt_caching import (
    apply_anthropic_cache_control,
    apply_cache_control_to_system,
    extract_cache_stats,
)

__all__ = [
    "TokenEstimator",
    "ContextCompressor",
    "apply_anthropic_cache_control",
    "apply_cache_control_to_system",
    "extract_cache_stats",
]