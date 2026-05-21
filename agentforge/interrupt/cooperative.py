"""协作式中断系统。

提供线程安全的中断令牌和处理器，支持跨子 Agent 和工具执行的中断传播。

参考 hermes-agent 的中断机制设计：
- agent/tool_executor.py: 中断检查和 ContextVars 传播
- tools/delegate_tool.py: 子 Agent 中断传播
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InterruptToken:
    """线程安全的中断令牌，支持协作式中断。

    中断传播机制：
    1. Agent 持有主 InterruptToken
    2. 子 Agent 继承父 Agent 的 token 或创建子 token
    3. ToolExecutor worker 线程通过 ContextVars 获取 token
    4. 中断时设置标志，所有检查点立即响应

    使用模式：
    - agent.run() 返回前创建 token
    - 用户中断时调用 token.interrupt()
    - Agent 循环、子 Agent、工具执行检查 is_interrupted

    属性：
        _interrupted: 是否已中断
        _reason: 中断原因
        _lock: 线程锁
        _parent: 父令牌（用于链式传播）
    """

    _interrupted: bool = field(default=False, init=False)
    _reason: Optional[str] = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _parent: Optional["InterruptToken"] = field(default=None, init=False)

    def interrupt(self, reason: Optional[str] = None) -> None:
        """请求中断。线程安全。

        Args:
            reason: 中断原因（可选）
        """
        with self._lock:
            self._interrupted = True
            self._reason = reason

    @property
    def is_interrupted(self) -> bool:
        """检查是否已中断。线程安全。"""
        with self._lock:
            return self._interrupted

    @property
    def reason(self) -> Optional[str]:
        """获取中断原因。"""
        with self._lock:
            return self._reason

    def create_child(self) -> "InterruptToken":
        """创建子令牌，共享中断状态。

        子令牌检查时会同时检查自身和父链。

        Returns:
            新的子 InterruptToken
        """
        child = InterruptToken()
        child._parent = self
        return child

    def check(self) -> bool:
        """检查自身或父链是否中断。

        Returns:
            True 如果已中断
        """
        with self._lock:
            if self._interrupted:
                return True
        if self._parent:
            return self._parent.check()
        return False

    def reset(self) -> None:
        """重置中断状态。"""
        with self._lock:
            self._interrupted = False
            self._reason = None

    def __repr__(self) -> str:
        return f"InterruptToken(interrupted={self._interrupted}, reason={self._reason!r})"


class InterruptHandler:
    """Agent 的中断处理器，管理中断令牌和传播。

    职责：
    - 创建和管理中断令牌
    - 向子 Agent 传播中断
    - 跟踪活动的子令牌

    使用示例：
        handler = InterruptHandler()
        token = handler.create_token()

        # 在子 Agent 中
        child_token = handler.create_child_token()
        handler.register_child(child_token)

        # 中断所有
        handler.propagate_interrupt("用户取消")
    """

    def __init__(self):
        self._main_token: Optional[InterruptToken] = None
        self._child_tokens: List[InterruptToken] = []
        self._lock = threading.Lock()

    def create_token(self) -> InterruptToken:
        """创建新的中断令牌。

        Returns:
            新的 InterruptToken
        """
        token = InterruptToken()
        with self._lock:
            if self._main_token is None:
                self._main_token = token
        return token

    def create_child_token(self) -> InterruptToken:
        """创建子令牌。

        Returns:
            子 InterruptToken，与主令牌关联
        """
        with self._lock:
            if self._main_token is None:
                self._main_token = InterruptToken()
            child = self._main_token.create_child()
            self._child_tokens.append(child)
            return child

    def register_child(self, token: InterruptToken) -> None:
        """注册子 Agent 的中断令牌。

        Args:
            token: 子 Agent 的中断令牌
        """
        with self._lock:
            if token not in self._child_tokens:
                self._child_tokens.append(token)

    def unregister_child(self, token: InterruptToken) -> None:
        """取消注册子令牌。

        Args:
            token: 要移除的令牌
        """
        with self._lock:
            if token in self._child_tokens:
                self._child_tokens.remove(token)

    def propagate_interrupt(self, reason: Optional[str] = None) -> None:
        """向所有子令牌传播中断。

        Args:
            reason: 中断原因
        """
        with self._lock:
            if self._main_token:
                self._main_token.interrupt(reason)
            for child in self._child_tokens:
                child.interrupt(reason)
            self._child_tokens.clear()

    def is_interrupted(self) -> bool:
        """检查是否已中断。"""
        with self._lock:
            if self._main_token:
                return self._main_token.is_interrupted
        return False

    def reset(self) -> None:
        """重置所有令牌状态。"""
        with self._lock:
            if self._main_token:
                self._main_token.reset()
            for child in self._child_tokens:
                child.reset()

    def clear(self) -> None:
        """清空所有令牌。"""
        with self._lock:
            self._main_token = None
            self._child_tokens.clear()
