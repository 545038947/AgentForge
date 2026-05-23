"""委托结果类型。

定义委托执行的结果类型和策略。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class DelegationStatus(enum.Enum):
    """委托状态。"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 成功完成
    FAILED = "failed"  # 执行失败
    TIMEOUT = "timeout"  # 执行超时
    INTERRUPTED = "interrupted"  # 被中断


class DelegationStrategy(enum.Enum):
    """委托策略。"""

    SEQUENTIAL = "sequential"  # 顺序执行
    PARALLEL = "parallel"  # 并行执行
    BEST_OF_N = "best_of_n"  # 选择最佳结果


class ExitReason(enum.Enum):
    """退出原因。"""

    COMPLETED = "completed"  # 正常完成
    MAX_ITERATIONS = "max_iterations"  # 达到最大迭代
    INTERRUPTED = "interrupted"  # 被中断
    TIMEOUT = "timeout"  # 超时
    ERROR = "error"  # 错误


@dataclass
class TaskResult:
    """单个任务结果。

    属性：
        task_index: 任务索引
        status: 执行状态
        summary: 结果摘要
        error: 错误信息（如果有）
        exit_reason: 退出原因
        api_calls: API 调用次数
        duration_seconds: 执行时长（秒）
        tokens: Token 使用量
        tool_trace: 工具调用轨迹
    """

    task_index: int
    status: DelegationStatus
    summary: Optional[str] = None
    error: Optional[str] = None
    exit_reason: ExitReason = ExitReason.COMPLETED
    api_calls: int = 0
    duration_seconds: float = 0.0
    tokens: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)

    def is_success(self) -> bool:
        """是否成功。"""
        return self.status == DelegationStatus.COMPLETED

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "task_index": self.task_index,
            "status": self.status.value,
            "summary": self.summary,
            "error": self.error,
            "exit_reason": self.exit_reason.value,
            "api_calls": self.api_calls,
            "duration_seconds": self.duration_seconds,
            "tokens": self.tokens,
            "tool_trace": self.tool_trace,
        }


@dataclass
class DelegationResult:
    """委托结果。

    封装整个委托操作的结果。

    属性：
        status: 整体状态
        results: 各任务结果列表
        strategy: 执行策略
        total_duration: 总执行时长
        total_tokens: 总 Token 使用量
        best_result: 最佳结果（BEST_OF_N 策略）
    """

    status: DelegationStatus
    results: List[TaskResult] = field(default_factory=list)
    strategy: DelegationStrategy = DelegationStrategy.PARALLEL
    total_duration: float = 0.0
    total_tokens: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    best_result: Optional[TaskResult] = None

    def is_success(self) -> bool:
        """是否全部成功。"""
        return all(r.is_success() for r in self.results) if self.results else False

    def get_summary(self) -> str:
        """获取结果摘要。"""
        if not self.results:
            return ""

        summaries = []
        for r in self.results:
            if r.summary:
                prefix = f"[{r.task_index + 1}] " if len(self.results) > 1 else ""
                summaries.append(f"{prefix}{r.summary}")

        return "\n".join(summaries)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "status": self.status.value,
            "results": [r.to_dict() for r in self.results],
            "strategy": self.strategy.value,
            "total_duration": self.total_duration,
            "total_tokens": self.total_tokens,
            "best_result": self.best_result.to_dict() if self.best_result else None,
        }

    def to_json(self) -> str:
        """转换为 JSON 字符串。"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)