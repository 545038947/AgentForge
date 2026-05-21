"""工具审批系统。

提供危险操作的审批机制。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ApprovalDecision(Enum):
    """审批决定。"""

    APPROVE = "approve"  # 批准执行
    DENY = "deny"  # 拒绝执行
    APPROVE_ONCE = "approve_once"  # 批准本次（不缓存）
    APPROVE_ALL = "approve_all"  # 批准所有同类操作


@dataclass
class ApprovalRequest:
    """审批请求。

    属性：
        tool_name: 工具名称
        args: 工具参数
        reason: 审批原因
        risk_level: 风险级别（low/medium/high）
        context: 额外上下文信息
    """

    tool_name: str
    args: Dict[str, Any]
    reason: str = ""
    risk_level: str = "medium"
    context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "context": self.context,
        }


@dataclass
class ApprovalResponse:
    """审批响应。

    属性：
        decision: 审批决定
        reason: 决定原因
        cache_key: 缓存键（用于 APPROVE_ALL）
    """

    decision: ApprovalDecision
    reason: str = ""
    cache_key: Optional[str] = None


class ApprovalCallback:
    """审批回调基类。

    定义审批接口，由应用层实现具体的审批逻辑。

    使用示例：
        class ConsoleApproval(ApprovalCallback):
            def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
                print(f"工具 {request.tool_name} 请求审批")
                print(f"参数: {request.args}")
                print(f"原因: {request.reason}")

                choice = input("批准？(y/n/a=全部): ")
                if choice == "y":
                    return ApprovalResponse(decision=ApprovalDecision.APPROVE)
                elif choice == "a":
                    return ApprovalResponse(decision=ApprovalDecision.APPROVE_ALL)
                else:
                    return ApprovalResponse(decision=ApprovalDecision.DENY)
    """

    def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """请求审批。

        Args:
            request: 审批请求

        Returns:
            审批响应
        """
        raise NotImplementedError("子类必须实现 request_approval 方法")


class ApprovalManager:
    """审批管理器。

    功能：
    - 管理审批回调
    - 缓存审批决定
    - 判断是否需要审批

    使用示例：
        manager = ApprovalManager()
        manager.set_callback(ConsoleApproval())

        # 检查是否需要审批
        if manager.needs_approval(tool, args):
            response = manager.request_approval(tool, args)
            if response.decision == ApprovalDecision.DENY:
                return ToolResult(...)
    """

    def __init__(self):
        """初始化审批管理器。"""
        self._callback: Optional[ApprovalCallback] = None
        self._cache: Dict[str, ApprovalDecision] = {}
        self._auto_approve_safe: bool = True  # 自动批准安全操作

    def set_callback(self, callback: Optional[ApprovalCallback]) -> None:
        """设置审批回调。

        Args:
            callback: 审批回调实例
        """
        self._callback = callback

    def needs_approval(self, tool, args: Dict[str, Any]) -> bool:
        """判断是否需要审批。

        Args:
            tool: 工具实例
            args: 工具参数

        Returns:
            True 如果需要审批
        """
        # 检查工具是否标记为需要审批
        if not tool.requires_approval and not tool.dangerous:
            return False

        # 检查工具自定义判断
        if hasattr(tool, "should_approve"):
            return tool.should_approve(args)

        return True

    def request_approval(
        self,
        tool,
        args: Dict[str, Any],
        reason: str = "",
    ) -> ApprovalResponse:
        """请求审批。

        Args:
            tool: 工具实例
            args: 工具参数
            reason: 审批原因

        Returns:
            审批响应
        """
        tool_name = tool.name

        # 生成缓存键
        cache_key = self._make_cache_key(tool_name, args)

        # 检查缓存
        if cache_key in self._cache:
            cached_decision = self._cache[cache_key]
            if cached_decision in (ApprovalDecision.APPROVE, ApprovalDecision.APPROVE_ALL):
                return ApprovalResponse(
                    decision=ApprovalDecision.APPROVE,
                    reason="使用缓存的审批决定",
                    cache_key=cache_key,
                )

        # 确定风险级别
        risk_level = "high" if tool.dangerous else "medium"

        # 创建审批请求
        request = ApprovalRequest(
            tool_name=tool_name,
            args=args,
            reason=reason or f"工具 {tool_name} 需要审批",
            risk_level=risk_level,
        )

        # 调用审批回调
        if self._callback is None:
            # 没有回调时，默认拒绝危险操作
            logger.warning(f"没有设置审批回调，拒绝执行 {tool_name}")
            return ApprovalResponse(
                decision=ApprovalDecision.DENY,
                reason="未设置审批回调",
            )

        response = self._callback.request_approval(request)

        # 缓存 APPROVE_ALL 决定
        if response.decision == ApprovalDecision.APPROVE_ALL:
            self._cache[cache_key] = ApprovalDecision.APPROVE_ALL

        return response

    def _make_cache_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """生成缓存键。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            缓存键
        """
        # 简化参数以生成稳定的键
        import json
        try:
            args_str = json.dumps(args, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            args_str = str(args)

        return f"{tool_name}:{args_str}"

    def clear_cache(self) -> None:
        """清空审批缓存。"""
        self._cache.clear()

    def auto_approve(self, tool, args: Dict[str, Any]) -> bool:
        """自动批准安全操作。

        Args:
            tool: 工具实例
            args: 工具参数

        Returns:
            True 如果自动批准
        """
        if not self._auto_approve_safe:
            return False

        # 安全操作自动批准
        if not tool.dangerous and not tool.requires_approval:
            return True

        return False
