"""Provider 认证注册表。

管理 Provider 的认证信息，支持多来源优先级。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import yaml


@dataclass
class ProviderCredentials:
    """Provider 认证凭证。

    不直接暴露 API Key，通过属性访问。

    属性：
        provider: Provider 名称
        api_key: API 密钥
        base_url: API 基础 URL
        api_mode: API 模式 (chat_completions / anthropic / etc)
        extra_headers: 额外的请求头
    """

    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_mode: Optional[str] = None
    extra_headers: Dict[str, str] = field(default_factory=dict)


class ProviderRegistry:
    """Provider 认证信息注册表。

    认证优先级（从高到低）：
    1. 运行时覆盖（代码显式传入）
    2. 配置文件（providers.yaml）
    3. 环境变量

    使用示例：
        registry = ProviderRegistry()
        registry.register("openai", ProviderCredentials(
            provider="openai",
            api_key="sk-xxx",
        ))
        registry.load_from_config("providers.yaml")

        if registry.is_available("openai"):
            cred = registry.get_credentials("openai")
    """

    def __init__(self):
        """初始化注册表。"""
        # 运行时覆盖（最高优先级）
        self._runtime_overrides: Dict[str, ProviderCredentials] = {}
        # 配置文件凭证
        self._config_credentials: Dict[str, ProviderCredentials] = {}
        # Provider Profile 信息（用于环境变量加载）
        self._provider_profiles: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        provider: str,
        credentials: ProviderCredentials,
        override: bool = False,
    ) -> None:
        """注册 Provider 凭证。

        Args:
            provider: Provider 名称
            credentials: 凭证对象
            override: 是否作为运行时覆盖（优先级最高）
        """
        if override:
            self._runtime_overrides[provider] = credentials
        else:
            self._config_credentials[provider] = credentials

    def get_credentials(self, provider: str) -> Optional[ProviderCredentials]:
        """获取 Provider 凭证（按优先级）。

        优先级：运行时覆盖 > 配置文件 > 环境变量

        Args:
            provider: Provider 名称

        Returns:
            凭证对象，如果不存在则返回 None
        """
        # 1. 运行时覆盖
        if cred := self._runtime_overrides.get(provider):
            return cred

        # 2. 配置文件
        if cred := self._config_credentials.get(provider):
            return cred

        # 3. 环境变量
        return self._load_from_env(provider)

    def is_available(self, provider: str) -> bool:
        """检查 Provider 是否可用（有凭证）。

        Args:
            provider: Provider 名称

        Returns:
            是否可用
        """
        cred = self.get_credentials(provider)
        return cred is not None and cred.api_key is not None

    @contextmanager
    def acquire(self, provider: str) -> Iterator[Optional[ProviderCredentials]]:
        """获取执行槽位。

        预留用于 Rate Limit 控制。

        Args:
            provider: Provider 名称

        Yields:
            凭证对象
        """
        yield self.get_credentials(provider)

    def load_from_config(self, path: Path) -> None:
        """从配置文件加载凭证。

        支持环境变量引用：${ENV_VAR}

        Args:
            path: 配置文件路径
        """
        if not path.exists():
            return

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        providers = data.get("providers", {})
        for provider_name, config in providers.items():
            if not isinstance(config, dict):
                continue

            # 解析环境变量引用
            api_key = config.get("api_key")
            if api_key and isinstance(api_key, str) and api_key.startswith("${"):
                env_var = api_key[2:-1]  # 提取 ${...} 中的变量名
                api_key = os.getenv(env_var)

            cred = ProviderCredentials(
                provider=provider_name,
                api_key=api_key,
                base_url=config.get("base_url"),
                api_mode=config.get("api_mode"),
                extra_headers=config.get("extra_headers", {}),
            )
            self._config_credentials[provider_name] = cred

    def _load_from_env(self, provider: str) -> Optional[ProviderCredentials]:
        """从环境变量加载凭证。

        Args:
            provider: Provider 名称

        Returns:
            凭证对象，如果不存在则返回 None
        """
        # 尝试从 ProviderProfile 获取环境变量名
        profile = self._provider_profiles.get(provider, {})
        env_vars = profile.get("env_vars", [])

        # 也尝试标准命名
        provider_upper = provider.upper().replace("-", "_")
        env_vars = env_vars or [f"{provider_upper}_API_KEY"]

        for env_var in env_vars:
            api_key = os.getenv(env_var)
            if api_key:
                return ProviderCredentials(
                    provider=provider,
                    api_key=api_key,
                    base_url=profile.get("base_url"),
                )

        return None

    def set_provider_profile(
        self,
        provider: str,
        profile: Dict[str, Any],
    ) -> None:
        """设置 Provider Profile 信息。

        用于环境变量加载时获取 env_vars 和 base_url。

        Args:
            provider: Provider 名称
            profile: Profile 信息
        """
        self._provider_profiles[provider] = profile

    def list_available(self) -> list[str]:
        """列出所有可用的 Provider。

        Returns:
            可用的 Provider 名称列表
        """
        all_providers = set(self._runtime_overrides.keys())
        all_providers.update(self._config_credentials.keys())
        all_providers.update(self._provider_profiles.keys())

        return [p for p in all_providers if self.is_available(p)]