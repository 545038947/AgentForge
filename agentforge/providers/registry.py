"""Provider 注册表。

支持动态注册、Entry Points 发现和实例创建。
"""

from __future__ import annotations

import importlib.metadata
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Type

from agentforge.providers.base import Provider
from agentforge.types.errors import ConfigurationError

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Provider 注册表，支持动态注册和发现。

    功能：
    - 动态注册 Provider 类
    - 通过 Entry Points 发现第三方 Provider
    - 创建 Provider 实例
    - 列出已注册 Provider

    使用示例：
        # 注册 Provider
        ProviderRegistry.register("openai", OpenAIProvider)

        # 获取 Provider 类
        provider_class = ProviderRegistry.get("openai")

        # 创建实例
        provider = ProviderRegistry.create("openai", api_key="sk-xxx")

        # 列出所有 Provider
        names = ProviderRegistry.list()
    """

    _providers: Dict[str, Type[Provider]] = {}
    _lock = threading.Lock()
    _discovered = False

    @classmethod
    def register(cls, name: str, provider_class: Type[Provider]) -> None:
        """注册 Provider 类。

        Args:
            name: Provider 名称标识
            provider_class: Provider 类

        Raises:
            ConfigurationError: 如果 Provider 已注册
        """
        with cls._lock:
            name_lower = name.lower()
            if name_lower in cls._providers:
                raise ConfigurationError(
                    f"Provider '{name}' 已注册",
                    details={"existing": cls._providers[name_lower].__name__},
                )
            cls._providers[name_lower] = provider_class
            logger.debug(f"注册 Provider: {name} -> {provider_class.__name__}")

    @classmethod
    def get(cls, name: str) -> Type[Provider]:
        """获取 Provider 类。

        如果未找到，尝试通过 Entry Points 发现。

        Args:
            name: Provider 名称标识

        Returns:
            Provider 类

        Raises:
            ConfigurationError: 如果 Provider 未找到
        """
        with cls._lock:
            name_lower = name.lower()

            # 尝试从已注册中获取
            if name_lower in cls._providers:
                return cls._providers[name_lower]

            # 尝试从 Entry Points 发现
            if not cls._discovered:
                cls._discover_from_entry_points()
                cls._discovered = True

            if name_lower in cls._providers:
                return cls._providers[name_lower]

            raise ConfigurationError(
                f"Provider '{name}' 未找到",
                details={
                    "available": list(cls._providers.keys()),
                    "hint": "请确保已安装相应的 Provider 包或手动注册",
                },
            )

    @classmethod
    def list(cls) -> List[str]:
        """列出所有已注册 Provider 名称。

        Returns:
            Provider 名称列表
        """
        with cls._lock:
            # 确保已发现 Entry Points
            if not cls._discovered:
                cls._discover_from_entry_points()
                cls._discovered = True
            return sorted(cls._providers.keys())

    @classmethod
    def create(
        cls,
        name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ) -> Provider:
        """创建 Provider 实例。

        Args:
            name: Provider 名称标识
            api_key: API 密钥
            base_url: API 基础 URL
            **kwargs: 其他 Provider 参数

        Returns:
            Provider 实例
        """
        provider_class = cls.get(name)
        return provider_class(
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    @classmethod
    def _discover_from_entry_points(cls) -> None:
        """从 Entry Points 发现第三方 Provider。

        Entry Points 格式：
            [project.entry-points."agentforge.providers"]
            my_provider = "my_package:MyProvider"
        """
        try:
            # Python 3.10+ 使用 select()
            eps = importlib.metadata.entry_points()
            if hasattr(eps, "select"):
                provider_eps = eps.select(group="agentforge.providers")
            else:
                # Python 3.9 兼容
                provider_eps = eps.get("agentforge.providers", [])

            for ep in provider_eps:
                name_lower = ep.name.lower()
                if name_lower in cls._providers:
                    logger.debug(
                        f"Entry Point Provider '{ep.name}' 已注册，跳过"
                    )
                    continue

                try:
                    provider_class = ep.load()
                    if isinstance(provider_class, type) and issubclass(
                        provider_class, Provider
                    ):
                        cls._providers[name_lower] = provider_class
                        logger.debug(
                            f"从 Entry Points 发现 Provider: {ep.name} -> "
                            f"{provider_class.__name__}"
                        )
                    else:
                        logger.warning(
                            f"Entry Point '{ep.name}' 不是有效的 Provider 类"
                        )
                except Exception as e:
                    logger.warning(
                        f"加载 Entry Point Provider '{ep.name}' 失败: {e}"
                    )
        except Exception as e:
            logger.debug(f"Entry Points 发现失败: {e}")

    @classmethod
    def clear(cls) -> None:
        """清空注册表（主要用于测试）。"""
        with cls._lock:
            cls._providers.clear()
            cls._discovered = False


# ── 注册装饰器 ──────────────────────────────────────────

def register_provider(name: str) -> Callable[[Type[Provider]], Type[Provider]]:
    """Provider 注册装饰器。

    使用示例：
        @register_provider("my_provider")
        class MyProvider(Provider):
            ...
    """
    def decorator(cls: Type[Provider]) -> Type[Provider]:
        ProviderRegistry.register(name, cls)
        return cls
    return decorator


# ── 便捷函数 ──────────────────────────────────────────

def get_provider(name: str) -> Type[Provider]:
    """获取 Provider 类。"""
    return ProviderRegistry.get(name)


def list_providers() -> List[str]:
    """列出所有已注册 Provider。"""
    return ProviderRegistry.list()


def create_provider(
    name: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> Provider:
    """创建 Provider 实例。"""
    return ProviderRegistry.create(name, api_key, base_url, **kwargs)
