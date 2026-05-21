"""P5 阶段单元测试：委托系统。"""

import pytest
import time

from agentforge.delegation import (
    DelegationConfig,
    IsolationConfig,
    DelegationResult,
    DelegationStrategy,
    DelegationManager,
)
from agentforge.delegation.config import TaskSpec, DELEGATE_BLOCKED_TOOLS
from agentforge.delegation.result import (
    DelegationStatus,
    ExitReason,
    TaskResult,
)


# ── 配置测试 ──────────────────────────────────────────────

class TestIsolationConfig:
    """IsolationConfig 测试。"""

    def test_default_config(self):
        """测试默认配置。"""
        config = IsolationConfig()

        assert config.inherit_tools is True
        assert config.inherit_memory is False
        assert config.max_iterations == 50
        assert config.timeout == 300.0

    def test_blocked_tools(self):
        """测试禁止工具。"""
        config = IsolationConfig()

        assert "delegate_task" in config.blocked_tools
        assert "clarify" in config.blocked_tools
        assert "memory" in config.blocked_tools

    def test_custom_blocked_tools(self):
        """测试自定义禁止工具。"""
        config = IsolationConfig(
            blocked_tools=frozenset(["custom_tool"]),
        )

        assert "custom_tool" in config.blocked_tools


class TestDelegationConfig:
    """DelegationConfig 测试。"""

    def test_default_config(self):
        """测试默认配置。"""
        config = DelegationConfig()

        assert config.max_depth == 1
        assert config.max_concurrent == 3
        assert config.orchestrator_enabled is True
        assert config.subagent_auto_approve is False

    def test_depth_limits(self):
        """测试深度限制。"""
        # 最小深度
        config = DelegationConfig(max_depth=0)
        assert config.max_depth == 0

        # 最大深度
        config = DelegationConfig(max_depth=3)
        assert config.max_depth == 3

    def test_concurrent_limits(self):
        """测试并发限制。"""
        config = DelegationConfig(max_concurrent=5)
        assert config.max_concurrent == 5


class TestTaskSpec:
    """TaskSpec 测试。"""

    def test_create_task(self):
        """测试创建任务。"""
        task = TaskSpec(goal="测试任务")

        assert task.goal == "测试任务"
        assert task.context is None
        assert task.role == "leaf"

    def test_task_with_context(self):
        """测试带上下文的任务。"""
        task = TaskSpec(
            goal="搜索",
            context="项目背景",
        )

        assert task.context == "项目背景"

    def test_task_to_dict(self):
        """测试任务转字典。"""
        task = TaskSpec(
            goal="测试",
            context="背景",
            role="orchestrator",
        )

        d = task.to_dict()
        assert d["goal"] == "测试"
        assert d["role"] == "orchestrator"


# ── 结果测试 ──────────────────────────────────────────────

class TestDelegationStatus:
    """DelegationStatus 测试。"""

    def test_status_values(self):
        """测试状态值。"""
        assert DelegationStatus.PENDING.value == "pending"
        assert DelegationStatus.COMPLETED.value == "completed"
        assert DelegationStatus.FAILED.value == "failed"
        assert DelegationStatus.TIMEOUT.value == "timeout"


class TestDelegationStrategy:
    """DelegationStrategy 测试。"""

    def test_strategy_values(self):
        """测试策略值。"""
        assert DelegationStrategy.SEQUENTIAL.value == "sequential"
        assert DelegationStrategy.PARALLEL.value == "parallel"
        assert DelegationStrategy.BEST_OF_N.value == "best_of_n"


class TestExitReason:
    """ExitReason 测试。"""

    def test_reason_values(self):
        """测试退出原因值。"""
        assert ExitReason.COMPLETED.value == "completed"
        assert ExitReason.MAX_ITERATIONS.value == "max_iterations"
        assert ExitReason.INTERRUPTED.value == "interrupted"


class TestTaskResult:
    """TaskResult 测试。"""

    def test_create_result(self):
        """测试创建结果。"""
        result = TaskResult(
            task_index=0,
            status=DelegationStatus.COMPLETED,
            summary="任务完成",
        )

        assert result.task_index == 0
        assert result.status == DelegationStatus.COMPLETED
        assert result.summary == "任务完成"

    def test_is_success(self):
        """测试成功判断。"""
        success = TaskResult(
            task_index=0,
            status=DelegationStatus.COMPLETED,
        )
        failed = TaskResult(
            task_index=0,
            status=DelegationStatus.FAILED,
        )

        assert success.is_success()
        assert not failed.is_success()

    def test_to_dict(self):
        """测试结果转字典。"""
        result = TaskResult(
            task_index=1,
            status=DelegationStatus.COMPLETED,
            summary="完成",
            duration_seconds=10.0,
        )

        d = result.to_dict()
        assert d["task_index"] == 1
        assert d["status"] == "completed"
        assert d["duration_seconds"] == 10.0


class TestDelegationResult:
    """DelegationResult 测试。"""

    def test_create_result(self):
        """测试创建委托结果。"""
        result = DelegationResult(
            status=DelegationStatus.COMPLETED,
            results=[
                TaskResult(task_index=0, status=DelegationStatus.COMPLETED),
            ],
        )

        assert result.status == DelegationStatus.COMPLETED
        assert len(result.results) == 1

    def test_is_success(self):
        """测试成功判断。"""
        success = DelegationResult(
            status=DelegationStatus.COMPLETED,
            results=[
                TaskResult(task_index=0, status=DelegationStatus.COMPLETED),
            ],
        )
        failed = DelegationResult(
            status=DelegationStatus.FAILED,
            results=[
                TaskResult(task_index=0, status=DelegationStatus.FAILED),
            ],
        )

        assert success.is_success()
        assert not failed.is_success()

    def test_get_summary(self):
        """测试获取摘要。"""
        result = DelegationResult(
            status=DelegationStatus.COMPLETED,
            results=[
                TaskResult(task_index=0, status=DelegationStatus.COMPLETED, summary="结果1"),
                TaskResult(task_index=1, status=DelegationStatus.COMPLETED, summary="结果2"),
            ],
        )

        summary = result.get_summary()
        assert "[1] 结果1" in summary
        assert "[2] 结果2" in summary

    def test_to_dict(self):
        """测试委托结果转字典。"""
        result = DelegationResult(
            status=DelegationStatus.COMPLETED,
            results=[TaskResult(task_index=0, status=DelegationStatus.COMPLETED)],
            strategy=DelegationStrategy.PARALLEL,
            total_duration=5.0,
        )

        d = result.to_dict()
        assert d["status"] == "completed"
        assert d["strategy"] == "parallel"
        assert d["total_duration"] == 5.0

    def test_to_json(self):
        """测试委托结果转 JSON。"""
        result = DelegationResult(
            status=DelegationStatus.COMPLETED,
            results=[TaskResult(task_index=0, status=DelegationStatus.COMPLETED)],
        )

        json_str = result.to_json()
        assert "completed" in json_str


# ── DelegationManager 测试 ──────────────────────────────────────────────

class TestDelegationManager:
    """DelegationManager 测试。"""

    def test_create_manager(self):
        """测试创建管理器。"""
        manager = DelegationManager()

        assert manager._config is not None
        assert len(manager.list_active_children()) == 0

    def test_delegate_empty_tasks(self):
        """测试空任务委托。"""
        manager = DelegationManager()

        result = manager.delegate_batch([])

        assert result.status == DelegationStatus.COMPLETED
        assert len(result.results) == 0

    def test_delegate_single_task(self):
        """测试单任务委托。"""
        manager = DelegationManager()

        result = manager.delegate(goal="测试任务")

        assert result is not None
        assert len(result.results) == 1

    def test_delegate_batch_tasks(self):
        """测试批量委托。"""
        manager = DelegationManager()

        tasks = [
            TaskSpec(goal="任务1"),
            TaskSpec(goal="任务2"),
        ]
        result = manager.delegate_batch(tasks)

        assert len(result.results) == 2

    def test_spawn_pause(self):
        """测试暂停功能。"""
        manager = DelegationManager()

        # 设置暂停
        manager.set_spawn_paused(True)
        assert manager.is_spawn_paused()

        # 委托应该失败
        result = manager.delegate(goal="测试")
        assert result.status == DelegationStatus.FAILED

        # 恢复
        manager.set_spawn_paused(False)
        assert not manager.is_spawn_paused()

    def test_depth_limit(self):
        """测试深度限制。"""
        config = DelegationConfig(max_depth=0)
        manager = DelegationManager(config)

        result = manager.delegate(goal="测试")

        assert result.status == DelegationStatus.FAILED
        assert "深度限制" in result.results[0].error

    def test_list_active_children(self):
        """测试列出活跃子 Agent。"""
        manager = DelegationManager()

        children = manager.list_active_children()
        assert len(children) == 0

    def test_interrupt_child(self):
        """测试中断子 Agent。"""
        manager = DelegationManager()

        # 中断不存在的子 Agent
        result = manager.interrupt_child("nonexistent")
        assert result is False

    def test_clear(self):
        """测试清空。"""
        manager = DelegationManager()

        manager.set_spawn_paused(True)
        manager.clear()

        assert not manager.is_spawn_paused()


# ── 集成测试 ──────────────────────────────────────────────

class TestP5Integration:
    """P5 阶段集成测试。"""

    def test_config_and_manager_integration(self):
        """测试配置与管理器集成。"""
        config = DelegationConfig(
            max_depth=2,
            max_concurrent=5,
        )
        manager = DelegationManager(config)

        assert manager._config.max_depth == 2
        assert manager._config.max_concurrent == 5

    def test_result_aggregation(self):
        """测试结果聚合。"""
        manager = DelegationManager()

        tasks = [
            TaskSpec(goal="任务A"),
            TaskSpec(goal="任务B"),
        ]
        result = manager.delegate_batch(tasks)

        # 检查总时长和 Token
        assert result.total_duration >= 0
        assert result.total_tokens["input"] >= 0
        assert result.total_tokens["output"] >= 0