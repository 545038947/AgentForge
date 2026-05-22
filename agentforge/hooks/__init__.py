"""Plugin Hooks 系统。

轻量级事件驱动系统，在关键生命周期点触发处理器。
Hooks 从配置目录发现，每个包含：
  - HOOK.yaml（元数据：name, description, events list）
  - handler.py（Python handler with async def handle(event_type, context））

事件：
  - agent:start     -- Agent 开始处理消息
  - agent:step      -- 工具调用循环中的每一步
  - agent:end       -- Agent 完成处理
  - tool:before     -- 工具执行前
  - tool:after      -- 工具执行后
  - provider:before -- Provider API 调用前
  - provider:after  -- Provider API 调用后
  - session:start   -- 新会话开始
  - session:end     -- 会话结束
  - session:reset   -- 会话重置
  - command:*       -- 任意斜杠命令执行（通配符匹配）
  - delegation:start -- 委托开始
  - delegation:end   -- 委托结束

参考 hermes-agent/gateway/hooks.py。
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HookRegistry:
    """发现、加载和触发事件 hooks。

    使用示例：
        registry = HookRegistry()
        registry.discover_and_load()
        await registry.emit("agent:start", {"provider": "openai", ...})
    """

    def __init__(self, hooks_dir: Optional[Path] = None):
        """初始化 Hook Registry。

        Args:
            hooks_dir: Hooks 目录路径，默认为 ~/.agentforge/hooks
        """
        self._handlers: Dict[str, List[Callable]] = {}
        self._loaded_hooks: List[Dict[str, Any]] = []
        self._hooks_dir = hooks_dir or self._get_default_hooks_dir()

    @staticmethod
    def _get_default_hooks_dir() -> Path:
        """获取默认 hooks 目录。"""
        import os
        home = Path.home()
        return home / ".agentforge" / "hooks"

    @property
    def loaded_hooks(self) -> List[Dict[str, Any]]:
        """返回所有已加载 hooks 的元数据。"""
        return list(self._loaded_hooks)

    def _register_builtin_hooks(self) -> None:
        """注册内置 hooks。

        内置 hooks 始终激活，无需配置。
        """
        pass

    def discover_and_load(self) -> None:
        """扫描 hooks 目录并加载处理器。

        每个 hook 目录必须包含：
          - HOOK.yaml，至少包含 'name' 和 'events' 键
          - handler.py，包含顶层 'handle' 函数（同步或异步）
        """
        self._register_builtin_hooks()

        if not self._hooks_dir.exists():
            logger.debug(f"Hooks 目录不存在: {self._hooks_dir}")
            return

        for hook_dir in sorted(self._hooks_dir.iterdir()):
            if not hook_dir.is_dir():
                continue

            manifest_path = hook_dir / "HOOK.yaml"
            handler_path = hook_dir / "handler.py"

            if not manifest_path.exists() or not handler_path.exists():
                continue

            try:
                import yaml
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if not manifest or not isinstance(manifest, dict):
                    logger.warning(f"跳过 {hook_dir.name}: 无效的 HOOK.yaml")
                    continue

                hook_name = manifest.get("name", hook_dir.name)
                events = manifest.get("events", [])
                if not events:
                    logger.warning(f"跳过 {hook_name}: 未声明事件")
                    continue

                # 动态加载 handler 模块
                module_name = f"agentforge_hook_{hook_name}"
                spec = importlib.util.spec_from_file_location(module_name, handler_path)
                if spec is None or spec.loader is None:
                    logger.warning(f"跳过 {hook_name}: 无法加载 handler.py")
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(module_name, None)
                    raise

                handle_fn = getattr(module, "handle", None)
                if handle_fn is None:
                    logger.warning(f"跳过 {hook_name}: 未找到 'handle' 函数")
                    continue

                # 为每个声明的事件注册处理器
                for event in events:
                    self._handlers.setdefault(event, []).append(handle_fn)

                self._loaded_hooks.append({
                    "name": hook_name,
                    "description": manifest.get("description", ""),
                    "events": events,
                    "path": str(hook_dir),
                })

                logger.info(f"已加载 hook '{hook_name}'，事件: {events}")

            except Exception as e:
                logger.error(f"加载 hook {hook_dir.name} 失败: {e}")

    def _resolve_handlers(self, event_type: str) -> List[Callable]:
        """返回应触发 event_type 的所有处理器。

        精确匹配先触发，然后是通配符匹配（如 'command:*' 匹配 'command:reset'）。
        """
        handlers = []

        # 精确匹配
        if event_type in self._handlers:
            handlers.extend(self._handlers[event_type])

        # 通配符匹配
        for pattern, pattern_handlers in self._handlers.items():
            if pattern.endswith(":*"):
                prefix = pattern[:-1]
                if event_type.startswith(prefix):
                    handlers.extend(pattern_handlers)

        return handlers

    async def emit(self, event_type: str, context: Dict[str, Any]) -> None:
        """触发事件，调用所有匹配的处理器。

        Args:
            event_type: 事件类型
            context: 事件上下文数据

        处理器中的错误被捕获并记录，但不会阻塞主管道。
        """
        handlers = self._resolve_handlers(event_type)

        for handler in handlers:
            try:
                result = handler(event_type, context)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Hook 处理器失败 ({event_type}): {e}")

    async def emit_collect(
        self,
        event_type: str,
        context: Dict[str, Any],
    ) -> List[Any]:
        """触发事件并收集处理器返回值。

        Args:
            event_type: 事件类型
            context: 事件上下文数据

        Returns:
            处理器返回值列表（排除 None）
        """
        handlers = self._resolve_handlers(event_type)
        results: List[Any] = []

        for handler in handlers:
            try:
                result = handler(event_type, context)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(f"Hook 处理器失败 ({event_type}): {e}")

        return results

    def emit_sync(self, event_type: str, context: Dict[str, Any]) -> None:
        """同步触发事件。

        Args:
            event_type: 事件类型
            context: 事件上下文数据
        """
        handlers = self._resolve_handlers(event_type)

        for handler in handlers:
            try:
                result = handler(event_type, context)
                if asyncio.iscoroutine(result):
                    # 在同步上下文中运行异步处理器
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        asyncio.run(result)
            except Exception as e:
                logger.error(f"Hook 处理器失败 ({event_type}): {e}")

    def register(self, event_type: str, handler: Callable) -> None:
        """手动注册处理器。

        Args:
            event_type: 事件类型
            handler: 处理函数
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def unregister(self, event_type: str, handler: Callable) -> bool:
        """取消注册处理器。

        Args:
            event_type: 事件类型
            handler: 处理函数

        Returns:
            True 如果成功移除
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                return True
            except ValueError:
                return False
        return False


# 全局 Hook Registry
_global_registry: Optional[HookRegistry] = None


def get_hook_registry() -> HookRegistry:
    """获取全局 Hook Registry。"""
    if _global_registry is None:
        _global_registry = HookRegistry()
        _global_registry.discover_and_load()
    return _global_registry


def emit_hook(event_type: str, context: Dict[str, Any]) -> None:
    """同步触发事件（使用全局 registry）。"""
    get_hook_registry().emit_sync(event_type, context)


async def emit_hook_async(event_type: str, context: Dict[str, Any]) -> None:
    """异步触发事件（使用全局 registry）。"""
    await get_hook_registry().emit(event_type, context)


__all__ = [
    "HookRegistry",
    "get_hook_registry",
    "emit_hook",
    "emit_hook_async",
    "emit_hook_collect",
]


async def emit_hook_collect(event_type: str, context: Dict[str, Any]) -> List[Any]:
    """异步触发事件并收集返回值（使用全局 registry）。"""
    return await get_hook_registry().emit_collect(event_type, context)