"""迭代预算管理。

线程安全的迭代计数器，用于限制 Agent 的最大迭代次数。
参考 hermes-agent/agent/iteration_budget.py。
"""

from __future__ import annotations

import threading
from typing import Optional


class IterationBudget:
    """线程安全的迭代计数器。

    每个 Agent（主 Agent 或子 Agent）拥有独立的迭代预算。
    主 Agent 的预算由 `max_iterations` 控制（默认 90）。
    子 Agent 的预算由 `delegation.max_iterations` 控制（默认 50）。

    使用示例：
        budget = IterationBudget(max_total=90)

        if budget.consume():
            # 执行迭代
            pass
        else:
            # 预算耗尽
            pass
    """

    def __init__(self, max_total: int):
        """初始化迭代预算。

        Args:
            max_total: 最大迭代次数
        """
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """尝试消耗一次迭代。

        Returns:
            True 如果允许继续，False 如果预算耗尽
        """
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """退还一次迭代（例如 execute_code 轮次）。"""
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        """已使用的迭代次数。"""
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        """剩余的迭代次数。"""
        with self._lock:
            return max(0, self.max_total - self._used)

    def reset(self) -> None:
        """重置计数器。"""
        with self._lock:
            self._used = 0

    def __repr__(self) -> str:
        return f"IterationBudget(used={self.used}/{self.max_total})"


__all__ = ["IterationBudget"]
