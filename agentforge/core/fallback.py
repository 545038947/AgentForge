"""Provider 回退链管理。

当主 Provider 失败时，按顺序尝试备用 Provider。
参考 hermes-agent/agent/agent_init.py 的 fallback_chain 实现。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 速率限制冷却时间（秒）
RATE_LIMIT_COOLDOWN_SECONDS = 60.0


@dataclass
class FallbackProvider:
    """回退 Provider 配置。"""

    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    priority: int = 0  # 优先级，数字越小优先级越高

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "priority": self.priority,
        }


class FallbackChain:
    """Provider 回退链。

    管理有序的备用 Provider 列表，当主 Provider 失败时按顺序尝试。

    使用示例：
        chain = FallbackChain([
            {"provider": "openai", "model": "gpt-4"},
            {"provider": "anthropic", "model": "claude-3-opus"},
        ])

        if chain.activate_next():
            current = chain.current
            # 使用 current.provider 和 current.model
    """

    def __init__(
        self,
        providers: Optional[List[Dict[str, Any]]] = None,
        cooldown_seconds: float = RATE_LIMIT_COOLDOWN_SECONDS,
    ):
        """初始化回退链。

        Args:
            providers: Provider 配置列表
            cooldown_seconds: 速率限制冷却时间（秒）
        """
        self._chain: List[FallbackProvider] = []
        self._index = 0
        self._activated = False
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: Optional[float] = None
        self._rate_limited_primary = False

        if providers:
            for p in providers:
                if isinstance(p, dict) and p.get("provider") and p.get("model"):
                    self._chain.append(FallbackProvider(
                        provider=p["provider"],
                        model=p["model"],
                        api_key=p.get("api_key"),
                        base_url=p.get("base_url"),
                        priority=p.get("priority", len(self._chain)),
                    ))

        # 按优先级排序
        self._chain.sort(key=lambda x: x.priority)

    @property
    def current(self) -> Optional[FallbackProvider]:
        """获取当前 Provider。"""
        if self._index < len(self._chain):
            return self._chain[self._index]
        return None

    @property
    def is_activated(self) -> bool:
        """是否已激活回退。"""
        return self._activated

    @property
    def has_fallback(self) -> bool:
        """是否有可用的回退 Provider。"""
        return self._index < len(self._chain)

    @property
    def remaining_count(self) -> int:
        """剩余可用的回退 Provider 数量。"""
        return max(0, len(self._chain) - self._index - 1)

    @property
    def is_in_cooldown(self) -> bool:
        """是否在冷却期。"""
        if self._cooldown_until is None:
            return False
        return time.time() < self._cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        """剩余冷却时间（秒）。"""
        if self._cooldown_until is None:
            return 0.0
        return max(0.0, self._cooldown_until - time.time())

    def activate_next(self) -> bool:
        """激活下一个回退 Provider。

        Returns:
            True 如果成功激活，False 如果没有更多回退
        """
        if self._index + 1 < len(self._chain):
            self._index += 1
            self._activated = True
            current = self.current
            logger.info(
                f"激活回退 Provider: {current.provider}/{current.model} "
                f"(索引 {self._index}/{len(self._chain) - 1})"
            )
            return True
        return False

    def mark_rate_limited(self) -> None:
        """标记主 Provider 被速率限制，启动冷却期。"""
        self._rate_limited_primary = True
        self._cooldown_until = time.time() + self._cooldown_seconds
        logger.warning(
            f"主 Provider 被速率限制，启动 {self._cooldown_seconds} 秒冷却期"
        )

    def reset(self) -> None:
        """重置到主 Provider。

        如果在冷却期内，不重置。
        """
        # 检查冷却期
        if self.is_in_cooldown and self._rate_limited_primary:
            logger.info(
                f"主 Provider 冷却期未结束，剩余 {self.cooldown_remaining:.1f} 秒"
            )
            return

        self._index = 0
        self._activated = False
        self._rate_limited_primary = False
        self._cooldown_until = None
        logger.info("重置到主 Provider")

    def force_reset(self) -> None:
        """强制重置到主 Provider（忽略冷却期）。"""
        self._index = 0
        self._activated = False
        self._rate_limited_primary = False
        self._cooldown_until = None
        logger.info("强制重置到主 Provider")

    def add(self, provider: FallbackProvider) -> None:
        """添加回退 Provider。

        Args:
            provider: Provider 配置
        """
        self._chain.append(provider)
        self._chain.sort(key=lambda x: x.priority)

    def get_all(self) -> List[FallbackProvider]:
        """获取所有 Provider。"""
        return self._chain.copy()

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表。"""
        return [p.to_dict() for p in self._chain]

    def __len__(self) -> int:
        return len(self._chain)

    def __repr__(self) -> str:
        providers = " → ".join(
            f"{p.provider}/{p.model}"
            for p in self._chain
        )
        cooldown = ""
        if self.is_in_cooldown:
            cooldown = f", cooldown={self.cooldown_remaining:.1f}s"
        return f"FallbackChain([{providers}], current={self._index}{cooldown})"


__all__ = ["FallbackProvider", "FallbackChain", "RATE_LIMIT_COOLDOWN_SECONDS"]
