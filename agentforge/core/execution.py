"""Agent 执行引擎。

封装核心执行逻辑：重试循环、错误恢复、回退链激活。
参考 hermes-agent/agent/conversation_loop.py 的设计。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from agentforge.types import Message, NormalizedResponse, ToolResult
from agentforge.types.errors import (
    ClassifiedError,
    ErrorReason,
    InterruptException,
    ProviderError,
    ProviderRateLimitError,
    ProviderContextOverflowError,
    classify_api_error,
)
from agentforge.core.retry_utils import (
    RetryContext,
    RetryPolicy,
    jittered_backoff,
    sleep_with_interrupt,
)
from agentforge.core.fallback import FallbackChain
from agentforge.core.iteration_budget import IterationBudget
from agentforge.tools.guardrails import (
    ToolCallGuardrailController,
    ToolGuardrailDecision,
)

if TYPE_CHECKING:
    from agentforge.providers import Provider
    from agentforge.tools import Tool

logger = logging.getLogger(__name__)


# 默认重试配置
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 5.0
DEFAULT_MAX_DELAY = 120.0
DEFAULT_MAX_COMPRESSION_ATTEMPTS = 3


@dataclass
class ExecutionConfig:
    """执行配置。

    控制重试、回退、压缩等行为。
    """

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY
    max_compression_attempts: int = DEFAULT_MAX_COMPRESSION_ATTEMPTS
    enable_fallback: bool = True
    enable_compression: bool = True
    enable_guardrails: bool = True


@dataclass
class ExecutionState:
    """执行状态跟踪。

    记录重试计数、压缩尝试、错误历史等。
    """

    api_call_count: int = 0
    retry_count: int = 0
    compression_attempts: int = 0
    length_continue_retries: int = 0
    truncated_tool_call_retries: int = 0

    # 特定错误的一次性重试标记
    auth_retry_attempted: bool = False
    thinking_sig_retry_attempted: bool = False
    image_shrink_retry_attempted: bool = False
    oauth_beta_retry_attempted: bool = False
    llama_grammar_retry_attempted: bool = False
    has_retried_429: bool = False

    # 错误历史
    errors: List[Exception] = field(default_factory=list)
    classified_errors: List[ClassifiedError] = field(default_factory=list)

    def reset_for_turn(self) -> None:
        """重置本轮状态。"""
        self.retry_count = 0
        self.compression_attempts = 0
        self.length_continue_retries = 0
        self.truncated_tool_call_retries = 0
        self.auth_retry_attempted = False
        self.thinking_sig_retry_attempted = False
        self.image_shrink_retry_attempted = False
        self.oauth_beta_retry_attempted = False
        self.llama_grammar_retry_attempted = False
        self.has_retried_429 = False
        self.errors.clear()
        self.classified_errors.clear()

    def record_error(self, error: Exception, classified: ClassifiedError) -> None:
        """记录错误。"""
        self.errors.append(error)
        self.classified_errors.append(classified)


@dataclass
class ExecutionResult:
    """执行结果。"""

    response: Optional[NormalizedResponse] = None
    messages: List[Message] = field(default_factory=list)
    completed: bool = False
    interrupted: bool = False
    failed: bool = False
    partial: bool = False
    error: Optional[str] = None
    api_calls: int = 0
    compression_exhausted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "completed": self.completed,
            "interrupted": self.interrupted,
            "failed": self.failed,
            "partial": self.partial,
            "error": self.error,
            "api_calls": self.api_calls,
            "compression_exhausted": self.compression_exhausted,
        }


class ExecutionEngine:
    """Agent 执行引擎。

    封装核心执行逻辑：
    - 重试循环（抖动指数退避）
    - 错误分类与恢复
    - 回退链激活
    - 上下文压缩触发
    - 工具护栏检查

    使用示例：
        engine = ExecutionEngine(provider, config)

        result = engine.execute(
            messages=context,
            tools=tools,
            interrupt_check=lambda: token.check(),
        )
    """

    def __init__(
        self,
        provider: "Provider",
        config: Optional[ExecutionConfig] = None,
        fallback_chain: Optional[FallbackChain] = None,
        guardrails: Optional[ToolCallGuardrailController] = None,
        context_compressor: Optional[Any] = None,
        event_dispatcher: Optional[Any] = None,
    ):
        """初始化执行引擎。

        Args:
            provider: Provider 实例
            config: 执行配置
            fallback_chain: 回退链（可选）
            guardrails: 工具护栏控制器（可选）
            context_compressor: 上下文压缩器（可选）
            event_dispatcher: 事件分发器（可选）
        """
        self._provider = provider
        self._config = config or ExecutionConfig()
        self._fallback_chain = fallback_chain
        self._guardrails = guardrails
        self._context_compressor = context_compressor
        self._event_dispatcher = event_dispatcher

        # 执行状态
        self._state = ExecutionState()

        # 重试策略
        self._retry_policy = RetryPolicy(
            max_retries=self._config.max_retries,
            base_delay=self._config.base_delay,
            max_delay=self._config.max_delay,
        )

    @property
    def state(self) -> ExecutionState:
        """获取当前执行状态。"""
        return self._state

    def reset_for_turn(self) -> None:
        """重置本轮状态。"""
        self._state.reset_for_turn()
        if self._guardrails:
            self._guardrails.reset_for_turn()

    def execute(
        self,
        messages: List[Message],
        tools: Optional[Dict[str, "Tool"]] = None,
        interrupt_check: Optional[Callable[[], bool]] = None,
        on_response: Optional[Callable[[NormalizedResponse], None]] = None,
        on_error: Optional[Callable[[Exception, ClassifiedError], None]] = None,
        on_retry: Optional[Callable[[int, float, ClassifiedError], None]] = None,
        on_fallback: Optional[Callable[[str, str], None]] = None,
        on_compression: Optional[Callable[[int, int], None]] = None,
    ) -> ExecutionResult:
        """执行 API 调用循环。

        Args:
            messages: 消息列表
            tools: 工具字典（可选）
            interrupt_check: 中断检查函数（可选）
            on_response: 响应回调（可选）
            on_error: 错误回调（可选）
            on_retry: 重试回调（可选）
            on_fallback: 回退回调（可选）
            on_compression: 压缩回调（可选）

        Returns:
            ExecutionResult 执行结果
        """
        self.reset_for_turn()

        result = ExecutionResult(messages=messages)
        tool_specs = list(tools.values()) if tools else None

        while self._state.retry_count < self._config.max_retries:
            # 检查中断
            if interrupt_check and interrupt_check():
                result.interrupted = True
                result.error = "执行被中断"
                result.api_calls = self._state.api_call_count
                return result

            # 尝试 API 调用
            try:
                self._state.api_call_count += 1

                # 发射请求事件
                if self._event_dispatcher:
                    self._event_dispatcher.dispatch("provider_request", {})

                response = self._provider.complete(
                    messages=messages,
                    tools=tool_specs,
                )

                # 发射响应事件
                if self._event_dispatcher:
                    self._event_dispatcher.dispatch("provider_response", {"response": response})

                # 验证响应
                if response is None or not self._validate_response(response):
                    self._handle_invalid_response(
                        response, messages, interrupt_check,
                        on_retry=on_retry,
                    )
                    continue

                # 成功响应
                if on_response:
                    on_response(response)

                result.response = response
                result.completed = True
                result.api_calls = self._state.api_call_count
                return result

            except InterruptException:
                result.interrupted = True
                result.error = "执行被中断"
                result.api_calls = self._state.api_call_count
                return result

            except Exception as e:
                # 分类错误
                approx_tokens = self._estimate_tokens(messages)
                context_length = self._get_context_length()

                classified = classify_api_error(
                    e,
                    provider=self._get_provider_name(),
                    model=self._get_model_name(),
                    approx_tokens=approx_tokens,
                    context_length=context_length,
                    num_messages=len(messages),
                )

                self._state.record_error(e, classified)

                if on_error:
                    on_error(e, classified)

                # 尝试恢复
                recovery_result = self._attempt_recovery(
                    e, classified, messages,
                    interrupt_check=interrupt_check,
                    on_fallback=on_fallback,
                    on_compression=on_compression,
                )

                if recovery_result is not None:
                    # 恢复成功，继续循环
                    if recovery_result.get("messages"):
                        messages = recovery_result["messages"]
                    self._state.retry_count = 0
                    self._state.compression_attempts = 0
                    continue

                # 检查是否应该停止重试
                if not classified.retryable:
                    result.failed = True
                    result.error = classified.message
                    result.api_calls = self._state.api_call_count
                    return result

                # 检查是否达到最大重试次数
                self._state.retry_count += 1
                if self._state.retry_count >= self._config.max_retries:
                    # 尝试回退
                    if self._try_activate_fallback(on_fallback):
                        self._state.retry_count = 0
                        self._state.compression_attempts = 0
                        continue

                    result.failed = True
                    result.error = f"达到最大重试次数 ({self._config.max_retries}): {classified.message}"
                    result.api_calls = self._state.api_call_count
                    return result

                # 计算退避延迟
                delay = jittered_backoff(
                    self._state.retry_count,
                    base_delay=self._config.base_delay,
                    max_delay=self._config.max_delay,
                )

                if on_retry:
                    on_retry(self._state.retry_count, delay, classified)

                logger.warning(
                    f"API 调用失败 (尝试 {self._state.retry_count}/{self._config.max_retries}): "
                    f"{classified.reason.value} - {classified.message}"
                )

                # 可中断睡眠
                interrupted = sleep_with_interrupt(delay, interrupt_check)
                if interrupted:
                    result.interrupted = True
                    result.error = "执行被中断（重试等待期间）"
                    result.api_calls = self._state.api_call_count
                    return result

        # 不应该到达这里
        result.failed = True
        result.error = "执行循环异常终止"
        result.api_calls = self._state.api_call_count
        return result

    def _validate_response(self, response: NormalizedResponse) -> bool:
        """验证响应是否有效。"""
        if response is None:
            return False

        # 检查是否有内容或工具调用
        has_content = response.content and len(response.content) > 0
        has_tool_calls = response.tool_calls and len(response.tool_calls) > 0

        return has_content or has_tool_calls

    def _handle_invalid_response(
        self,
        response: Optional[NormalizedResponse],
        messages: List[Message],
        interrupt_check: Optional[Callable[[], bool]],
        on_retry: Optional[Callable[[int, float, ClassifiedError], None]] = None,
    ) -> None:
        """处理无效响应。"""
        self._state.retry_count += 1

        # 尝试回退
        if self._try_activate_fallback(None):
            self._state.retry_count = 0
            self._state.compression_attempts = 0
            return

        # 达到最大重试次数
        if self._state.retry_count >= self._config.max_retries:
            return

        # 退避重试
        delay = jittered_backoff(
            self._state.retry_count,
            base_delay=self._config.base_delay,
            max_delay=self._config.max_delay,
        )

        classified = ClassifiedError(
            reason=ErrorReason.format_error,
            message="无效响应",
            provider=self._get_provider_name(),
            model=self._get_model_name(),
        )

        if on_retry:
            on_retry(self._state.retry_count, delay, classified)

        sleep_with_interrupt(delay, interrupt_check)

    def _attempt_recovery(
        self,
        error: Exception,
        classified: ClassifiedError,
        messages: List[Message],
        interrupt_check: Optional[Callable[[], bool]],
        on_fallback: Optional[Callable[[str, str], None]] = None,
        on_compression: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[Dict[str, Any]]:
        """尝试从错误中恢复。

        Returns:
            恢复成功返回包含新消息等信息的字典，失败返回 None
        """
        # 1. 速率限制：立即尝试回退
        if classified.reason in {ErrorReason.rate_limit, ErrorReason.billing}:
            if self._try_activate_fallback(on_fallback):
                return {}

        # 2. 认证错误：尝试回退
        if classified.reason == ErrorReason.auth:
            if self._try_activate_fallback(on_fallback):
                return {}

        # 3. 上下文溢出：尝试压缩
        if classified.should_compress and self._config.enable_compression:
            return self._attempt_compression(
                messages, interrupt_check, on_compression
            )

        # 4. 负载过大：尝试压缩
        if classified.reason == ErrorReason.payload_too_large:
            return self._attempt_compression(
                messages, interrupt_check, on_compression
            )

        # 5. Thinking signature：清除 reasoning blocks
        if classified.reason == ErrorReason.thinking_signature:
            if not self._state.thinking_sig_retry_attempted:
                self._state.thinking_sig_retry_attempted = True
                cleared_messages = self._clear_reasoning_blocks(messages)
                return {"messages": cleared_messages}

        # 6. 图片过大：尝试缩小
        if classified.reason == ErrorReason.image_too_large:
            if not self._state.image_shrink_retry_attempted:
                self._state.image_shrink_retry_attempted = True
                shrunk_messages = self._shrink_images(messages)
                return {"messages": shrunk_messages}

        return None

    def _attempt_compression(
        self,
        messages: List[Message],
        interrupt_check: Optional[Callable[[], bool]],
        on_compression: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[Dict[str, Any]]:
        """尝试上下文压缩。"""
        if not self._context_compressor:
            return None

        self._state.compression_attempts += 1

        if self._state.compression_attempts > self._config.max_compression_attempts:
            return None

        original_len = len(messages)

        # 执行压缩
        try:
            compressed_messages = self._context_compressor.compress(messages)
        except Exception as e:
            logger.warning(f"上下文压缩失败: {e}")
            return None

        if len(compressed_messages) < original_len:
            if on_compression:
                on_compression(original_len, len(compressed_messages))

            logger.info(
                f"上下文压缩: {original_len} → {len(compressed_messages)} 条消息"
            )

            # 短暂等待
            sleep_with_interrupt(2.0, interrupt_check)

            return {"messages": compressed_messages}

        return None

    def _try_activate_fallback(
        self,
        on_fallback: Optional[Callable[[str, str], None]] = None,
    ) -> bool:
        """尝试激活回退 Provider。"""
        if not self._fallback_chain or not self._config.enable_fallback:
            return False

        if self._fallback_chain.activate_next():
            current = self._fallback_chain.current
            if current and on_fallback:
                on_fallback(current.provider, current.model)

            logger.info(
                f"激活回退 Provider: {current.provider}/{current.model}"
            )
            return True

        return False

    def _clear_reasoning_blocks(self, messages: List[Message]) -> List[Message]:
        """清除消息中的 reasoning blocks。"""
        cleared = []
        for msg in messages:
            # 创建新消息，移除 reasoning_details
            new_msg = Message(
                role=msg.role,
                content=msg.content,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
            )
            # 不复制 reasoning_details
            cleared.append(new_msg)
        return cleared

    def _shrink_images(
        self,
        messages: List[Message],
        max_dimension: int = 1024,
    ) -> List[Message]:
        """缩小消息中的图片尺寸。

        当图片过大导致 API 错误时，尝试缩小图片尺寸以继续处理。
        支持缩小 base64 编码的图片，URL 图片会被移除（无法本地处理）。

        Args:
            messages: 消息列表
            max_dimension: 最大尺寸（宽/高），默认 1024

        Returns:
            处理后的消息列表
        """
        from agentforge.types import ImageContent, TextContent

        shrunk_messages = []
        for msg in messages:
            if isinstance(msg.content, str):
                # 纯文本消息，无需处理
                shrunk_messages.append(msg)
                continue

            # 多模态消息，处理图片
            new_content = []
            for block in msg.content:
                if isinstance(block, ImageContent):
                    # 尝试缩小图片
                    shrunk_image = self._shrink_single_image(block, max_dimension)
                    if shrunk_image:
                        new_content.append(shrunk_image)
                    else:
                        # 无法处理 URL 图片或缩小失败，添加文本说明
                        new_content.append(TextContent(
                            text="[图片已被移除（尺寸过大）]"
                        ))
                else:
                    new_content.append(block)

            shrunk_messages.append(Message(
                role=msg.role,
                content=new_content,
            ))

        return shrunk_messages

    def _shrink_single_image(
        self,
        image: "ImageContent",
        max_dimension: int,
    ) -> Optional["ImageContent"]:
        """缩小单个图片。

        Args:
            image: 图片内容块
            max_dimension: 最大尺寸

        Returns:
            缩小后的图片，或 None（无法处理）
        """
        import base64
        import io
        from agentforge.types import ImageContent

        # URL 图片无法本地处理
        if image.url and not image.base64:
            logger.warning("URL 图片无法本地缩小，将被移除")
            return None

        # 尝试解码和缩小 base64 图片
        try:
            # 解码 base64
            image_data = base64.b64decode(image.base64)

            # 尝试使用 PIL 处理
            try:
                from PIL import Image as PILImage

                pil_img = PILImage.open(io.BytesIO(image_data))

                # 计算缩小比例
                width, height = pil_img.size
                if width > max_dimension or height > max_dimension:
                    # 保持比例缩小
                    ratio = min(max_dimension / width, max_dimension / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)

                    # 缩小图片
                    pil_img = pil_img.resize((new_width, new_height), PILImage.LANCZOS)

                    # 转换为 base64
                    buffer = io.BytesIO()
                    # 保持原格式或转换为 JPEG（默认）
                    format_name = "JPEG" if image.media_type == "image/jpeg" else "PNG"
                    pil_img.save(buffer, format=format_name)
                    shrunk_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                    logger.info(
                        f"图片缩小: {width}x{height} -> {new_width}x{new_height}"
                    )

                    return ImageContent(
                        base64=shrunk_base64,
                        media_type=f"image/{format_name.lower()}",
                    )
                else:
                    # 图片尺寸已符合要求
                    return image

            except ImportError:
                # PIL 未安装，记录警告并跳过
                logger.warning(
                    "PIL 未安装，无法缩小图片。"
                    "请安装 Pillow: pip install Pillow"
                )
                return None

        except Exception as e:
            logger.warning(f"图片缩小失败: {e}")
            return None

    def _estimate_tokens(self, messages: List[Message]) -> int:
        """估算消息 Token 数。"""
        total = 0
        for msg in messages:
            if msg.content:
                # 粗略估算：每 4 字符约 1 token
                total += len(msg.content) // 4
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    if tc.arguments:
                        total += len(str(tc.arguments)) // 4
        return total

    def _get_context_length(self) -> int:
        """获取当前上下文长度限制。"""
        if self._context_compressor:
            return getattr(self._context_compressor, "context_length", 200000)
        return 200000

    def _get_provider_name(self) -> str:
        """获取当前 Provider 名称。"""
        return getattr(self._provider, "name", "") or ""

    def _get_model_name(self) -> str:
        """获取当前模型名称。"""
        return getattr(self._provider, "model", "") or ""

    def execute_tool_calls(
        self,
        response: NormalizedResponse,
        tools: Dict[str, "Tool"],
        interrupt_check: Optional[Callable[[], bool]] = None,
        on_tool_start: Optional[Callable[[List], None]] = None,
        on_tool_result: Optional[Callable[[ToolResult], None]] = None,
    ) -> List[ToolResult]:
        """执行工具调用。

        Args:
            response: 包含工具调用的响应
            tools: 工具字典
            interrupt_check: 中断检查函数（可选）
            on_tool_start: 工具开始回调（可选）
            on_tool_result: 工具结果回调（可选）

        Returns:
            工具结果列表
        """
        if not response.tool_calls:
            return []

        results = []

        # 护栏检查
        if self._guardrails and self._config.enable_guardrails:
            for tc in response.tool_calls:
                decision = self._guardrails.before_call(tc.name, tc.arguments)
                if not decision.allows_execution:
                    # 返回错误结果
                    result = ToolResult(
                        tool_call_id=tc.id,
                        content=f"护栏阻止: {decision.message}",
                        is_error=True,
                    )
                    results.append(result)
                    continue

        # 发射工具开始事件
        if on_tool_start:
            on_tool_start(response.tool_calls)

        if self._event_dispatcher:
            self._event_dispatcher.dispatch(
                "tool_start",
                {"tool_calls": response.tool_calls},
            )

        # 执行工具
        for tc in response.tool_calls:
            # 检查中断
            if interrupt_check and interrupt_check():
                result = ToolResult(
                    tool_call_id=tc.id,
                    content="执行被中断",
                    is_error=True,
                )
                results.append(result)
                break

            tool = tools.get(tc.name)
            if not tool:
                result = ToolResult(
                    tool_call_id=tc.id,
                    content=f"工具未找到: {tc.name}",
                    is_error=True,
                )
                results.append(result)
                continue

            try:
                # 解析工具参数（JSON 字符串）
                import json
                try:
                    args = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                # 执行工具（传递 tool_call_id 和 kwargs）
                output = tool.execute(tc.id, **args)

                # 处理返回值（可能是 ToolResult 或字符串）
                if isinstance(output, ToolResult):
                    result = output
                else:
                    result = ToolResult(
                        tool_call_id=tc.id,
                        content=output if isinstance(output, str) else str(output),
                        is_error=False,
                    )

                # 护栏后检查
                if self._guardrails:
                    decision = self._guardrails.after_call(
                        tc.name, tc.arguments, result.content
                    )
                    if decision.action == "warn":
                        logger.warning(f"工具护栏警告: {decision.message}")

            except Exception as e:
                result = ToolResult(
                    tool_call_id=tc.id,
                    content=f"工具执行错误: {e}",
                    is_error=True,
                )

                # 护栏记录失败
                if self._guardrails:
                    self._guardrails.after_call(
                        tc.name, tc.arguments, result.content, failed=True
                    )

            results.append(result)

            if on_tool_result:
                on_tool_result(result)

        # 发射工具结束事件
        if self._event_dispatcher:
            self._event_dispatcher.dispatch("tool_end", {"results": results})

        return results


__all__ = [
    "ExecutionConfig",
    "ExecutionState",
    "ExecutionResult",
    "ExecutionEngine",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_BASE_DELAY",
    "DEFAULT_MAX_DELAY",
    "DEFAULT_MAX_COMPRESSION_ATTEMPTS",
]