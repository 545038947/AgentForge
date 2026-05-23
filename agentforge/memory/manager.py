"""Memory Manager 编排器。

管理多个 memory provider 和 MemoryStore，提供统一的预取、同步和查询接口。
参考 hermes-agent/agent/memory_manager.py。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from agentforge.memory.base import MemoryProvider
from agentforge.memory.memory_store_base import MemoryStoreBase
from agentforge.memory.memory_store import MemoryStore
from agentforge.memory.metadata import MemoryType
from agentforge.memory.extractor import (
    MemoryExtractor,
    RuleBasedExtractor,
    HybridExtractor,
    ExtractedMemory,
    create_extractor,
)
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

    负责管理多个 memory provider 和 MemoryStore，提供：
    - 统一的预取接口（prefetch_all）
    - 统一的同步接口（sync_all）
    - 工具 schema 收集
    - 系统提示构建
    - 冻结快照模式
    - 生命周期钩子

    记忆层次：
    - Layer 1: Session Memory（SessionProvider，独立管理）
    - Layer 2: Working Memory（ContextCompressor，独立管理）
    - Layer 3: Persistent Memory（MemoryStore）
    - Layer 4: External Provider（可选）

    使用示例：
        manager = MemoryManager()
        manager.register("session", InMemoryProvider())

        # 启用 MemoryStore
        manager.enable_memory_store("./memories")

        # 预取所有数据
        manager.prefetch_all()

        # 获取系统提示（包含冻结快照）
        prompt = manager.build_system_prompt()

        # 同步所有数据
        manager.sync_all()
    """

    def __init__(
        self,
        event_dispatcher: Optional[EventDispatcher] = None,
        max_workers: int = 4,
        memory_store_path: Optional[str] = None,
    ):
        """初始化记忆管理器。

        Args:
            event_dispatcher: 事件分发器
            max_workers: 并发工作线程数
            memory_store_path: MemoryStore 存储路径（可选）
        """
        self._providers: Dict[str, MemoryProvider] = {}
        self._provider_configs: Dict[str, Dict[str, Any]] = {}
        self._event_dispatcher = event_dispatcher
        self._max_workers = max_workers

        # MemoryStore（长期记忆）
        self._memory_store: Optional[MemoryStoreBase] = None
        if memory_store_path:
            self.enable_memory_store(memory_store_path)

        # 缓存
        self._cache: Dict[str, MemoryBlock] = {}
        self._cache_lock = threading.Lock()

        # 预取状态
        self._prefetched = False
        self._prefetch_lock = threading.Lock()

        # 会话状态（用于生命周期钩子）
        self._session_started = False

        # 自动提取器
        self._extractor: Optional[MemoryExtractor] = None
        self._auto_extraction_enabled = False

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

    # === MemoryStore 管理 ===

    def enable_memory_store(
        self,
        base_path: Optional[str] = None,
        store: Optional[MemoryStoreBase] = None,
        memory_char_limit: int = 2200,
        user_char_limit: int = 1375,
    ) -> None:
        """启用 MemoryStore（长期记忆）。

        支持两种方式：
        1. 传入 base_path：使用默认的 MemoryStore 实现
        2. 传入 store：使用自定义的 MemoryStoreBase 实现

        Args:
            base_path: 存储目录路径（使用默认 MemoryStore 时必填）
            store: 自定义 MemoryStoreBase 实例（优先级高于 base_path）
            memory_char_limit: MEMORY 文件字符限制（默认实现）
            user_char_limit: USER 文件字符限制（默认实现）

        示例：
            # 使用默认存储
            manager.enable_memory_store(base_path="./memories")

            # 使用自定义存储（如多用户）
            manager.enable_memory_store(
                store=MultiUserMemoryStore("./memories", user_id="user-123")
            )
        """
        if store is not None:
            # 使用自定义存储
            self._memory_store = store
            logger.debug(f"已启用自定义 MemoryStore: {type(store).__name__}")
        elif base_path is not None:
            # 使用默认存储
            self._memory_store = MemoryStore(
                base_path=base_path,
                memory_char_limit=memory_char_limit,
                user_char_limit=user_char_limit,
            )
            logger.debug(f"已启用 MemoryStore: {base_path}")
        else:
            raise ValueError("必须提供 base_path 或 store 参数")

    def disable_memory_store(self) -> None:
        """禁用 MemoryStore。"""
        if self._memory_store:
            # 同步到磁盘
            self._memory_store.sync_to_disk()
            self._memory_store = None
            logger.debug("已禁用 MemoryStore")

    def get_memory_store(self) -> Optional[MemoryStoreBase]:
        """获取 MemoryStore 实例。"""
        return self._memory_store

    def has_memory_store(self) -> bool:
        """检查是否启用了 MemoryStore。"""
        return self._memory_store is not None

    def add_memory_entry(
        self,
        target: str,
        entry: str,
        sync: bool = True,
    ) -> bool:
        """添加记忆条目到 MemoryStore。

        Args:
            target: 目标类型（memory/user）
            entry: 条目内容
            sync: 是否立即同步到磁盘

        Returns:
            是否成功添加
        """
        if not self._memory_store:
            logger.warning("MemoryStore 未启用")
            return False

        return self._memory_store.add_entry(target, entry, sync=sync)

    def get_memory_for_prompt(self, target: str) -> str:
        """获取用于系统提示的记忆块。

        返回冻结快照，保持 LLM 前缀缓存。

        Args:
            target: 目标类型（memory/user）

        Returns:
            记忆块文本
        """
        if not self._memory_store:
            return ""
        return self._memory_store.format_for_system_prompt(target)

    # === 自动记忆提取 ===

    def enable_auto_extraction(
        self,
        extractor: Optional[MemoryExtractor] = None,
        provider: Optional["Provider"] = None,
        use_llm: bool = False,
    ) -> None:
        """启用自动记忆提取。

        在对话过程中自动提取值得记忆的信息。

        Args:
            extractor: 自定义提取器（可选）
            provider: LLM Provider（用于 LLM 提取）
            use_llm: 是否使用 LLM 辅助提取

        示例：
            # 使用规则提取
            manager.enable_auto_extraction()

            # 使用 LLM 辅助提取
            manager.enable_auto_extraction(provider=openai_provider, use_llm=True)

            # 使用自定义提取器
            manager.enable_auto_extraction(extractor=my_extractor)
        """
        if extractor is not None:
            self._extractor = extractor
        else:
            self._extractor = create_extractor(provider=provider, use_llm=use_llm)

        self._auto_extraction_enabled = True
        logger.debug(f"已启用自动记忆提取: {type(self._extractor).__name__}")

    def disable_auto_extraction(self) -> None:
        """禁用自动记忆提取。"""
        self._auto_extraction_enabled = False
        self._extractor = None
        logger.debug("已禁用自动记忆提取")

    def is_auto_extraction_enabled(self) -> bool:
        """检查是否启用了自动提取。"""
        return self._auto_extraction_enabled

    def extract_and_store(
        self,
        user_message: str,
        assistant_response: str,
        sync: bool = True,
    ) -> List[ExtractedMemory]:
        """从对话中提取并存储记忆。

        Args:
            user_message: 用户消息
            assistant_response: 助手回复
            sync: 是否立即同步到磁盘

        Returns:
            提取的记忆列表
        """
        if not self._auto_extraction_enabled or not self._extractor:
            return []

        if not self._memory_store:
            logger.warning("MemoryStore 未启用，无法存储提取的记忆")
            return []

        # 提取记忆
        memories = self._extractor.extract(user_message, assistant_response)

        # 存储记忆
        for memory in memories:
            target = "memory" if memory.memory_type == MemoryType.FACT else "user"
            self._memory_store.add_entry(target, memory.content, sync=False)

        if sync and memories:
            self._memory_store.sync_to_disk()

        if memories:
            logger.debug(f"自动提取并存储了 {len(memories)} 条记忆")

        return memories

    # === 生命周期钩子 ===

    def on_session_start(self) -> None:
        """会话开始钩子。

        加载记忆并创建冻结快照。
        """
        if self._memory_store:
            self._memory_store.load_from_disk()
            # 捕获冻结快照
            self._memory_store.refresh_snapshot()

        self._session_started = True
        logger.debug("会话开始，已加载记忆")

    def on_session_end(self) -> None:
        """会话结束钩子。

        同步记忆到存储。
        """
        if self._memory_store:
            self._memory_store.sync_to_disk()
            self._memory_store.refresh_snapshot()

        self._session_started = False
        logger.debug("会话结束，已同步记忆")

    def on_turn_start(self, turn_number: int, message: str) -> None:
        """回合开始钩子。

        Args:
            turn_number: 回合编号
            message: 用户消息
        """
        # 预取相关记忆（如果需要）
        pass

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """记忆写入钩子。

        Args:
            action: 操作类型（add/remove/update）
            target: 目标类型
            content: 内容
        """
        if self._memory_store and action == "add":
            self._memory_store.add_entry(target, content)

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
                except (TimeoutError, OSError) as e:
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

        except (OSError, IOError, ValueError, TimeoutError) as e:
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
                except (OSError, IOError) as e:
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
            except (OSError, IOError, ValueError, TimeoutError) as e:
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
                except (OSError, IOError, ValueError, TimeoutError) as e:
                    logger.error(f"从 provider {name} 收集工具失败: {e}")

        return schemas

    def build_system_prompt(self, include_blocks: Optional[List[str]] = None) -> str:
        """构建系统提示。

        从各 provider 收集信息并构建系统提示。
        包含 MemoryStore 的冻结快照（保持 LLM 前缀缓存）。

        Args:
            include_blocks: 要包含的 provider 块列表，None 表示全部
                特殊值 "memory" 和 "user" 表示 MemoryStore 的块

        Returns:
            系统提示文本
        """
        parts: List[str] = []

        # 添加 MemoryStore 冻结快照（优先级最高）
        if self._memory_store and (include_blocks is None or "memory" in include_blocks):
            memory_block = self._memory_store.format_for_system_prompt("memory")
            if memory_block:
                parts.append(memory_block)

        if self._memory_store and (include_blocks is None or "user" in include_blocks):
            user_block = self._memory_store.format_for_system_prompt("user")
            if user_block:
                parts.append(user_block)

        # 添加其他 provider 的提示
        for name, provider in self._providers.items():
            if include_blocks and name not in include_blocks:
                continue

            # 检查 provider 是否有 build_prompt 方法
            if hasattr(provider, "build_prompt"):
                try:
                    prompt_block = provider.build_prompt()
                    if prompt_block:
                        parts.append(f"## {name}\n{prompt_block}")
                except (OSError, IOError, ValueError, TimeoutError) as e:
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
            except (OSError, IOError, ValueError, TimeoutError) as e:
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
        except (OSError, IOError, ValueError, TimeoutError) as e:
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
        except (OSError, json.JSONDecodeError, ValueError) as e:
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
        except (OSError, IOError) as e:
            logger.error(f"从 {provider_name}:{key} 删除失败: {e}")
            return False

    def clear_all(self) -> None:
        """清空所有 provider 的数据。"""
        for name, provider in self._providers.items():
            try:
                provider.clear()
            except (OSError, IOError, ValueError, TimeoutError) as e:
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
            except (RuntimeError, ValueError) as e:
                logger.debug(f"发射事件失败: {e}")

    def shutdown(self) -> None:
        """关闭所有存储后端，释放资源。"""
        # 关闭 MemoryStore
        if self._memory_store:
            try:
                self._memory_store.shutdown()
            except (OSError, RuntimeError) as e:
                logger.warning(f"关闭 MemoryStore 失败: {e}")

        # 关闭所有 provider
        for name, provider in self._providers.items():
            try:
                if hasattr(provider, "shutdown"):
                    provider.shutdown()
            except (OSError, RuntimeError) as e:
                logger.warning(f"关闭 provider {name} 失败: {e}")


__all__ = [
    "MemoryBlock",
    "MemoryManager",
]
