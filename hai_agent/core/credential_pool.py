"""凭证池管理。

支持同一 Provider 的多凭证轮换，当凭证失败时自动切换到下一个。

参考 hermes-agent/agent/credential_pool.py 设计。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 状态常量
STATUS_OK = "ok"
STATUS_EXHAUSTED = "exhausted"

# 认证类型
AUTH_TYPE_API_KEY = "api_key"

# 选择策略
STRATEGY_FILL_FIRST = "fill_first"  # 优先使用第一个可用凭证
STRATEGY_ROUND_ROBIN = "round_robin"  # 轮询
STRATEGY_RANDOM = "random"  # 随机选择
STRATEGY_LEAST_USED = "least_used"  # 最少使用

SUPPORTED_STRATEGIES = {
    STRATEGY_FILL_FIRST,
    STRATEGY_ROUND_ROBIN,
    STRATEGY_RANDOM,
    STRATEGY_LEAST_USED,
}

# 凭证耗尽后的冷却时间
EXHAUSTED_TTL_401_SECONDS = 5 * 60  # 5 分钟（认证错误可能是瞬态）
EXHAUSTED_TTL_429_SECONDS = 60 * 60  # 1 小时（速率限制）
EXHAUSTED_TTL_DEFAULT_SECONDS = 60 * 60  # 1 小时


@dataclass
class PooledCredential:
    """池化凭证。

    存储单个 API 密钥及其状态。
    """

    id: str
    access_token: str  # API 密钥
    label: str = ""
    priority: int = 0
    base_url: Optional[str] = None

    # 状态追踪
    last_status: Optional[str] = None
    last_status_at: Optional[float] = None
    last_error_code: Optional[int] = None
    last_error_message: Optional[str] = None
    last_error_reset_at: Optional[float] = None

    # 使用统计
    request_count: int = 0

    # 额外数据
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PooledCredential":
        """从字典创建凭证。"""
        return cls(
            id=data.get("id", ""),
            access_token=data.get("access_token", data.get("api_key", "")),
            label=data.get("label", ""),
            priority=data.get("priority", 0),
            base_url=data.get("base_url"),
            last_status=data.get("last_status"),
            last_status_at=data.get("last_status_at"),
            last_error_code=data.get("last_error_code"),
            last_error_message=data.get("last_error_message"),
            last_error_reset_at=data.get("last_error_reset_at"),
            request_count=data.get("request_count", 0),
            extra=data.get("extra", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "id": self.id,
            "access_token": self.access_token,
            "label": self.label,
            "priority": self.priority,
            "base_url": self.base_url,
            "last_status": self.last_status,
            "last_status_at": self.last_status_at,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "last_error_reset_at": self.last_error_reset_at,
            "request_count": self.request_count,
            "extra": self.extra,
        }

    @property
    def api_key(self) -> str:
        """API 密钥别名。"""
        return self.access_token


def _exhausted_ttl(error_code: Optional[int]) -> int:
    """根据 HTTP 状态码返回冷却时间。"""
    if error_code == 401:
        return EXHAUSTED_TTL_401_SECONDS
    if error_code == 429:
        return EXHAUSTED_TTL_429_SECONDS
    return EXHAUSTED_TTL_DEFAULT_SECONDS


class CredentialPool:
    """凭证池。

    管理同一 Provider 的多个凭证，支持：
    - 自动轮换（凭证失败时切换）
    - 冷却期（避免重复使用失败凭证）
    - 多种选择策略

    使用示例：
        pool = CredentialPool([
            {"id": "key1", "access_token": "sk-xxx"},
            {"id": "key2", "access_token": "sk-yyy"},
        ])

        # 获取当前凭证
        cred = pool.current()
        if cred:
            # 使用 cred.api_key 调用 API
            pass

        # 标记凭证失败
        pool.mark_exhausted(cred, 429, {"message": "Rate limited"})

        # 切换到下一个凭证
        pool.rotate()
    """

    def __init__(
        self,
        credentials: Optional[List[Dict[str, Any]]] = None,
        strategy: str = STRATEGY_FILL_FIRST,
    ):
        """初始化凭证池。

        Args:
            credentials: 凭证列表
            strategy: 选择策略
        """
        self._entries: List[PooledCredential] = []
        self._current_index = 0
        self._strategy = strategy if strategy in SUPPORTED_STRATEGIES else STRATEGY_FILL_FIRST
        self._lock = threading.Lock()

        if credentials:
            for cred_data in credentials:
                if isinstance(cred_data, dict):
                    cred = PooledCredential.from_dict(cred_data)
                    if cred.access_token:
                        self._entries.append(cred)

        # 按优先级排序
        self._entries.sort(key=lambda e: e.priority)

    def has_credentials(self) -> bool:
        """是否有凭证。"""
        return bool(self._entries)

    def has_available(self) -> bool:
        """是否有可用凭证（未在冷却期）。"""
        return bool(self._available_entries())

    def entries(self) -> List[PooledCredential]:
        """获取所有凭证。"""
        return list(self._entries)

    def current(self) -> Optional[PooledCredential]:
        """获取当前凭证。"""
        with self._lock:
            if not self._entries:
                return None
            if self._current_index >= len(self._entries):
                self._current_index = 0
            return self._entries[self._current_index]

    def _available_entries(self) -> List[PooledCredential]:
        """获取可用凭证列表。"""
        now = time.time()
        available = []

        for entry in self._entries:
            if entry.last_status != STATUS_EXHAUSTED:
                available.append(entry)
                continue

            # 检查冷却期
            reset_at = entry.last_error_reset_at
            if reset_at is not None:
                if now < reset_at:
                    continue
            elif entry.last_status_at:
                ttl = _exhausted_ttl(entry.last_error_code)
                if now < entry.last_status_at + ttl:
                    continue

            available.append(entry)

        return available

    def select(self) -> Optional[PooledCredential]:
        """根据策略选择一个可用凭证。

        Returns:
            选中的凭证，如果没有可用凭证则返回 None
        """
        with self._lock:
            available = self._available_entries()
            if not available:
                return None

            if self._strategy == STRATEGY_FILL_FIRST:
                # 优先使用第一个可用凭证
                selected = available[0]

            elif self._strategy == STRATEGY_ROUND_ROBIN:
                # 轮询
                self._current_index = (self._current_index + 1) % len(available)
                selected = available[self._current_index % len(available)]

            elif self._strategy == STRATEGY_RANDOM:
                # 随机选择
                import random
                selected = random.choice(available)

            elif self._strategy == STRATEGY_LEAST_USED:
                # 最少使用
                selected = min(available, key=lambda e: e.request_count)

            else:
                selected = available[0]

            # 更新当前索引
            for i, entry in enumerate(self._entries):
                if entry.id == selected.id:
                    self._current_index = i
                    break

            return selected

    def rotate(self) -> Optional[PooledCredential]:
        """轮换到下一个可用凭证。

        Returns:
            新的当前凭证
        """
        with self._lock:
            available = self._available_entries()
            if not available:
                return None

            # 找到当前凭证在可用列表中的位置
            current = self.current()
            current_available_index = -1
            if current:
                for i, entry in enumerate(available):
                    if entry.id == current.id:
                        current_available_index = i
                        break

            # 选择下一个
            next_index = (current_available_index + 1) % len(available)
            selected = available[next_index]

            # 更新当前索引
            for i, entry in enumerate(self._entries):
                if entry.id == selected.id:
                    self._current_index = i
                    break

            logger.info(
                f"凭证轮换: {current.id if current else 'none'} → {selected.id}"
            )
            return selected

    def mark_exhausted(
        self,
        entry: PooledCredential,
        status_code: Optional[int] = None,
        error_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """标记凭证为耗尽状态。

        Args:
            entry: 凭证
            status_code: HTTP 状态码
            error_context: 错误上下文
        """
        with self._lock:
            error_context = error_context or {}
            now = time.time()

            # 计算重置时间
            reset_at = error_context.get("reset_at")
            if reset_at is None:
                # 从错误消息中提取重置时间
                message = error_context.get("message", "")
                reset_at = self._extract_reset_at(message, status_code)

            updated = replace(
                entry,
                last_status=STATUS_EXHAUSTED,
                last_status_at=now,
                last_error_code=status_code,
                last_error_message=error_context.get("message"),
                last_error_reset_at=reset_at,
            )

            # 更新条目
            for i, e in enumerate(self._entries):
                if e.id == entry.id:
                    self._entries[i] = updated
                    break

            logger.warning(
                f"凭证 {entry.id} 标记为耗尽 (状态码: {status_code}): "
                f"{error_context.get('message', 'unknown')}"
            )

    def mark_ok(self, entry: PooledCredential) -> None:
        """标记凭证为正常状态。"""
        with self._lock:
            updated = replace(
                entry,
                last_status=STATUS_OK,
                last_status_at=time.time(),
                request_count=entry.request_count + 1,
            )

            for i, e in enumerate(self._entries):
                if e.id == entry.id:
                    self._entries[i] = updated
                    break

    def _extract_reset_at(
        self,
        message: str,
        status_code: Optional[int],
    ) -> Optional[float]:
        """从错误消息中提取重置时间。"""
        import re

        if not message:
            return None

        # 尝试解析 "retry after X seconds" 格式
        match = re.search(
            r"retry\s+(?:after\s+)?(\d+(?:\.\d+)?)\s*(?:sec|seconds|s)\b",
            message,
            re.IGNORECASE,
        )
        if match:
            return time.time() + float(match.group(1))

        # 尝试解析 "resets at <timestamp>" 格式
        match = re.search(r"resets?\s+at\s+(\d+)", message, re.IGNORECASE)
        if match:
            try:
                ts = float(match.group(1))
                # 判断是毫秒还是秒
                if ts > 1_000_000_000_000:
                    ts /= 1000.0
                return ts
            except ValueError:
                pass

        return None

    def add(self, credential: Dict[str, Any]) -> PooledCredential:
        """添加凭证。

        Args:
            credential: 凭证数据

        Returns:
            新添加的凭证
        """
        with self._lock:
            entry = PooledCredential.from_dict(credential)
            self._entries.append(entry)
            self._entries.sort(key=lambda e: e.priority)
            return entry

    def remove(self, credential_id: str) -> bool:
        """移除凭证。

        Args:
            credential_id: 凭证 ID

        Returns:
            是否成功移除
        """
        with self._lock:
            for i, entry in enumerate(self._entries):
                if entry.id == credential_id:
                    self._entries.pop(i)
                    if self._current_index >= len(self._entries):
                        self._current_index = 0
                    return True
            return False

    def reset(self) -> None:
        """重置所有凭证状态。"""
        with self._lock:
            now = time.time()
            for i, entry in enumerate(self._entries):
                self._entries[i] = replace(
                    entry,
                    last_status=None,
                    last_status_at=None,
                    last_error_code=None,
                    last_error_message=None,
                    last_error_reset_at=None,
                )
            logger.info("所有凭证状态已重置")

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表。"""
        return [entry.to_dict() for entry in self._entries]

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        available = len(self._available_entries())
        return f"CredentialPool({len(self._entries)} entries, {available} available)"


__all__ = [
    "PooledCredential",
    "CredentialPool",
    "STATUS_OK",
    "STATUS_EXHAUSTED",
    "STRATEGY_FILL_FIRST",
    "STRATEGY_ROUND_ROBIN",
    "STRATEGY_RANDOM",
    "STRATEGY_LEAST_USED",
]