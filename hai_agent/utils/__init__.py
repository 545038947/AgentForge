"""工具函数模块。"""

from hai_agent.utils.platform import (
    get_platform,
    is_windows,
    is_linux,
    is_macos,
    get_home_dir,
    get_temp_dir,
)
from hai_agent.utils.logging import setup_logging, get_logger
from hai_agent.utils.model_metadata import (
    get_model_context_length,
    get_model_capabilities,
    supports_tools,
    supports_vision,
    supports_streaming,
    supports_caching,
    supports_reasoning,
    estimate_tokens,
    estimate_messages_tokens,
    get_model_family,
    is_reasoning_model,
    get_default_max_tokens,
)
from hai_agent.utils.schema_sanitizer import (
    strip_nullable_unions,
    strip_format_patterns,
    sanitize_schema,
    sanitize_tool_schema,
    sanitize_tools,
    validate_schema,
)

__all__ = [
    # platform
    "get_platform",
    "is_windows",
    "is_linux",
    "is_macos",
    "get_home_dir",
    "get_temp_dir",
    # logging
    "setup_logging",
    "get_logger",
    # model_metadata
    "get_model_context_length",
    "get_model_capabilities",
    "supports_tools",
    "supports_vision",
    "supports_streaming",
    "supports_caching",
    "supports_reasoning",
    "estimate_tokens",
    "estimate_messages_tokens",
    "get_model_family",
    "is_reasoning_model",
    "get_default_max_tokens",
    # schema_sanitizer
    "strip_nullable_unions",
    "strip_format_patterns",
    "sanitize_schema",
    "sanitize_tool_schema",
    "sanitize_tools",
    "validate_schema",
]