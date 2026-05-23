"""Streaming Context Scrubber。

用于流式文本的状态清理器，处理跨块的 memory-context 标签。
防止 memory-context 内容泄露到 UI。

参考 hermes-agent/agent/memory_manager.py。
"""

from __future__ import annotations

import re
from typing import List


# 内部上下文正则
_INTERNAL_CONTEXT_RE = re.compile(
    r"<memory-context>.*?</memory-context>",
    re.IGNORECASE | re.DOTALL,
)

# 系统注记正则
_INTERNAL_NOTE_RE = re.compile(
    r"^\s*<!-- system-note:.*?-->\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# 围栏标签正则
_FENCE_TAG_RE = re.compile(
    r"</?memory-context>",
    re.IGNORECASE,
)


def sanitize_context(text: str) -> str:
    """从文本中移除围栏标签、注入的上下文块和系统注记。

    Args:
        text: 输入文本

    Returns:
        清理后的文本
    """
    text = _INTERNAL_CONTEXT_RE.sub("", text)
    text = _INTERNAL_NOTE_RE.sub("", text)
    text = _FENCE_TAG_RE.sub("", text)
    return text


class StreamingContextScrubber:
    """流式上下文清理器。

    处理跨块的 memory-context 标签，防止内容泄露。
    单次正则无法处理跨块的标签，此清理器运行状态机跨 delta 处理。

    使用示例：
        scrubber = StreamingContextScrubber()
        for delta in stream:
            visible = scrubber.feed(delta)
            if visible:
                emit(visible)
        trailing = scrubber.flush()  # 流结束时
        if trailing:
            emit(trailing)
    """

    _OPEN_TAG = "<memory-context>"
    _CLOSE_TAG = "</memory-context>"

    def __init__(self) -> None:
        """初始化清理器。"""
        self._in_span: bool = False
        self._buf: str = ""
        self._at_block_boundary: bool = True

    def reset(self) -> None:
        """重置清理器状态。"""
        self._in_span = False
        self._buf = ""
        self._at_block_boundary = True

    def feed(self, text: str) -> str:
        """返回清理后的可见文本。

        任何可能是标签开头的尾部片段会被保留在内部缓冲区，
        在下一次 feed() 调用时处理，或由 flush() 处理。

        Args:
            text: 输入文本

        Returns:
            清理后的可见文本
        """
        if not text:
            return ""

        buf = self._buf + text
        self._buf = ""
        out: List[str] = []

        while buf:
            if self._in_span:
                idx = buf.lower().find(self._CLOSE_TAG)
                if idx == -1:
                    # 保留可能的部分关闭标签；丢弃其余部分
                    held = self._max_partial_suffix(buf, self._CLOSE_TAG)
                    self._buf = buf[-held:] if held else ""
                    return "".join(out)
                # 找到关闭标签 — 跳过 span 内容 + 标签，继续
                buf = buf[idx + len(self._CLOSE_TAG):]
                self._in_span = False
            else:
                idx = self._find_boundary_open_tag(buf)
                if idx == -1:
                    # 没有打开标签 — 保留可能的部分打开标签
                    held = (
                        self._max_pending_open_suffix(buf)
                        or self._max_partial_suffix(buf, self._OPEN_TAG)
                    )
                    if held:
                        self._append_visible(out, buf[:-held])
                        self._buf = buf[-held:]
                    else:
                        self._append_visible(out, buf)
                    return "".join(out)
                # 发出标签前的文本，进入 span
                if idx > 0:
                    self._append_visible(out, buf[:idx])
                buf = buf[idx + len(self._OPEN_TAG):]
                self._in_span = True

        return "".join(out)

    def flush(self) -> str:
        """在流结束时发出保留的缓冲区。

        如果仍在未终止的 span 内，剩余内容被丢弃（更安全）。
        否则保留的部分标签尾部被原样发出。

        Returns:
            剩余的可见文本
        """
        if self._in_span:
            self._buf = ""
            self._in_span = False
            return ""

        tail = self._buf
        self._buf = ""
        return tail

    @staticmethod
    def _max_partial_suffix(buf: str, tag: str) -> int:
        """返回最长 buf 后缀的长度，该后缀是 tag 的前缀。

        大小写不敏感。如果没有后缀可以开始标签则返回 0。
        """
        tag_lower = tag.lower()
        buf_lower = buf.lower()
        max_check = min(len(buf_lower), len(tag_lower) - 1)

        for i in range(max_check, 0, -1):
            if tag_lower.startswith(buf_lower[-i:]):
                return i
        return 0

    def _find_boundary_open_tag(self, buf: str) -> int:
        """查找只在块边界开始的打开围栏。"""
        buf_lower = buf.lower()
        search_start = 0

        while True:
            idx = buf_lower.find(self._OPEN_TAG, search_start)
            if idx == -1:
                return -1
            if self._is_block_boundary(buf, idx) and self._has_block_opener_suffix(buf, idx):
                return idx
            search_start = idx + 1

    def _max_pending_open_suffix(self, buf: str) -> int:
        """保留完整的边界标签直到下一个字符确认。"""
        if not buf.lower().endswith(self._OPEN_TAG):
            return 0

        idx = len(buf) - len(self._OPEN_TAG)
        if not self._is_block_boundary(buf, idx):
            return 0

        return len(self._OPEN_TAG)

    def _has_block_opener_suffix(self, buf: str, idx: int) -> bool:
        """检查标签后是否有块开始符。"""
        after_idx = idx + len(self._OPEN_TAG)
        if after_idx >= len(buf):
            return False
        return buf[after_idx] in "\r\n"

    def _is_block_boundary(self, buf: str, idx: int) -> bool:
        """检查位置是否是块边界。"""
        if idx == 0:
            return True
        return buf[idx - 1] in "\r\n"

    def _append_visible(self, out: List[str], text: str) -> None:
        """追加可见文本到输出。"""
        if text:
            out.append(text)


__all__ = [
    "sanitize_context",
    "StreamingContextScrubber",
]