"""Anthropic Prompt Caching 策略。

在 system prompt + 最后 3 条消息处放置 cache_control 断点，
减少多轮对话的输入 token 成本约 75%。

参考 hermes-agent/agent/prompt_caching.py。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List


def _apply_cache_marker(
    msg: Dict[str, Any],
    cache_marker: Dict[str, str],
    native_anthropic: bool = False,
) -> None:
    """向单条消息添加 cache_control，处理所有格式变体。

    Args:
        msg: 消息字典
        cache_marker: cache_control 标记
        native_anthropic: 是否使用原生 Anthropic 格式
    """
    role = msg.get("role", "")
    content = msg.get("content")

    # tool 消息特殊处理
    if role == "tool":
        if native_anthropic:
            msg["cache_control"] = cache_marker
        return

    # 空内容
    if content is None or content == "":
        msg["cache_control"] = cache_marker
        return

    # 字符串内容转 content blocks
    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": cache_marker}
        ]
        return

    # content blocks 列表 - 在最后一个 block 添加 cache_control
    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = cache_marker


def _build_marker(ttl: str) -> Dict[str, str]:
    """构建 cache_control 标记字典。

    Args:
        ttl: TTL 值 ('5m' 或 '1h')

    Returns:
        cache_control 字典
    """
    marker: Dict[str, str] = {"type": "ephemeral"}
    if ttl == "1h":
        marker["ttl"] = "1h"
    return marker


def apply_anthropic_cache_control(
    api_messages: List[Dict[str, Any]],
    cache_ttl: str = "5m",
    native_anthropic: bool = False,
) -> List[Dict[str, Any]]:
    """应用 system_and_3 缓存策略到消息。

    在最多 4 个位置放置 cache_control 断点：
    system prompt + 最后 3 条非 system 消息。

    Args:
        api_messages: API 消息列表
        cache_ttl: 缓存 TTL ('5m' 或 '1h')
        native_anthropic: 是否使用原生 Anthropic 格式

    Returns:
        深拷贝的消息列表，带有 cache_control 断点
    """
    messages = copy.deepcopy(api_messages)
    if not messages:
        return messages

    marker = _build_marker(cache_ttl)

    breakpoints_used = 0

    # system 消息
    if messages[0].get("role") == "system":
        _apply_cache_marker(messages[0], marker, native_anthropic=native_anthropic)
        breakpoints_used += 1

    # 最后 3 条非 system 消息
    remaining = 4 - breakpoints_used
    non_sys = [i for i in range(len(messages)) if messages[i].get("role") != "system"]

    for idx in non_sys[-remaining:]:
        _apply_cache_marker(messages[idx], marker, native_anthropic=native_anthropic)

    return messages


def apply_cache_control_to_system(
    system_prompt: str,
    cache_ttl: str = "5m",
) -> List[Dict[str, Any]]:
    """向 system prompt 应用 cache_control。

    Args:
        system_prompt: System prompt 文本
        cache_ttl: 缓存 TTL

    Returns:
        带 cache_control 的 content blocks
    """
    marker = _build_marker(cache_ttl)

    return [
        {"type": "text", "text": system_prompt, "cache_control": marker}
    ]


def extract_cache_stats(response: Any) -> Dict[str, int]:
    """从响应中提取缓存统计。

    Args:
        response: API 响应

    Returns:
        缓存统计字典
    """
    stats = {
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }

    if response is None:
        return stats

    # Anthropic 响应格式
    usage = getattr(response, "usage", None)
    if usage:
        stats["cache_read_tokens"] = getattr(usage, "cache_read_input_tokens", 0) or 0
        stats["cache_write_tokens"] = getattr(usage, "cache_creation_input_tokens", 0) or 0

    # dict 格式
    if isinstance(response, dict):
        usage_data = response.get("usage", {})
        if isinstance(usage_data, dict):
            stats["cache_read_tokens"] = usage_data.get("cache_read_input_tokens", 0)
            stats["cache_write_tokens"] = usage_data.get("cache_creation_input_tokens", 0)

    return stats


__all__ = [
    "apply_anthropic_cache_control",
    "apply_cache_control_to_system",
    "extract_cache_stats",
]