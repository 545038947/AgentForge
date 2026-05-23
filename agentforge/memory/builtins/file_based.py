"""文件存储实现。

使用文件系统存储数据，支持持久化。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentforge.memory.base import MemoryProvider

logger = logging.getLogger(__name__)


class FileBasedProvider(MemoryProvider):
    """文件存储提供者。

    使用文件系统存储数据，适用于：
    - 持久化存储
    - 跨进程共享
    - 生产环境

    使用示例：
        memory = FileBasedProvider("/path/to/storage")
        memory.save("key", {"data": "value"})
        data = memory.load("key")
    """

    def __init__(self, base_path: str, create_dir: bool = True):
        """初始化文件存储。

        Args:
            base_path: 存储目录路径
            create_dir: 是否自动创建目录
        """
        self._base_path = Path(base_path)
        self._lock = threading.Lock()

        if create_dir:
            self._base_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, key: str) -> Path:
        """获取键对应的文件路径。

        Args:
            key: 键名

        Returns:
            文件路径
        """
        # 对键名进行安全编码
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self._base_path / f"{safe_key}.json"

    def _get_meta_path(self, key: str) -> Path:
        """获取键对应的元数据文件路径。

        Args:
            key: 键名

        Returns:
            元数据文件路径
        """
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self._base_path / f"{safe_key}.meta.json"

    def save(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """保存数据。

        Args:
            key: 键名
            value: 值
            metadata: 元数据（可选）
        """
        with self._lock:
            file_path = self._get_file_path(key)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"value": value}, f, ensure_ascii=False, indent=2)

                if metadata:
                    meta_path = self._get_meta_path(key)
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, ensure_ascii=False, indent=2)
            except (OSError, PermissionError, TypeError) as e:
                logger.error(f"保存数据失败: {e}")
                raise

    def load(self, key: str) -> Optional[Any]:
        """加载数据。

        Args:
            key: 键名

        Returns:
            存储的值，如果不存在则返回 None
        """
        with self._lock:
            file_path = self._get_file_path(key)
            if not file_path.exists():
                return None

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("value")
            except (OSError, json.JSONDecodeError, ValueError) as e:
                logger.error(f"加载数据失败: {e}")
                return None

    def delete(self, key: str) -> bool:
        """删除数据。

        Args:
            key: 键名

        Returns:
            是否成功删除
        """
        with self._lock:
            file_path = self._get_file_path(key)
            meta_path = self._get_meta_path(key)

            deleted = False
            if file_path.exists():
                file_path.unlink()
                deleted = True

            if meta_path.exists():
                meta_path.unlink()

            return deleted

    def exists(self, key: str) -> bool:
        """检查键是否存在。

        Args:
            key: 键名

        Returns:
            是否存在
        """
        with self._lock:
            return self._get_file_path(key).exists()

    def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """列出所有键。

        Args:
            prefix: 键前缀过滤（可选）

        Returns:
            键名列表
        """
        with self._lock:
            keys = []
            for file_path in self._base_path.glob("*.json"):
                if file_path.name.endswith(".meta.json"):
                    continue
                # 从文件名恢复键名
                key = file_path.stem
                if prefix is None or key.startswith(prefix):
                    keys.append(key)
            return keys

    def clear(self) -> None:
        """清空所有数据。"""
        with self._lock:
            for file_path in self._base_path.glob("*.json"):
                file_path.unlink()

    def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """获取元数据。

        Args:
            key: 键名

        Returns:
            元数据字典，如果不存在则返回 None
        """
        with self._lock:
            meta_path = self._get_meta_path(key)
            if not meta_path.exists():
                return None

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError, ValueError) as e:
                logger.error(f"加载元数据失败: {e}")
                return None
