"""Provider Profile 声明式配置。

ProviderProfile 声明式描述 Provider 的行为：认证、端点、quirks 等。
Transport 读取这些配置，而不是接收大量布尔参数。

参考 hermes-agent/providers/base.py 的设计。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sentinel for "omit temperature entirely" (某些 Provider 由服务器管理)
OMIT_TEMPERATURE = object()


def _profile_user_agent() -> str:
    """返回 User-Agent 字符串。"""
    try:
        from hai_agent import __version__
        return f"hai_agent/{__version__}"
    except (ImportError, AttributeError):
        return "hai_agent"


@dataclass
class ProviderProfile:
    """Provider Profile 基类。

    声明式设计：描述 Provider 的行为，不负责客户端构建、凭证轮换或流式处理。
    这些职责由 Agent 和 Provider 实现。

    使用示例：
        profile = ProviderProfile(
            name="openai",
            api_mode="chat_completions",
            base_url="https://api.openai.com/v1",
            env_vars=("OPENAI_API_KEY",),
        )
    """

    # ── 身份标识 ─────────────────────────────────────────────
    name: str
    api_mode: str = "chat_completions"  # chat_completions | anthropic | bedrock | gemini
    aliases: Tuple[str, ...] = ()

    # ── 人类可读元数据 ───────────────────────────────────────
    display_name: str = ""  # 显示名称，如 "OpenAI"
    description: str = ""  # 描述，如 "OpenAI GPT 系列"
    signup_url: str = ""  # 注册链接

    # ── 认证和端点 ─────────────────────────────────────────
    env_vars: Tuple[str, ...] = ()  # 环境变量名列表
    base_url: str = ""
    models_url: str = ""  # 模型列表端点，默认为 {base_url}/models
    auth_type: str = "api_key"  # api_key | oauth_device_code | oauth_external | aws_sdk
    supports_health_check: bool = True  # False → 跳过健康检查

    # ── 模型目录 ───────────────────────────────────────────
    fallback_models: Tuple[str, ...] = ()  # 模型列表获取失败时的备用列表
    hostname: str = ""  # 用于 URL→Provider 反向映射

    # ── 客户端级 quirks（客户端构建时设置）──────────────────
    default_headers: Dict[str, str] = field(default_factory=dict)

    # ── 请求级 quirks ───────────────────────────────────────
    fixed_temperature: Any = None  # None = 使用调用者默认，OMIT_TEMPERATURE = 不发送
    default_max_tokens: Optional[int] = None
    default_aux_model: str = ""  # 辅助任务使用的廉价模型

    # ── 能力声明 ───────────────────────────────────────────
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_caching: bool = False
    supports_reasoning: bool = False

    def get_hostname(self) -> str:
        """获取 Provider 的基础 hostname。

        使用显式设置的 hostname，否则从 base_url 提取。
        例如 'https://api.openai.com/v1' → 'api.openai.com'
        """
        if self.hostname:
            return self.hostname
        if self.base_url:
            from urllib.parse import urlparse
            return urlparse(self.base_url).hostname or ""
        return ""

    def prepare_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Provider 特定的消息预处理。

        在字段清理后、角色交换前调用。
        默认：直接返回。
        """
        return messages

    def build_extra_body(
        self,
        *,
        session_id: Optional[str] = None,
        **context: Any,
    ) -> Dict[str, Any]:
        """Provider 特定的 extra_body 字段。

        合并到 API kwargs 的 extra_body 中。
        默认：空字典。
        """
        return {}

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: Optional[Dict] = None,
        **context: Any,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Provider 特定的 kwargs 分配。

        返回 (extra_body_additions, top_level_kwargs)。
        Transport 将 extra_body_additions 合并到 extra_body，
        top_level_kwargs 直接合并到 api_kwargs。

        这种分离是因为某些 Provider 将 reasoning 配置放在 extra_body
        （如 OpenRouter），而其他放在顶层（如 Kimi）。

        默认：({}, {})
        """
        return {}, {}

    def fetch_models(
        self,
        *,
        api_key: Optional[str] = None,
        timeout: float = 8.0,
    ) -> Optional[List[str]]:
        """从 Provider 的模型端点获取实时模型列表。

        返回模型 ID 字符串列表，如果获取失败则返回 None。

        端点 URL 解析顺序：
          1. self.models_url（显式覆盖）
          2. self.base_url + "/models"（标准 OpenAI 兼容 fallback）
        """
        url = (self.models_url or "").strip()
        if not url:
            if not self.base_url:
                return None
            url = self.base_url.rstrip("/") + "/models"

        import json
        import urllib.request

        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", _profile_user_agent())
        for k, v in self.default_headers.items():
            req.add_header(k, v)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            items = data if isinstance(data, list) else data.get("data", [])
            return [m["id"] for m in items if isinstance(m, dict) and "id" in m]
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            logger.debug("fetch_models(%s): %s", self.name, exc)
            return None

    def get_api_key(self) -> Optional[str]:
        """从环境变量获取 API 密钥。

        按顺序尝试 env_vars 中列出的环境变量。
        """
        import os
        for env_var in self.env_vars:
            key = os.getenv(env_var)
            if key:
                return key
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "api_mode": self.api_mode,
            "aliases": list(self.aliases),
            "display_name": self.display_name,
            "description": self.description,
            "signup_url": self.signup_url,
            "env_vars": list(self.env_vars),
            "base_url": self.base_url,
            "models_url": self.models_url,
            "auth_type": self.auth_type,
            "supports_health_check": self.supports_health_check,
            "fallback_models": list(self.fallback_models),
            "hostname": self.hostname,
            "supports_tools": self.supports_tools,
            "supports_streaming": self.supports_streaming,
            "supports_vision": self.supports_vision,
            "supports_caching": self.supports_caching,
            "supports_reasoning": self.supports_reasoning,
        }


# ── 内置 Provider Profiles ──────────────────────────────────────

OPENAI_PROFILE = ProviderProfile(
    name="openai",
    api_mode="chat_completions",
    aliases=("gpt",),
    display_name="OpenAI",
    description="OpenAI GPT 系列",
    signup_url="https://platform.openai.com/",
    env_vars=("OPENAI_API_KEY",),
    base_url="https://api.openai.com/v1",
    fallback_models=("gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"),
    supports_tools=True,
    supports_streaming=True,
    supports_vision=True,
)

ANTHROPIC_PROFILE = ProviderProfile(
    name="anthropic",
    api_mode="anthropic",
    aliases=("claude",),
    display_name="Anthropic",
    description="Anthropic Claude 系列",
    signup_url="https://console.anthropic.com/",
    env_vars=("ANTHROPIC_API_KEY",),
    base_url="https://api.anthropic.com",
    fallback_models=("claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"),
    supports_tools=True,
    supports_streaming=True,
    supports_vision=True,
    supports_caching=True,
    supports_reasoning=True,
)

MOONSHOT_PROFILE = ProviderProfile(
    name="moonshot",
    api_mode="chat_completions",
    aliases=("kimi",),
    display_name="Moonshot (Kimi)",
    description="Moonshot Kimi 长上下文模型",
    signup_url="https://platform.moonshot.cn/",
    env_vars=("MOONSHOT_API_KEY",),
    base_url="https://api.moonshot.cn/v1",
    fallback_models=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
    supports_tools=True,
    supports_streaming=True,
    supports_vision=False,
)

QWEN_PROFILE = ProviderProfile(
    name="qwen",
    api_mode="chat_completions",
    aliases=("dashscope", "通义千问"),
    display_name="通义千问",
    description="阿里云通义千问系列",
    signup_url="https://dashscope.console.aliyun.com/",
    env_vars=("DASHSCOPE_API_KEY",),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    fallback_models=("qwen-turbo", "qwen-plus", "qwen-max"),
    supports_tools=True,
    supports_streaming=True,
    supports_vision=True,
)

DEEPSEEK_PROFILE = ProviderProfile(
    name="deepseek",
    api_mode="chat_completions",
    display_name="DeepSeek",
    description="DeepSeek 深度求索系列",
    signup_url="https://platform.deepseek.com/",
    env_vars=("DEEPSEEK_API_KEY",),
    base_url="https://api.deepseek.com/v1",
    fallback_models=("deepseek-chat", "deepseek-reasoner"),
    supports_tools=True,
    supports_streaming=True,
    supports_vision=False,
    supports_reasoning=True,  # deepseek-reasoner
)

OLLAMA_PROFILE = ProviderProfile(
    name="ollama",
    api_mode="chat_completions",
    aliases=("local",),
    display_name="Ollama (本地模型)",
    description="Ollama 本地和远程服务器",
    signup_url="https://ollama.com/",
    env_vars=(),  # Ollama 不需要 API Key
    base_url="http://localhost:11434/v1",
    fallback_models=("llama3.2", "llama3.1", "gemma2", "mistral"),
    supports_tools=True,  # 取决于模型
    supports_streaming=True,
    supports_vision=False,  # 取决于模型
    supports_health_check=True,
)

# Provider Profile 注册表
_PROFILE_REGISTRY: Dict[str, ProviderProfile] = {
    "openai": OPENAI_PROFILE,
    "anthropic": ANTHROPIC_PROFILE,
    "moonshot": MOONSHOT_PROFILE,
    "qwen": QWEN_PROFILE,
    "deepseek": DEEPSEEK_PROFILE,
    "ollama": OLLAMA_PROFILE,
}


def get_profile(name: str) -> Optional[ProviderProfile]:
    """获取 Provider Profile。

    Args:
        name: Provider 名称

    Returns:
        ProviderProfile 实例，如果不存在则返回 None
    """
    return _PROFILE_REGISTRY.get(name.lower())


def register_profile(profile: ProviderProfile) -> None:
    """注册 Provider Profile。

    Args:
        profile: ProviderProfile 实例
    """
    _PROFILE_REGISTRY[profile.name.lower()] = profile
    for alias in profile.aliases:
        _PROFILE_REGISTRY[alias.lower()] = profile


def list_profiles() -> List[str]:
    """列出所有已注册的 Provider 名称。"""
    return list(_PROFILE_REGISTRY.keys())


__all__ = [
    "ProviderProfile",
    "OMIT_TEMPERATURE",
    "get_profile",
    "register_profile",
    "list_profiles",
    "OPENAI_PROFILE",
    "ANTHROPIC_PROFILE",
    "MOONSHOT_PROFILE",
    "QWEN_PROFILE",
    "DEEPSEEK_PROFILE",
]