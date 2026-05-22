"""Memory Manager 编排器。

管理多个 memory provider，提供统一的预取、同步和查询接口。
参考 hermes-agent/agent/memory_manager.py。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from agentforge.memory.base import MemoryProvider
from agentforge.events import EventType, EventDispatcher

if TYPE_CHECKING:
    from agentforge.tools import ToolSpec

logger = logging.getLogger(__name__)


class MemoryBlock:
    """记忆块。

    表示一个记忆条目的完整信息。
    """

    def __init__(
        self,
        key: str,
        value: Any,
        provider_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """初始化记忆块。

        Args:
            key: 键名
            value: 值
            provider_name: 来源 provider 名称
            metadata: 元数据
        """
        self.key = key
        self.value = value
        self.provider_name = provider_name
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "key": self.key,
            "value": self.value,
            "provider_name": self.provider_name,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return f"MemoryBlock(key={self.key!r}, provider={self.provider_name!r})"


class MemoryManager:
    """记忆管理器。

    负责管理多个 memory provider，提供：
    - 统一的预取接口（prefetch_all）
    - 统一的同步接口（sync_all）
    - 工具 schema 收集
    - 系统提示构建

    使用示例：
        manager = MemoryManager()
        manager.register("session", InMemoryProvider())
        manager.register("file", FileBasedProvider())

        # 预取所有数据
        await manager.prefetch_all()

        # 获取系统提示
        prompt = manager.build_system_prompt()

        # 同步所有数据
        await manager.sync_all()
    """

    def __init__(
        self,
        event_dispatcher: Optional[EventDispatcher] = None,
        max_workers: int = 4,
    ):
        """初始化记忆管理器。

        Args:
            event_dispatcher: 事件分发器
            max_workers: 并发工作线程数
        """
        self._providers: Dict[str, MemoryProvider] = {}
        self._provider_configs: Dict[str, Dict[str, Any]] = {}
        self._event_dispatcher = event_dispatcher
        self._max_workers = max_workers

        # 缓存
        self._cache: Dict[str, MemoryBlock] = {}
        self._cache_lock = threading.Lock()

        # 预取状态
        self._prefetched = False
        self._prefetch_lock = threading.Lock()

    def register(
        self,
        name: str,
        provider: MemoryProvider,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """注册 memory provider。

        Args:
            name: provider 名称
            provider: provider 实例
            config: provider 配置
        """
        self._providers[name] = provider
        self._provider_configs[name] = config or {}

        logger.debug(f"已注册 memory provider: {name}")

    def unregister(self, name: str) -> bool:
        """取消注册 memory provider。

        Args:
            name: provider 名称

        Returns:
            是否成功取消注册
        """
        if name in self._providers:
            del self._providers[name]
            self._provider_configs.pop(name, None)

            # 清理缓存
            with self._cache_lock:
                keys_to_remove = [
                    k for k in self._cache
                    if self._cache[k].provider_name == name
                ]
                for k in keys_to_remove:
                    del self._cache[k]

            logger.debug(f"已取消注册 memory provider: {name}")
            return True
        return False

    def get_provider(self, name: str) -> Optional[MemoryProvider]:
        """获取指定 provider。

        Args:
            name: provider 名称

        Returns:
            provider 实例，如果不存在则返回 None
        """
        return self._providers.get(name)

    def list_providers(self) -> List[str]:
        """列出所有 provider 名称。"""
        return list(self._providers.keys())

    def prefetch_all(self, keys: Optional[Dict[str, List[str]]] = None) -> Dict[str, Dict[str, Any]]:
        """预取所有 provider 的数据。

        Args:
            keys: 每个 provider 要预取的键列表，None 表示预取所有

        Returns:
            预取结果 {provider_name: {key: value}}
        """
        self._emit_event(EventType.MEMORY_PREFETCH, {"keys": keys})

        results: Dict[str, Dict[str, Any]] = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {}
            for name, provider in self._providers.items():
                provider_keys = None
                if keys and name in keys:
                    provider_keys = keys[name]

                future = executor.submit(self._prefetch_provider, name, provider, provider_keys)
                futures[future] = name

            for future in futures:
                name = futures[future]
                try:
                    results[name] = future.result(timeout=30)
                except Exception as e:
                    logger.error(f"预取 provider {name} 失败: {e}")
                    results[name] = {}

        # 更新缓存
        with self._cache_lock:
            for name, data in results.items():
                for key, value in data.items():
                    cache_key = f"{name}:{key}"
                    self._cache[cache_key] = MemoryBlock(
                        key=key,
                        value=value,
                        provider_name=name,
                    )

        with self._prefetch_lock:
            self._prefetched = True

        self._emit_event(EventType.MEMORY_PREFETCH_DONE, {
            "provider_count": len(results),
            "total_keys": sum(len(v) for v in results.values()),
        })

        return results

    def _prefetch_provider(
        self,
        name: str,
        provider: MemoryProvider,
        keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """预取单个 provider 的数据。"""
        result: Dict[str, Any] = {}

        try:
            if keys is None:
                keys = provider.list_keys()

            for key in keys:
                value = provider.load(key)
                if value is not None:
                    result[key] = value

        except Exception as e:
            logger.error(f"预取 provider {name} 数据失败: {e}")

        return result

    async def prefetch_all_async(
        self,
        keys: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """异步预取所有 provider 的数据。

        Args:
            keys: 每个 provider 要预取的键列表

        Returns:
            预取结果
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.prefetch_all, keys)

    def sync_all(self) -> Dict[str, int]:
        """同步所有 provider 的数据。

        将缓存中的数据写回 provider。

        Returns:
            每个 provider 同步的条目数
        """
        self._emit_event(EventType.MEMORY_SYNC, {})

        results: Dict[str, int] = {}

        with self._cache_lock:
            # 按 provider 分组
            provider_data: Dict[str, Dict[str, Any]] = {}
            for cache_key, block in self._cache.items():
                if block.provider_name not in provider_data:
                    provider_data[block.provider_name] = {}
                provider_data[block.provider_name][block.key] = block.value

        # 同步每个 provider
        for name, data in provider_data.items():
            provider = self._providers.get(name)
            if provider is None:
                continue

            count = 0
            for key, value in data.items():
                try:
                    provider.save(key, value)
                    count += 1
                except Exception as e:
                    logger.error(f"同步 {name}:{key} 失败: {e}")

            results[name] = count

        self._emit_event(EventType.MEMORY_SYNC_DONE, {
            "provider_counts": results,
        })

        return results

    async def sync_all_async(self) -> Dict[str, int]:
        """异步同步所有 provider 的数据。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.sync_all)

    def queue_prefetch_all(self, keys: Optional[Dict[str, List[str]]] = None) -> None:
        """队列预取（非阻塞）。

        在后台执行预取，不阻塞当前线程。

        Args:
            keys: 每个 provider 要预取的键列表
        """
        def _background_prefetch():
            try:
                self.prefetch_all(keys)
            except Exception as e:
                logger.error(f"后台预取失败: {e}")

        thread = threading.Thread(target=_background_prefetch, daemon=True)
        thread.start()

    def get_cached(self, provider_name: str, key: str) -> Optional[MemoryBlock]:
        """获取缓存的数据。

        Args:
            provider_name: provider 名称
            key: 键名

        Returns:
            记忆块，如果不存在则返回 None
        """
        cache_key = f"{provider_name}:{key}"
        with self._cache_lock:
            return self._cache.get(cache_key)

    def set_cached(self, provider_name: str, key: str, value: Any) -> None:
        """设置缓存数据。

        Args:
            provider_name: provider 名称
            key: 键名
            value: 值
        """
        cache_key = f"{provider_name}:{key}"
        with self._cache_lock:
            self._cache[cache_key] = MemoryBlock(
                key=key,
                value=value,
                provider_name=provider_name,
            )

    def invalidate_cached(self, provider_name: str, key: str) -> bool:
        """使缓存失效。

        Args:
            provider_name: provider 名称
            key: 键名

        Returns:
            是否成功使缓存失效
        """
        cache_key = f"{provider_name}:{key}"
        with self._cache_lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
        return False

    def collect_tool_schemas(self) -> List["ToolSpec"]:
        """收集所有 provider 的工具 schema。

        Returns:
            工具规格列表
        """
        from agentforge.tools import ToolSpec

        schemas: List[ToolSpec] = []

        for name, provider in self._providers.items():
            # 检查 provider 是否有 tools 属性
            if hasattr(provider, "get_tools"):
                try:
                    tools = provider.get_tools()
                    schemas.extend(tools)
                except Exception as e:
                    logger.error(f"从 provider {name} 收集工具失败: {e}")

        return schemas

    def build_system_prompt(self, include_blocks: Optional[List[str]] = None) -> str:
        """构建系统提示。

        从各 provider 收集信息并构建系统提示。

        Args:
            include_blocks: 要包含的 provider 块列表，None 表示全部

        Returns:
            系统提示文本
        """
        parts: List[str] = []

        for name, provider in self._providers.items():
            if include_blocks and name not in include_blocks:
                continue

            # 检查 provider 是否有 build_prompt 方法
            if hasattr(provider, "build_prompt"):
                try:
                    prompt_block = provider.build_prompt()
                    if prompt_block:
                        parts.append(f"## {name}\n{prompt_block}")
                except Exception as e:
                    logger.error(f"构建 provider {name} 提示失败: {e}")

            # 从缓存中获取数据
            with self._cache_lock:
                provider_blocks = [
                    block for block in self._cache.values()
                    if block.provider_name == name
                ]

            if provider_blocks:
                config = self._provider_configs.get(name, {})
                if config.get("include_in_prompt", True):
                    block_texts = []
                    for block in provider_blocks[:10]:  # 限制数量
                        if isinstance(block.value, str):
                            block_texts.append(f"- {block.key}: {block.value[:200]}")
                        else:
                            block_texts.append(f"- {block.key}: [数据]")

                    if block_texts:
                        parts.append(f"## {name}\n" + "\n".join(block_texts))

        return "\n\n".join(parts) if parts else ""

    def search_all(self, query: str, limit: int = 10) -> List[MemoryBlock]:
        """在所有 provider 中搜索。

        Args:
            query: 搜索查询
            limit: 最大结果数

        Returns:
            搜索结果列表
        """
        results: List[MemoryBlock] = []

        for name, provider in self._providers.items():
            try:
                search_results = provider.search(query, limit=limit)
                for item in search_results:
                    results.append(MemoryBlock(
                        key=item.get("key", ""),
                        value=item.get("value"),
                        provider_name=name,
                        metadata=item.get("metadata"),
                    ))
            except Exception as e:
                logger.error(f"在 provider {name} 中搜索失败: {e}")

        # 按相关性排序（简单实现：键匹配优先）
        results.sort(key=lambda b: query.lower() in b.key.lower(), reverse=True)

        return results[:limit]

    def save_to(
        self,
        provider_name: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """保存数据到指定 provider。

        Args:
            provider_name: provider 名称
            key: 键名
            value: 值
            metadata: 元数据

        Returns:
            是否成功保存
        """
        provider = self._providers.get(provider_name)
        if provider is None:
            logger.error(f"Provider {provider_name} 不存在")
            return False

        try:
            provider.save(key, value, metadata)
            self.set_cached(provider_name, key, value)
            return True
        except Exception as e:
            logger.error(f"保存到 {provider_name}:{key} 失败: {e}")
            return False

    def load_from(
        self,
        provider_name: str,
        key: str,
        use_cache: bool = True,
    ) -> Optional[Any]:
        """从指定 provider 加载数据。

        Args:
            provider_name: provider 名称
            key: 键名
            use_cache: 是否使用缓存

        Returns:
            加载的值，如果不存在则返回 None
        """
        # 先检查缓存
        if use_cache:
            cached = self.get_cached(provider_name, key)
            if cached is not None:
                return cached.value

        provider = self._providers.get(provider_name)
        if provider is None:
            logger.error(f"Provider {provider_name} 不存在")
            return None

        try:
            value = provider.load(key)
            if value is not None:
                self.set_cached(provider_name, key, value)
            return value
        except Exception as e:
            logger.error(f"从 {provider_name}:{key} 加载失败: {e}")
            return None

    def delete_from(self, provider_name: str, key: str) -> bool:
        """从指定 provider 删除数据。

        Args:
            provider_name: provider 名称
            key: 键名

        Returns:
            是否成功删除
        """
        provider = self._providers.get(provider_name)
        if provider is None:
            logger.error(f"Provider {provider_name} 不存在")
            return False

        try:
            result = provider.delete(key)
            if result:
                self.invalidate_cached(provider_name, key)
            return result
        except Exception as e:
            logger.error(f"从 {provider_name}:{key} 删除失败: {e}")
            return False

    def clear_all(self) -> None:
        """清空所有 provider 的数据。"""
        for name, provider in self._providers.items():
            try:
                provider.clear()
            except Exception as e:
                logger.error(f"清空 provider {name} 失败: {e}")

        with self._cache_lock:
            self._cache.clear()

        with self._prefetch_lock:
            self._prefetched = False

    def is_prefetched(self) -> bool:
        """检查是否已预取。"""
        with self._prefetch_lock:
            return self._prefetched

    def _emit_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """发射事件。

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self._event_dispatcher:
            try:
                self._event_dispatcher.dispatch(event_type, data)
            except Exception as e:
                logger.debug(f"发射事件失败: {e}")


__all__ = [
    "MemoryBlock",
    "MemoryManager",
]
