"""记忆元数据定义。

定义记忆条目的标准元数据结构，支持来源追踪、重要性评分、过期时间等。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional


class MemorySource(str, Enum):
    """记忆来源类型。"""

    USER = "user"  # 用户直接提供
    AGENT = "agent"  # Agent 推断/提取
    SYSTEM = "system"  # 系统生成
    EXTERNAL = "external"  # 外部导入


class MemoryType(str, Enum):
    """记忆类型。"""

    FACT = "fact"  # 事实记忆（用户喜欢 Python）
    PREFERENCE = "preference"  # 用户偏好（用户喜欢简洁的回答）
    CONTEXT = "context"  # 上下文信息（当前项目使用 Python 3.11）
    INSTRUCTION = "instruction"  # 用户指令（总是用中文回答）
    RELATIONSHIP = "relationship"  # 关系信息（用户是开发者）


@dataclass
class MemoryMetadata:
    """记忆条目元数据。

    提供记忆条目的丰富上下文信息，支持：
    - 来源追踪（谁提供/生成的）
    - 重要性评分（用于优先级和淘汰）
    - 过期时间（支持时间衰减）
    - 关联信息（与其他记忆的关系）

    Attributes:
        source: 记忆来源
        memory_type: 记忆类型
        importance: 重要性评分 (0.0-1.0)
        created_at: 创建时间
        updated_at: 更新时间
        expires_at: 过期时间（可选）
        confidence: 置信度 (0.0-1.0)
        tags: 标签列表
        related_to: 关联的其他记忆键
        extra: 额外元数据
    """

    source: MemorySource = MemorySource.USER
    memory_type: MemoryType = MemoryType.FACT
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证元数据。"""
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError(f"importance 必须在 0.0-1.0 之间: {self.importance}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence 必须在 0.0-1.0 之间: {self.confidence}")

    def is_expired(self) -> bool:
        """检查记忆是否已过期。"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def should_decay(self, threshold: float = 0.1) -> bool:
        """检查记忆是否应该被衰减/淘汰。

        基于时间衰减和重要性判断。

        Args:
            threshold: 衰减阈值

        Returns:
            True 如果应该衰减
        """
        if self.importance < threshold:
            return True
        return self.is_expired()

    def get_age_hours(self) -> float:
        """获取记忆年龄（小时）。"""
        delta = datetime.now() - self.created_at
        return delta.total_seconds() / 3600

    def apply_decay(self, decay_rate: float = 0.01) -> "MemoryMetadata":
        """应用时间衰减。

        降低重要性分数，模拟记忆遗忘。

        Args:
            decay_rate: 每小时衰减率

        Returns:
            更新后的元数据
        """
        age_hours = self.get_age_hours()
        decay_factor = 1 - (decay_rate * age_hours)
        new_importance = max(0.0, self.importance * decay_factor)

        # 创建更新后的元数据
        return MemoryMetadata(
            source=self.source,
            memory_type=self.memory_type,
            importance=new_importance,
            created_at=self.created_at,
            updated_at=datetime.now(),
            expires_at=self.expires_at,
            confidence=self.confidence,
            tags=self.tags,
            related_to=self.related_to,
            extra=self.extra,
        )

    def touch(self) -> "MemoryMetadata":
        """更新访问时间，提升重要性。"""
        return MemoryMetadata(
            source=self.source,
            memory_type=self.memory_type,
            importance=min(1.0, self.importance + 0.1),
            created_at=self.created_at,
            updated_at=datetime.now(),
            expires_at=self.expires_at,
            confidence=self.confidence,
            tags=self.tags,
            related_to=self.related_to,
            extra=self.extra,
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "source": self.source.value,
            "memory_type": self.memory_type.value,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "confidence": self.confidence,
            "tags": self.tags,
            "related_to": self.related_to,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryMetadata":
        """从字典创建。"""
        return cls(
            source=MemorySource(data.get("source", "user")),
            memory_type=MemoryType(data.get("memory_type", "fact")),
            importance=data.get("importance", 0.5),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(),
            expires_at=datetime.fromisoformat(data["expires_at"])
            if data.get("expires_at")
            else None,
            confidence=data.get("confidence", 1.0),
            tags=data.get("tags", []),
            related_to=data.get("related_to", []),
            extra=data.get("extra", {}),
        )

    @classmethod
    def user_fact(
        cls,
        importance: float = 0.7,
        tags: Optional[list[str]] = None,
        **kwargs,
    ) -> "MemoryMetadata":
        """创建用户事实记忆的元数据。"""
        return cls(
            source=MemorySource.USER,
            memory_type=MemoryType.FACT,
            importance=importance,
            tags=tags or [],
            **kwargs,
        )

    @classmethod
    def agent_inferred(
        cls,
        confidence: float = 0.8,
        importance: float = 0.5,
        **kwargs,
    ) -> "MemoryMetadata":
        """创建 Agent 推断记忆的元数据。"""
        return cls(
            source=MemorySource.AGENT,
            memory_type=MemoryType.FACT,
            confidence=confidence,
            importance=importance,
            **kwargs,
        )

    @classmethod
    def user_preference(
        cls,
        importance: float = 0.8,
        **kwargs,
    ) -> "MemoryMetadata":
        """创建用户偏好记忆的元数据。"""
        return cls(
            source=MemorySource.USER,
            memory_type=MemoryType.PREFERENCE,
            importance=importance,
            **kwargs,
        )


@dataclass
class MemoryEntry:
    """完整的记忆条目（内容 + 元数据）。"""

    content: str
    metadata: MemoryMetadata
    key: Optional[str] = None  # 唯一标识符

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "key": self.key,
            "content": self.content,
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """从字典创建。"""
        return cls(
            key=data.get("key"),
            content=data["content"],
            metadata=MemoryMetadata.from_dict(data["metadata"]),
        )


__all__ = [
    "MemorySource",
    "MemoryType",
    "MemoryMetadata",
    "MemoryEntry",
]
