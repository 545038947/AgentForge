"""工具护栏控制器。

防止工具调用循环、重复失败、无进展等问题。
参考 hermes-agent/agent/tool_guardrails.py。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


# 幂等工具（只读，不修改状态）
IDEMPOTENT_TOOL_NAMES = frozenset({
    "read_file",
    "search_files",
    "web_search",
    "web_fetch",
    "file_read",
    "list_directory",
    "get_file_info",
})

# 变更工具（修改状态）
MUTATING_TOOL_NAMES = frozenset({
    "shell",
    "execute_code",
    "write_file",
    "file_write",
    "patch",
    "todo",
    "memory",
    "browser_click",
    "browser_type",
    "delegate_task",
})


@dataclass(frozen=True)
class ToolCallGuardrailConfig:
    """工具护栏配置。

    控制循环检测、失败重试限制等阈值。
    """

    warnings_enabled: bool = True
    hard_stop_enabled: bool = False
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5
    idempotent_tools: frozenset = field(default_factory=lambda: IDEMPOTENT_TOOL_NAMES)
    mutating_tools: frozenset = field(default_factory=lambda: MUTATING_TOOL_NAMES)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ToolCallGuardrailConfig":
        """从配置字典构建护栏配置。

        支持 config.yaml 中的 `tool_loop_guardrails` 配置节。

        Args:
            data: 配置字典

        Returns:
            ToolCallGuardrailConfig 实例
        """
        if not isinstance(data, Mapping):
            return cls()

        warn_after = data.get("warn_after")
        if not isinstance(warn_after, Mapping):
            warn_after = {}

        hard_stop_after = data.get("hard_stop_after")
        if not isinstance(hard_stop_after, Mapping):
            hard_stop_after = {}

        defaults = cls()
        return cls(
            warnings_enabled=_as_bool(data.get("warnings_enabled"), defaults.warnings_enabled),
            hard_stop_enabled=_as_bool(data.get("hard_stop_enabled"), defaults.hard_stop_enabled),
            exact_failure_warn_after=_positive_int(
                warn_after.get("exact_failure", data.get("exact_failure_warn_after")),
                defaults.exact_failure_warn_after,
            ),
            same_tool_failure_warn_after=_positive_int(
                warn_after.get("same_tool_failure", data.get("same_tool_failure_warn_after")),
                defaults.same_tool_failure_warn_after,
            ),
            no_progress_warn_after=_positive_int(
                warn_after.get("idempotent_no_progress", data.get("no_progress_warn_after")),
                defaults.no_progress_warn_after,
            ),
            exact_failure_block_after=_positive_int(
                hard_stop_after.get("exact_failure", data.get("exact_failure_block_after")),
                defaults.exact_failure_block_after,
            ),
            same_tool_failure_halt_after=_positive_int(
                hard_stop_after.get("same_tool_failure", data.get("same_tool_failure_halt_after")),
                defaults.same_tool_failure_halt_after,
            ),
            no_progress_block_after=_positive_int(
                hard_stop_after.get("idempotent_no_progress", data.get("no_progress_block_after")),
                defaults.no_progress_block_after,
            ),
        )


def _as_bool(value: Any, default: bool) -> bool:
    """转换为布尔值。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _positive_int(value: Any, default: int) -> int:
    """转换为正整数。"""
    if value is None:
        return default
    try:
        result = int(value)
        return result if result > 0 else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ToolCallSignature:
    """工具调用的稳定签名（用于检测重复调用）。

    包含工具名和参数哈希，不暴露原始参数值。
    """

    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, Any] | None) -> "ToolCallSignature":
        """从工具调用创建签名。"""
        canonical = _canonical_tool_args(args or {})
        return cls(tool_name=tool_name, args_hash=_sha256(canonical))

    def to_metadata(self) -> Dict[str, str]:
        """返回公开元数据。"""
        return {"tool_name": self.tool_name, "args_hash": self.args_hash}


@dataclass(frozen=True)
class ToolGuardrailDecision:
    """护栏决策结果。"""

    action: str = "allow"  # allow | warn | block | halt
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0
    signature: Optional[ToolCallSignature] = None

    @property
    def allows_execution(self) -> bool:
        """是否允许执行。"""
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        """是否需要停止。"""
        return self.action in {"block", "halt"}

    def to_metadata(self) -> Dict[str, Any]:
        """转换为元数据。"""
        data: Dict[str, Any] = {
            "action": self.action,
            "code": self.code,
            "message": self.message,
            "tool_name": self.tool_name,
            "count": self.count,
        }
        if self.signature is not None:
            data["signature"] = self.signature.to_metadata()
        return data


def _canonical_tool_args(args: Mapping[str, Any]) -> str:
    """返回排序后的紧凑 JSON。"""
    if not isinstance(args, Mapping):
        return "{}"
    return json.dumps(
        args,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(text: str) -> str:
    """计算 SHA256 哈希。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _coerce_args(args: Any) -> Mapping[str, Any]:
    """强制转换参数为 Mapping。"""
    if isinstance(args, Mapping):
        return args
    if isinstance(args, dict):
        return args
    return {}


def classify_tool_failure(tool_name: str, result: str | None) -> tuple[bool, str]:
    """分类工具执行是否失败。

    Args:
        tool_name: 工具名称
        result: 工具结果内容

    Returns:
        (是否失败, 失败标签)
    """
    if result is None:
        return False, ""

    # 检查错误标记
    lower = result[:500].lower()
    if "error" in lower or "failed" in lower or result.startswith("Error"):
        return True, " [error]"

    # Shell 工具特殊处理
    if tool_name in {"shell", "terminal"}:
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                exit_code = data.get("exit_code")
                if exit_code is not None and exit_code != 0:
                    return True, f" [exit {exit_code}]"
        except (json.JSONDecodeError, TypeError):
            pass

    return False, ""


class ToolCallGuardrailController:
    """工具护栏控制器。

    检测并防止：
    - 重复相同参数的失败调用
    - 同一工具的多次失败
    - 幂等工具的无进展重复调用

    使用示例：
        controller = ToolCallGuardrailController()
        controller.reset_for_turn()

        # 执行前检查
        decision = controller.before_call("read_file", {"path": "/tmp"})
        if not decision.allows_execution:
            # 处理阻止
            pass

        # 执行后记录
        result = tool.execute(...)
        decision = controller.after_call("read_file", {"path": "/tmp"}, result.content)
    """

    def __init__(self, config: Optional[ToolCallGuardrailConfig] = None):
        """初始化控制器。

        Args:
            config: 护栏配置
        """
        self.config = config or ToolCallGuardrailConfig()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        """重置本轮统计。"""
        self._exact_failure_counts: Dict[ToolCallSignature, int] = {}
        self._same_tool_failure_counts: Dict[str, int] = {}
        self._no_progress: Dict[ToolCallSignature, tuple[str, int]] = {}
        self._halt_decision: Optional[ToolGuardrailDecision] = None

    @property
    def halt_decision(self) -> Optional[ToolGuardrailDecision]:
        """获取停止决策。"""
        return self._halt_decision

    def before_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
    ) -> ToolGuardrailDecision:
        """执行前检查。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            护栏决策
        """
        signature = ToolCallSignature.from_call(tool_name, _coerce_args(args))

        if not self.config.hard_stop_enabled:
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        # 检查重复失败
        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.config.exact_failure_block_after:
            decision = ToolGuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"阻止 {tool_name}: 相同参数的调用已失败 {exact_count} 次。"
                    "请改变策略或说明阻塞原因。"
                ),
                tool_name=tool_name,
                count=exact_count,
                signature=signature,
            )
            self._halt_decision = decision
            return decision

        # 检查幂等工具无进展
        if self._is_idempotent(tool_name):
            record = self._no_progress.get(signature)
            if record is not None:
                _, repeat_count = record
                if repeat_count >= self.config.no_progress_block_after:
                    decision = ToolGuardrailDecision(
                        action="block",
                        code="idempotent_no_progress_block",
                        message=(
                            f"阻止 {tool_name}: 此只读调用已返回相同结果 {repeat_count} 次。"
                            "请使用已提供的结果或尝试不同的查询。"
                        ),
                        tool_name=tool_name,
                        count=repeat_count,
                        signature=signature,
                    )
                    self._halt_decision = decision
                    return decision

        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: Optional[bool] = None,
    ) -> ToolGuardrailDecision:
        """执行后记录。

        Args:
            tool_name: 工具名称
            args: 工具参数
            result: 工具结果
            failed: 是否失败（可选，自动检测）

        Returns:
            护栏决策
        """
        args = _coerce_args(args)
        signature = ToolCallSignature.from_call(tool_name, args)

        # 自动检测失败
        if failed is None:
            failed, _ = classify_tool_failure(tool_name, result)

        # 记录失败
        if failed:
            # 相同签名失败计数
            exact_count = self._exact_failure_counts.get(signature, 0) + 1
            self._exact_failure_counts[signature] = exact_count

            # 同工具失败计数
            same_tool_count = self._same_tool_failure_counts.get(tool_name, 0) + 1
            self._same_tool_failure_counts[tool_name] = same_tool_count

            # 检查是否需要警告或阻止
            if exact_count >= self.config.exact_failure_warn_after:
                if self.config.warnings_enabled:
                    return ToolGuardrailDecision(
                        action="warn",
                        code="repeated_exact_failure",
                        message=(
                            f"警告: {tool_name} 已失败 {exact_count} 次（相同参数）。"
                            "考虑改变策略。"
                        ),
                        tool_name=tool_name,
                        count=exact_count,
                        signature=signature,
                    )

            if same_tool_count >= self.config.same_tool_failure_warn_after:
                if self.config.warnings_enabled:
                    return ToolGuardrailDecision(
                        action="warn",
                        code="repeated_same_tool_failure",
                        message=(
                            f"警告: {tool_name} 已失败 {same_tool_count} 次。"
                            "考虑使用其他工具。"
                        ),
                        tool_name=tool_name,
                        count=same_tool_count,
                    )

        # 记录幂等工具结果（用于检测无进展）
        elif self._is_idempotent(tool_name) and result:
            result_hash = _sha256(result[:1000])
            record = self._no_progress.get(signature)

            if record is not None:
                prev_hash, prev_count = record
                if prev_hash == result_hash:
                    # 相同结果，增加计数
                    self._no_progress[signature] = (result_hash, prev_count + 1)
                    if prev_count + 1 >= self.config.no_progress_warn_after:
                        if self.config.warnings_enabled:
                            return ToolGuardrailDecision(
                                action="warn",
                                code="idempotent_no_progress",
                                message=(
                                    f"警告: {tool_name} 返回相同结果 {prev_count + 1} 次。"
                                    "请使用已有结果。"
                                ),
                                tool_name=tool_name,
                                count=prev_count + 1,
                                signature=signature,
                            )
                else:
                    # 不同结果，重置
                    self._no_progress[signature] = (result_hash, 1)
            else:
                self._no_progress[signature] = (result_hash, 1)

        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def _is_idempotent(self, tool_name: str) -> bool:
        """检查是否为幂等工具。"""
        return tool_name in self.config.idempotent_tools

    def _is_mutating(self, tool_name: str) -> bool:
        """检查是否为变更工具。"""
        return tool_name in self.config.mutating_tools

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        return {
            "exact_failures": {
                sig.args_hash: count
                for sig, count in self._exact_failure_counts.items()
            },
            "same_tool_failures": dict(self._same_tool_failure_counts),
            "no_progress_count": len(self._no_progress),
        }