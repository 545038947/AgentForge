"""MemoryStore 抽象基类。

定义长期记忆存储的统一接口，支持自定义实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MemoryStoreBase(ABC):
    """长期记忆存储抽象基类。

    定义长期记忆存储的统一接口，支持：
    - 多类型记忆存储（memory/user）
    - 冻结快照模式
    - 安全扫描
    - 持久化同步

    开发者可以继承此类实现自定义存储后端，如：
    - 多用户隔离存储
    - 向量数据库存储
    - 云端存储

    使用示例：
        class MyMemoryStore(MemoryStoreBase):
            def load_from_disk(self) -> Tuple[int, int]:
                # 实现加载逻辑
                ...

            def add_entry(self, target: str, entry: str, **kwargs) -> bool:
                # 实现添加逻辑
                ...

            # 实现其他抽象方法...
    """

    @abstractmethod
    def load_from_disk(self) -> tuple[int, int]:
        """从存储加载数据。

        Returns:
            (memory_count, user_count) 加载的条目数
        """
        ...

    @abstractmethod
    def sync_to_disk(self) -> Dict[str, bool]:
        """同步数据到存储。

        Returns:
            {"memory": success, "user": success}
        """
        ...

    @abstractmethod
    def add_entry(
        self,
        target: str,
        entry: str,
        sync: bool = True,
        check_threats: bool = True,
    ) -> bool:
        """添加记忆条目。

        Args:
            target: 目标类型（memory/user）
            entry: 条目内容
            sync: 是否立即同步
            check_threats: 是否检查安全威胁

        Returns:
            是否成功添加
        """
        ...

    @abstractmethod
    def remove_entry(self, target: str, entry: str, sync: bool = True) -> bool:
        """移除记忆条目。

        Args:
            target: 目标类型（memory/user）
            entry: 条目内容
            sync: 是否立即同步

        Returns:
            是否成功移除
        """
        ...

    @abstractmethod
    def format_for_system_prompt(self, target: str) -> str:
        """获取用于系统提示的记忆块。

        返回冻结快照，保持 LLM 前缀缓存。

        Args:
            target: 目标类型（memory/user）

        Returns:
            记忆块文本
        """
        ...

    @abstractmethod
    def refresh_snapshot(self) -> None:
        """刷新冻结快照。"""
        ...

    @abstractmethod
    def scan_for_threats(self, content: str) -> List[str]:
        """扫描内容中的安全威胁模式。

        Args:
            content: 待扫描内容

        Returns:
            发现的威胁类型列表
        """
        ...

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息。

        Returns:
            统计信息字典
        """
        ...

    @property
    @abstractmethod
    def memory_entries(self) -> List[str]:
        """获取事实记忆条目。"""
        ...

    @property
    @abstractmethod
    def user_entries(self) -> List[str]:
        """获取用户偏好条目。"""
        ...

    def clear_entries(self, target: str, sync: bool = True) -> int:
        """清空指定目标的条目。

        Args:
            target: 目标类型（memory/user）
            sync: 是否立即同步

        Returns:
            清空的条目数
        """
        # 默认实现：逐个移除
        entries = self.memory_entries if target == "memory" else self.user_entries
        count = 0
        for entry in entries[:]:  # 复制避免迭代时修改
            if self.remove_entry(target, entry, sync=False):
                count += 1
        if sync:
            self.sync_to_disk()
        return count


__all__ = ["MemoryStoreBase"]
