"""异常类型定义。

定义 AgentForge 框架的异常层次结构，参考 hermes-agent 的 error_classifier.py 设计。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class ErrorReason(enum.Enum):
    """错误原因分类，决定恢复策略。

    参考 hermes-agent/agent/error_classifier.py 的 FailoverReason 设计。
    """

    # 认证/授权错误
    auth = "auth"  # 认证失败（401/403），需要刷新/轮换凭证
    auth_permanent = "auth_permanent"  # 认证永久失败，需要终止

    # 计费/配额错误
    billing = "billing"  # 402 或余额耗尽，需要立即轮换凭证
    rate_limit = "rate_limit"  # 429 或配额限制，需要退避后重试

    # 服务端错误
    overloaded = "overloaded"  # 503/529，服务端过载
    server_error = "server_error"  # 500/502，内部服务器错误

    # 传输错误
    timeout = "timeout"  # 连接/读取超时
    connection_error = "connection_error"  # 网络连接错误

    # 上下文/负载错误
    context_overflow = "context_overflow"  # 上下文过长，需要压缩
    payload_too_large = "payload_too_large"  # 413，负载过大
    image_too_large = "image_too_large"  # 图片过大

    # 模型错误
    model_not_found = "model_not_found"  # 404 或无效模型
    provider_policy_blocked = "provider_policy_blocked"  # Provider 策略阻止

    # 请求格式错误
    format_error = "format_error"  # 400 错误请求

    # 工具错误
    tool_execution = "tool_execution"  # 工具执行错误
    tool_timeout = "tool_timeout"  # 工具超时
    tool_approval_denied = "tool_approval_denied"  # 工具审批被拒绝

    # 委托错误
    delegation_depth_exceeded = "delegation_depth_exceeded"  # 委托深度超限

    # 中断
    interrupt = "interrupt"  # 用户/系统中断

    # 未知错误
    unknown = "unknown"  # 未分类错误


@dataclass
class ClassifiedError:
    """结构化错误分类，包含恢复提示。

    参考 hermes-agent/agent/error_classifier.py 的 ClassifiedError 设计。
    """

    reason: ErrorReason
    message: str = ""
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    tool_name: Optional[str] = None
    error_context: Dict[str, Any] = field(default_factory=dict)

    # 恢复动作提示
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        """检查是否为认证错误。"""
        return self.reason in {ErrorReason.auth, ErrorReason.auth_permanent}

    @property
    def is_rate_limit(self) -> bool:
        """检查是否为速率限制错误。"""
        return self.reason == ErrorReason.rate_limit

    @property
    def is_context_overflow(self) -> bool:
        """检查是否为上下文溢出错误。"""
        return self.reason == ErrorReason.context_overflow

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "reason": self.reason.value,
            "message": self.message,
            "status_code": self.status_code,
            "provider": self.provider,
            "model": self.model,
            "tool_name": self.tool_name,
            "retryable": self.retryable,
            "should_compress": self.should_compress,
            "should_rotate_credential": self.should_rotate_credential,
            "should_fallback": self.should_fallback,
        }


class AgentForgeError(Exception):
    """AgentForge 基础异常类。

    所有框架异常的基类，提供统一的错误处理接口。
    """

    def __init__(
        self,
        message: str,
        reason: ErrorReason = ErrorReason.unknown,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.details = details or {}

    def to_classified(self) -> ClassifiedError:
        """转换为 ClassifiedError。"""
        return ClassifiedError(
            reason=self.reason,
            message=self.message,
            **self.details
        )

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "error": self.__class__.__name__,
            "reason": self.reason.value,
            "message": self.message,
            "details": self.details,
        }


# ── 配置错误 ──────────────────────────────────────────

class ConfigurationError(AgentForgeError):
    """配置错误。

    配置验证失败、缺失必要配置等情况。
    """

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, ErrorReason.format_error, details)


# ── Provider 错误 ──────────────────────────────────────

class ProviderError(AgentForgeError):
    """Provider 基础错误。"""

    def __init__(
        self,
        message: str,
        reason: ErrorReason = ErrorReason.unknown,
        status_code: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        if provider:
            details["provider"] = provider
        if model:
            details["model"] = model
        super().__init__(message, reason, details)
        self.status_code = status_code
        self.provider = provider
        self.model = model


class ProviderConnectionError(ProviderError):
    """Provider 连接错误。

    网络连接失败、服务不可达等情况。
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message,
            ErrorReason.connection_error,
            provider=provider,
            details=details,
        )


class ProviderRateLimitError(ProviderError):
    """Provider 速率限制错误。

    API 调用触发速率限制。
    """

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message,
            ErrorReason.rate_limit,
            status_code=429,
            provider=provider,
            model=model,
            details=details,
        )
        self.retry_after = retry_after


class ProviderResponseError(ProviderError):
    """Provider 响应错误。

    API 返回无效响应、解析失败等情况。
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        provider: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message,
            ErrorReason.format_error,
            status_code=status_code,
            provider=provider,
            details=details,
        )


class ProviderContextOverflowError(ProviderError):
    """Provider 上下文溢出错误。

    请求上下文超过模型限制。
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        approx_tokens: int = 0,
        context_length: int = 0,
        details: Optional[dict] = None,
    ):
        details = details or {}
        details["approx_tokens"] = approx_tokens
        details["context_length"] = context_length
        super().__init__(
            message,
            ErrorReason.context_overflow,
            status_code=400,
            provider=provider,
            model=model,
            details=details,
        )
        self.approx_tokens = approx_tokens
        self.context_length = context_length


# ── 工具错误 ────────────────────────────────────────────

class ToolError(AgentForgeError):
    """工具基础错误。"""

    def __init__(
        self,
        message: str,
        tool_name: str,
        reason: ErrorReason = ErrorReason.tool_execution,
        tool_call_id: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        details = details or {}
        details["tool_name"] = tool_name
        if tool_call_id:
            details["tool_call_id"] = tool_call_id
        super().__init__(message, reason, details)
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id


class ToolExecutionError(ToolError):
    """工具执行错误。

    工具执行过程中发生异常。
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        tool_call_id: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message,
            tool_name,
            ErrorReason.tool_execution,
            tool_call_id,
            details,
        )


class ToolApprovalDeniedError(ToolError):
    """工具审批被拒绝。

    用户或系统拒绝了工具执行请求。
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        reason: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        details = details or {}
        if reason:
            details["denial_reason"] = reason
        super().__init__(
            message,
            tool_name,
            ErrorReason.tool_approval_denied,
            details=details,
        )
        self.denial_reason = reason


class ToolTimeoutError(ToolError):
    """工具执行超时。"""

    def __init__(
        self,
        message: str,
        tool_name: str,
        timeout: float,
        tool_call_id: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        details = details or {}
        details["timeout"] = timeout
        super().__init__(
            message,
            tool_name,
            ErrorReason.tool_timeout,
            tool_call_id,
            details,
        )
        self.timeout = timeout


# ── 委托错误 ────────────────────────────────────────────

class DelegationError(AgentForgeError):
    """委托基础错误。"""

    def __init__(
        self,
        message: str,
        reason: ErrorReason = ErrorReason.delegation_depth_exceeded,
        details: Optional[dict] = None,
    ):
        super().__init__(message, reason, details)


class DelegationDepthExceededError(DelegationError):
    """委托深度超限。

    子 Agent 嵌套层级超过配置的最大值。
    """

    def __init__(
        self,
        message: str,
        current_depth: int,
        max_depth: int,
        details: Optional[dict] = None,
    ):
        details = details or {}
        details["current_depth"] = current_depth
        details["max_depth"] = max_depth
        super().__init__(message, ErrorReason.delegation_depth_exceeded, details)
        self.current_depth = current_depth
        self.max_depth = max_depth


# ── 上下文错误 ──────────────────────────────────────────

class ContextError(AgentForgeError):
    """上下文基础错误。"""

    def __init__(
        self,
        message: str,
        reason: ErrorReason = ErrorReason.context_overflow,
        details: Optional[dict] = None,
    ):
        super().__init__(message, reason, details)


class ContextCompressionError(ContextError):
    """上下文压缩错误。

    压缩过程中发生异常。
    """

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, ErrorReason.format_error, details)


# ── 中断异常 ────────────────────────────────────────────

class InterruptException(AgentForgeError):
    """中断异常。

    用户或系统请求中断执行。
    """

    def __init__(
        self,
        reason: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(
            reason or "执行被中断",
            ErrorReason.interrupt,
            details,
        )
        self.interrupt_reason = reason
