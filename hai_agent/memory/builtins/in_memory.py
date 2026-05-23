"""内存存储实现。

使用字典存储数据，适用于临时存储和测试。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from hai_agent.memory.base import MemoryProvider

logger = logging.getLogger(__name__)


class InMemoryProvider(MemoryProvider):
    """内存存储提供者。

    使用字典存储数据，适用于：
    - 临时存储
    - 测试环境
    - 单进程应用

    使用示例：
        memory = InMemoryProvider()
        memory.save("key", {"data": "value"})
        data = memory.load("key")
    """

    def __init__(self):
        """初始化内存存储。"""
        self._data: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """保存数据。

        Args:
            key: 键名
            value: 值
            metadata: 元数据（可选）
        """
        with self._lock:
            self._data[key] = value
            if metadata:
                self._metadata[key] = metadata.copy()

    def load(self, key: str) -> Optional[Any]:
        """加载数据。

        Args:
            key: 键名

        Returns:
            存储的值，如果不存在则返回 None
        """
        with self._lock:
            return self._data.get(key)

    def delete(self, key: str) -> bool:
        """删除数据。

        Args:
            key: 键名

        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._metadata.pop(key, None)
                return True
            return False

    def exists(self, key: str) -> bool:
        """检查键是否存在。

        Args:
            key: 键名

        Returns:
            是否存在
        """
        with self._lock:
            return key in self._data

    def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """列出所有键。

        Args:
            prefix: 键前缀过滤（可选）

        Returns:
            键名列表
        """
        with self._lock:
            keys = list(self._data.keys())
            if prefix:
                keys = [k for k in keys if k.startswith(prefix)]
            return keys

    def clear(self) -> None:
        """清空所有数据。"""
        with self._lock:
            self._data.clear()
            self._metadata.clear()

    def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """获取元数据。

        Args:
            key: 键名

        Returns:
            元数据字典，如果不存在则返回 None
        """
        with self._lock:
            return self._metadata.get(key)

    def count(self, prefix: Optional[str] = None) -> int:
        """统计键数量。

        Args:
            prefix: 键前缀过滤（可选）

        Returns:
            键数量
        """
        with self._lock:
            if prefix:
                return sum(1 for k in self._data if k.startswith(prefix))
            return len(self._data)
