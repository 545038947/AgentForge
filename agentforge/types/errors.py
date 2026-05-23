"""异常类型定义。

定义 AgentForge 框架的异常层次结构，参考 hermes-agent 的 error_classifier.py 设计。
"""

from __future__ import annotations

import enum
import json
import logging

logger = logging.getLogger(__name__)

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

    # Provider 特定错误
    thinking_signature = "thinking_signature"  # Anthropic thinking block 签名无效
    long_context_tier = "long_context_tier"  # Anthropic 长上下文层级限制
    oauth_long_context_beta_forbidden = "oauth_long_context_beta_forbidden"  # Anthropic OAuth 订阅拒绝长上下文 beta
    llama_cpp_grammar_pattern = "llama_cpp_grammar_pattern"  # llama.cpp JSON schema 语法错误

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


# ── 错误模式定义 ──────────────────────────────────────────

# 计费耗尽模式
_BILLING_PATTERNS = [
    "insufficient credits",
    "insufficient_quota",
    "insufficient balance",
    "credit balance",
    "credits have been exhausted",
    "top up your credits",
    "payment required",
    "billing hard limit",
    "exceeded your current quota",
    "account is deactivated",
    "plan does not include",
]

# 速率限制模式
_RATE_LIMIT_PATTERNS = [
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "requests per minute",
    "tokens per minute",
    "requests per day",
    "try again in",
    "please retry after",
    "resource_exhausted",
    "rate increased too quickly",
    "throttlingexception",
    "too many concurrent requests",
    "servicequotaexceededexception",
]

# 使用限制模式（需要区分计费还是速率限制）
_USAGE_LIMIT_PATTERNS = [
    "usage limit",
    "quota",
    "limit exceeded",
    "key limit exceeded",
]

# 瞬态使用限制信号
_USAGE_LIMIT_TRANSIENT_SIGNALS = [
    "try again",
    "retry",
    "resets at",
    "reset in",
    "wait",
    "requests remaining",
    "periodic",
    "window",
]

# 负载过大模式
_PAYLOAD_TOO_LARGE_PATTERNS = [
    "request entity too large",
    "payload too large",
    "error code: 413",
]

# 图片过大模式
_IMAGE_TOO_LARGE_PATTERNS = [
    "image exceeds",
    "image too large",
    "image_too_large",
    "image size exceeds",
]

# 上下文溢出模式
_CONTEXT_OVERFLOW_PATTERNS = [
    "context length",
    "context size",
    "maximum context",
    "token limit",
    "too many tokens",
    "reduce the length",
    "exceeds the limit",
    "context window",
    "prompt is too long",
    "prompt exceeds max length",
    "max_tokens",
    "maximum number of tokens",
    "exceeds the max_model_len",
    "max_model_len",
    "prompt length",
    "input is too long",
    "maximum model length",
    "context length exceeded",
    "truncating input",
    "slot context",
    "n_ctx_slot",
    "超过最大长度",
    "上下文长度",
    "input is too long",
    "max input token",
    "input token",
    "exceeds the maximum number of input tokens",
]

# 模型未找到模式
_MODEL_NOT_FOUND_PATTERNS = [
    "is not a valid model",
    "invalid model",
    "model not found",
    "model_not_found",
    "does not exist",
    "no such model",
    "unknown model",
    "unsupported model",
]

# Provider 策略阻止模式
_PROVIDER_POLICY_BLOCKED_PATTERNS = [
    "no endpoints available matching your guardrail",
    "no endpoints available matching your data policy",
    "no endpoints found matching your data policy",
]

# 认证模式
_AUTH_PATTERNS = [
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid token",
    "token expired",
    "token revoked",
    "access denied",
]

# 超时消息模式
_TIMEOUT_MESSAGE_PATTERNS = [
    "timed out",
    "turn timed out",
    "request timed out",
    "deadline exceeded",
    "operation timed out",
    "upstream timed out",
]

# 传输错误类型
_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "PoolTimeout",
    "ConnectError", "RemoteProtocolError",
    "ConnectionError", "ConnectionResetError",
    "ConnectionAbortedError", "BrokenPipeError",
    "TimeoutError", "ReadError",
    "ServerDisconnectedError",
    "SSLError", "SSLZeroReturnError", "SSLWantReadError",
    "SSLWantWriteError", "SSLEOFError", "SSLSyscallError",
    "APIConnectionError",
    "APITimeoutError",
})

# 服务器断开连接模式
_SERVER_DISCONNECT_PATTERNS = [
    "server disconnected",
    "peer closed connection",
    "connection reset by peer",
    "connection was closed",
    "network connection lost",
    "unexpected eof",
    "incomplete chunked read",
]

# SSL 瞬态错误模式
_SSL_TRANSIENT_PATTERNS = [
    "bad record mac",
    "ssl alert",
    "tls alert",
    "ssl handshake failure",
    "tlsv1 alert",
    "sslv3 alert",
    "bad_record_mac",
    "ssl_alert",
    "tls_alert",
    "tls_alert_internal_error",
    "[ssl:",
]


# ── 错误分类函数 ──────────────────────────────────────────

def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
    approx_tokens: int = 0,
    context_length: int = 200000,
    num_messages: int = 0,
) -> ClassifiedError:
    """分类 API 错误，返回结构化的恢复建议。

    优先级管道：
      1. Provider 特定模式（thinking signature、tier gate）
      2. HTTP 状态码 + 消息感知细化
      3. 错误码分类（来自响应体）
      4. 消息模式匹配
      5. SSL/TLS 瞬态错误
      6. 服务器断开 + 大会话 → 上下文溢出
      7. 传输错误启发式
      8. 回退：未知（可重试，带退避）

    Args:
        error: API 调用异常
        provider: 当前 Provider 名称
        model: 当前模型名称
        approx_tokens: 当前上下文近似 Token 数
        context_length: 当前模型最大上下文长度

    Returns:
        ClassifiedError 包含原因和恢复动作提示
    """
    status_code = _extract_status_code(error)
    error_type = type(error).__name__

    # RateLimitError 强制设为 429
    if status_code is None and error_type == "RateLimitError":
        status_code = 429

    body = _extract_error_body(error)
    error_code = _extract_error_code(body)

    # 构建综合错误消息字符串
    _raw_msg = str(error).lower()
    _body_msg = ""
    _metadata_msg = ""

    if isinstance(body, dict):
        _err_obj = body.get("error", {})
        if isinstance(_err_obj, dict):
            _body_msg = str(_err_obj.get("message") or "").lower()
            _metadata = _err_obj.get("metadata", {})
            if isinstance(_metadata, dict):
                _raw_json = _metadata.get("raw") or ""
                if isinstance(_raw_json, str) and _raw_json.strip():
                    try:
                        import json
                        _inner = json.loads(_raw_json)
                        if isinstance(_inner, dict):
                            _inner_err = _inner.get("error", {})
                            if isinstance(_inner_err, dict):
                                _metadata_msg = str(_inner_err.get("message") or "").lower()
                    except (json.JSONDecodeError, TypeError):
                        pass
        if not _body_msg:
            _body_msg = str(body.get("message") or "").lower()

    parts = [_raw_msg]
    if _body_msg and _body_msg not in _raw_msg:
        parts.append(_body_msg)
    if _metadata_msg and _metadata_msg not in _raw_msg and _metadata_msg not in _body_msg:
        parts.append(_metadata_msg)
    error_msg = " ".join(parts)

    def _result(reason: ErrorReason, **overrides) -> ClassifiedError:
        defaults = {
            "reason": reason,
            "status_code": status_code,
            "provider": provider,
            "model": model,
            "message": _extract_message(error, body),
        }
        defaults.update(overrides)
        return ClassifiedError(**defaults)

    # 1. Provider 特定模式
    # Anthropic thinking block signature
    if (
        status_code == 400
        and "signature" in error_msg
        and "thinking" in error_msg
    ):
        return _result(
            ErrorReason.thinking_signature,
            retryable=True,
            should_compress=False,
        )

    # Anthropic long-context tier gate
    if (
        status_code == 429
        and "extra usage" in error_msg
        and "long context" in error_msg
    ):
        return _result(
            ErrorReason.long_context_tier,
            retryable=True,
            should_compress=True,
        )

    # Anthropic OAuth long context beta forbidden
    if (
        status_code == 400
        and "long context beta" in error_msg
        and "not yet available" in error_msg
    ):
        return _result(
            ErrorReason.oauth_long_context_beta_forbidden,
            retryable=True,
            should_compress=False,
        )

    # llama.cpp grammar pattern
    if (
        status_code == 400
        and (
            "error parsing grammar" in error_msg
            or "json-schema-to-grammar" in error_msg
            or ("unable to generate parser" in error_msg and "template" in error_msg)
        )
    ):
        return _result(
            ErrorReason.llama_cpp_grammar_pattern,
            retryable=True,
            should_compress=False,
        )

    # xAI Grok subscription
    if (
        "do not have an active grok subscription" in error_msg
        or ("out of available resources" in error_msg and "grok" in error_msg)
    ):
        return _result(
            ErrorReason.auth,
            retryable=False,
            should_fallback=True,
        )

    # 2. HTTP 状态码分类
    if status_code is not None:
        classified = _classify_by_status(
            status_code, error_msg, error_code, body,
            provider=provider, model=model,
            approx_tokens=approx_tokens, context_length=context_length,
            num_messages=num_messages,
            result_fn=_result,
        )
        if classified is not None:
            return classified

    # 3. 错误码分类
    if error_code:
        classified = _classify_by_error_code(error_code, error_msg, _result)
        if classified is not None:
            return classified

    # 4. 消息模式匹配
    classified = _classify_by_message(
        error_msg, error_type,
        approx_tokens=approx_tokens,
        context_length=context_length,
        result_fn=_result,
    )
    if classified is not None:
        return classified

    # 5. SSL/TLS 瞬态错误
    if any(p in error_msg for p in _SSL_TRANSIENT_PATTERNS):
        return _result(ErrorReason.timeout, retryable=True)

    # 6. 服务器断开 + 大会话
    is_disconnect = any(p in error_msg for p in _SERVER_DISCONNECT_PATTERNS)
    if is_disconnect and not status_code:
        is_large = approx_tokens > context_length * 0.6 or (
            context_length <= 256000 and (approx_tokens > 120000 or num_messages > 200)
        )
        if is_large:
            return _result(
                ErrorReason.context_overflow,
                retryable=True,
                should_compress=True,
            )
        return _result(ErrorReason.timeout, retryable=True)

    # 7. 传输错误启发式
    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return _result(ErrorReason.timeout, retryable=True)

    # 8. 回退：未知
    return _result(ErrorReason.unknown, retryable=True)


def _classify_by_status(
    status_code: int,
    error_msg: str,
    error_code: str,
    body: dict,
    *,
    provider: str,
    model: str,
    approx_tokens: int,
    context_length: int,
    num_messages: int = 0,
    result_fn,
) -> Optional[ClassifiedError]:
    """基于 HTTP 状态码分类。"""

    if status_code == 401:
        return result_fn(
            ErrorReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 403:
        if "key limit exceeded" in error_msg or "spending limit" in error_msg:
            return result_fn(
                ErrorReason.billing,
                retryable=False,
                should_rotate_credential=True,
                should_fallback=True,
            )
        return result_fn(
            ErrorReason.auth,
            retryable=False,
            should_fallback=True,
        )

    if status_code == 402:
        return _classify_402(error_msg, result_fn)

    if status_code == 404:
        if any(p in error_msg for p in _PROVIDER_POLICY_BLOCKED_PATTERNS):
            return result_fn(
                ErrorReason.provider_policy_blocked,
                retryable=False,
                should_fallback=False,
            )
        if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
            return result_fn(
                ErrorReason.model_not_found,
                retryable=False,
                should_fallback=True,
            )
        return result_fn(ErrorReason.unknown, retryable=True)

    if status_code == 413:
        return result_fn(
            ErrorReason.payload_too_large,
            retryable=True,
            should_compress=True,
        )

    if status_code == 429:
        return result_fn(
            ErrorReason.rate_limit,
            retryable=True,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 400:
        return _classify_400(
            error_msg, error_code, body,
            provider=provider, model=model,
            approx_tokens=approx_tokens,
            context_length=context_length,
            num_messages=num_messages,
            result_fn=result_fn,
        )

    if status_code in {500, 502}:
        return result_fn(ErrorReason.server_error, retryable=True)

    if status_code in {503, 529}:
        return result_fn(ErrorReason.overloaded, retryable=True)

    if 400 <= status_code < 500:
        return result_fn(
            ErrorReason.format_error,
            retryable=False,
            should_fallback=True,
        )

    if 500 <= status_code < 600:
        return result_fn(ErrorReason.server_error, retryable=True)

    return None


def _classify_402(error_msg: str, result_fn) -> ClassifiedError:
    """区分 402：计费耗尽 vs 瞬态使用限制。"""
    has_usage_limit = any(p in error_msg for p in _USAGE_LIMIT_PATTERNS)
    has_transient_signal = any(p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS)

    if has_usage_limit and has_transient_signal:
        return result_fn(
            ErrorReason.rate_limit,
            retryable=True,
            should_rotate_credential=True,
            should_fallback=True,
        )

    return result_fn(
        ErrorReason.billing,
        retryable=False,
        should_rotate_credential=True,
        should_fallback=True,
    )


def _classify_400(
    error_msg: str,
    error_code: str,
    body: dict,
    *,
    provider: str,
    model: str,
    approx_tokens: int,
    context_length: int,
    num_messages: int = 0,
    result_fn,
) -> ClassifiedError:
    """分类 400 Bad Request。"""

    # 图片过大
    if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
        return result_fn(
            ErrorReason.image_too_large,
            retryable=True,
        )

    # 上下文溢出
    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return result_fn(
            ErrorReason.context_overflow,
            retryable=True,
            should_compress=True,
        )

    # Provider 策略阻止
    if any(p in error_msg for p in _PROVIDER_POLICY_BLOCKED_PATTERNS):
        return result_fn(
            ErrorReason.provider_policy_blocked,
            retryable=False,
            should_fallback=False,
        )

    # 模型未找到
    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return result_fn(
            ErrorReason.model_not_found,
            retryable=False,
            should_fallback=True,
        )

    # 速率限制（某些 Provider 用 400 而非 429）
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(
            ErrorReason.rate_limit,
            retryable=True,
            should_rotate_credential=True,
            should_fallback=True,
        )

    # 计费错误
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return result_fn(
            ErrorReason.billing,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    # 通用 400 + 大会话 → 可能是上下文溢出
    err_body_msg = ""
    if isinstance(body, dict):
        err_obj = body.get("error", {})
        if isinstance(err_obj, dict):
            err_body_msg = str(err_obj.get("message") or "").strip().lower()
        if not err_body_msg:
            err_body_msg = str(body.get("message") or "").strip().lower()

    is_generic = len(err_body_msg) < 30 or err_body_msg in {"error", ""}
    is_large = approx_tokens > context_length * 0.4 or (
        context_length <= 256000 and (approx_tokens > 80000 or num_messages > 80)
    )

    if is_generic and is_large:
        return result_fn(
            ErrorReason.context_overflow,
            retryable=True,
            should_compress=True,
        )

    return result_fn(
        ErrorReason.format_error,
        retryable=False,
        should_fallback=True,
    )


def _classify_by_error_code(
    error_code: str, error_msg: str, result_fn,
) -> Optional[ClassifiedError]:
    """基于结构化错误码分类。"""
    code_lower = error_code.lower()

    if code_lower in {"resource_exhausted", "throttled", "rate_limit_exceeded"}:
        return result_fn(
            ErrorReason.rate_limit,
            retryable=True,
            should_rotate_credential=True,
        )

    if code_lower in {"insufficient_quota", "billing_not_active", "payment_required"}:
        return result_fn(
            ErrorReason.billing,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if code_lower in {"model_not_found", "model_not_available", "invalid_model"}:
        return result_fn(
            ErrorReason.model_not_found,
            retryable=False,
            should_fallback=True,
        )

    if code_lower in {"context_length_exceeded", "max_tokens_exceeded"}:
        return result_fn(
            ErrorReason.context_overflow,
            retryable=True,
            should_compress=True,
        )

    return None


def _classify_by_message(
    error_msg: str,
    error_type: str,
    *,
    approx_tokens: int,
    context_length: int,
    result_fn,
) -> Optional[ClassifiedError]:
    """基于错误消息模式分类。"""

    if any(p in error_msg for p in _PAYLOAD_TOO_LARGE_PATTERNS):
        return result_fn(
            ErrorReason.payload_too_large,
            retryable=True,
            should_compress=True,
        )

    if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
        return result_fn(
            ErrorReason.image_too_large,
            retryable=True,
        )

    # 速率限制模式（优先于 usage_limit 检查）
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(
            ErrorReason.rate_limit,
            retryable=True,
            should_rotate_credential=True,
            should_fallback=True,
        )

    # 计费错误模式
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return result_fn(
            ErrorReason.billing,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    # 使用限制模式（需要区分计费还是速率限制）
    has_usage_limit = any(p in error_msg for p in _USAGE_LIMIT_PATTERNS)
    if has_usage_limit:
        has_transient_signal = any(p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS)
        if has_transient_signal:
            return result_fn(
                ErrorReason.rate_limit,
                retryable=True,
                should_rotate_credential=True,
                should_fallback=True,
            )
        return result_fn(
            ErrorReason.billing,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return result_fn(
            ErrorReason.context_overflow,
            retryable=True,
            should_compress=True,
        )

    if any(p in error_msg for p in _AUTH_PATTERNS):
        return result_fn(
            ErrorReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if any(p in error_msg for p in _PROVIDER_POLICY_BLOCKED_PATTERNS):
        return result_fn(
            ErrorReason.provider_policy_blocked,
            retryable=False,
            should_fallback=False,
        )

    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return result_fn(
            ErrorReason.model_not_found,
            retryable=False,
            should_fallback=True,
        )

    if any(p in error_msg for p in _TIMEOUT_MESSAGE_PATTERNS):
        return result_fn(ErrorReason.timeout, retryable=True)

    return None


def _extract_status_code(error: Exception) -> Optional[int]:
    """从错误链中提取 HTTP 状态码。"""
    current = error
    for _ in range(5):
        code = getattr(current, "status_code", None)
        if isinstance(code, int):
            return code
        code = getattr(current, "status", None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if cause is None or cause is current:
            break
        current = cause
    return None


def _extract_error_body(error: Exception) -> dict:
    """从 SDK 异常中提取结构化错误体。"""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        return body
    response = getattr(error, "response", None)
    if response is not None:
        try:
            json_body = response.json()
            if isinstance(json_body, dict):
                return json_body
        except (json.JSONDecodeError, ValueError, AttributeError, UnicodeDecodeError):
            logger.debug("无法解析响应体为 JSON")
    return {}


def _extract_error_code(body: dict) -> str:
    """从响应体中提取错误码。"""
    if not body:
        return ""
    error_obj = body.get("error", {})
    if isinstance(error_obj, dict):
        code = error_obj.get("code") or error_obj.get("type") or ""
        if isinstance(code, str) and code.strip():
            return code.strip()
    code = body.get("code") or body.get("error_code") or ""
    if isinstance(code, (str, int)):
        return str(code).strip()
    return ""


def _extract_message(error: Exception, body: dict) -> str:
    """提取最有信息量的错误消息。"""
    if body:
        error_obj = body.get("error", {})
        if isinstance(error_obj, dict):
            msg = error_obj.get("message", "")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()[:500]
        msg = body.get("message", "")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()[:500]
    return str(error)[:500]
