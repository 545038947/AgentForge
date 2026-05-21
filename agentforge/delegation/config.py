"""委托配置。

定义委托系统的配置选项和隔离边界。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional

from pydantic import BaseModel, Field


# 子 Agent 禁止使用的工具
DELEGATE_BLOCKED_TOOLS: FrozenSet[str] = frozenset([
    "delegate_task",  # 禁止递归委托
    "clarify",  # 禁止用户交互
    "memory",  # 禁止写入共享存储
    "send_message",  # 禁止跨平台副作用
])


class IsolationConfig(BaseModel):
    """隔离配置。

    定义子 Agent 的隔离边界和限制。

    属性：
        blocked_tools: 禁止的工具列表
        inherit_tools: 是否继承父 Agent 的工具
        inherit_memory: 是否继承父 Agent 的存储
        max_iterations: 最大迭代次数
        timeout: 执行超时（秒）
    """

    blocked_tools: FrozenSet[str] = Field(
        default_factory=lambda: DELEGATE_BLOCKED_TOOLS,
    )
    inherit_tools: bool = True
    inherit_memory: bool = False
    max_iterations: int = Field(default=50, gt=0)
    timeout: float = Field(default=300.0, gt=0)


class DelegationConfig(BaseModel):
    """委托配置。

    定义委托系统的全局配置。

    属性：
        max_depth: 最大委托深度
        max_concurrent: 最大并发子 Agent 数
        orchestrator_enabled: 是否启用编排者角色
        subagent_auto_approve: 子 Agent 是否自动批准危险操作
        isolation: 隔离配置
    """

    max_depth: int = Field(default=1, ge=0, le=3)
    max_concurrent: int = Field(default=3, gt=0, le=10)
    orchestrator_enabled: bool = True
    subagent_auto_approve: bool = False
    isolation: IsolationConfig = Field(default_factory=IsolationConfig)

    # 心跳配置
    heartbeat_interval: float = Field(default=30.0, gt=0)
    stale_threshold_idle: int = Field(default=15, gt=0)
    stale_threshold_in_tool: int = Field(default=40, gt=0)


@dataclass
class TaskSpec:
    """任务规格。

    定义单个委托任务的参数。

    属性：
        goal: 任务目标
        context: 任务上下文（可选）
        toolsets: 工具集列表（可选）
        role: 角色（leaf 或 orchestrator）
        model: 模型名称（可选）
    """

    goal: str
    context: Optional[str] = None
    toolsets: Optional[List[str]] = None
    role: str = "leaf"
    model: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "goal": self.goal,
            "context": self.context,
            "toolsets": self.toolsets,
            "role": self.role,
            "model": self.model,
        }