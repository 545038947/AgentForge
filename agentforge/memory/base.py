"""MemoryProvider 抽象基类。

定义存储提供者的统一接口。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryProvider(ABC):
    """存储提供者抽象基类。

    定义存储系统的统一接口，支持：
    - 键值存储
    - 查询和搜索
    - 过期和清理

    使用示例：
        class MyMemory(MemoryProvider):
            def save(self, key: str, value: Any) -> None:
                # 实现保存逻辑
                ...

            def load(self, key: str) -> Optional[Any]:
                # 实现加载逻辑
                ...
    """

    @abstractmethod
    def save(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """保存数据。

        Args:
            key: 键名
            value: 值
            metadata: 元数据（可选）
        """
        ...

    @abstractmethod
    def load(self, key: str) -> Optional[Any]:
        """加载数据。

        Args:
            key: 键名

        Returns:
            存储的值，如果不存在则返回 None
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除数据。

        Args:
            key: 键名

        Returns:
            是否成功删除
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查键是否存在。

        Args:
            key: 键名

        Returns:
            是否存在
        """
        ...

    @abstractmethod
    def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """列出所有键。

        Args:
            prefix: 键前缀过滤（可选）

        Returns:
            键名列表
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空所有数据。"""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """获取数据，支持默认值。

        Args:
            key: 键名
            default: 默认值

        Returns:
            存储的值或默认值
        """
        value = self.load(key)
        return value if value is not None else default

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """设置数据（save 的别名）。

        Args:
            key: 键名
            value: 值
            metadata: 元数据（可选）
        """
        self.save(key, value, metadata)

    def update(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新数据。

        Args:
            key: 键名
            value: 新值
            metadata: 新元数据（可选）

        Returns:
            是否成功更新
        """
        if not self.exists(key):
            return False
        self.save(key, value, metadata)
        return True

    def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """获取元数据。

        Args:
            key: 键名

        Returns:
            元数据字典，如果不存在则返回 None
        """
        # 默认实现：子类可以覆盖
        return None

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索数据。

        Args:
            query: 搜索查询
            limit: 最大结果数

        Returns:
            搜索结果列表
        """
        # 默认实现：简单的键名匹配
        results = []
        for key in self.list_keys():
            if query.lower() in key.lower():
                value = self.load(key)
                if value is not None:
                    results.append({
                        "key": key,
                        "value": value,
                    })
                    if len(results) >= limit:
                        break
        return results

    def count(self, prefix: Optional[str] = None) -> int:
        """统计键数量。

        Args:
            prefix: 键前缀过滤（可选）

        Returns:
            键数量
        """
        return len(self.list_keys(prefix))
