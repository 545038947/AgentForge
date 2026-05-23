"""文件工具。

提供文件读写功能。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agentforge.tools.base import Tool
from agentforge.types import ToolResult

logger = logging.getLogger(__name__)


class FileReadTool(Tool):
    """文件读取工具。"""

    # 工具元信息
    timeout: float = 30.0
    requires_approval: bool = False
    dangerous: bool = False

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return """读取文件内容。

参数：
- path: 文件路径（必需）
- encoding: 编码格式（可选，默认 utf-8）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径",
                },
                "encoding": {
                    "type": "string",
                    "description": "编码格式",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        }

    def execute(
        self,
        tool_call_id: str,
        path: str,
        encoding: str = "utf-8",
        **kwargs,
    ) -> ToolResult:
        """读取文件。

        Args:
            tool_call_id: 工具调用 ID
            path: 文件路径
            encoding: 编码格式

        Returns:
            工具执行结果
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"文件不存在: {path}",
                    is_error=True,
                )

            if not file_path.is_file():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"路径不是文件: {path}",
                    is_error=True,
                )

            content = file_path.read_text(encoding=encoding)

            return ToolResult(
                tool_call_id=tool_call_id,
                content=content,
            )

        except (OSError, FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
            logger.error(f"文件读取错误: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"文件读取错误: {e}",
                is_error=True,
            )


class FileWriteTool(Tool):
    """文件写入工具。"""

    # 工具元信息
    timeout: float = 30.0
    requires_approval: bool = True
    dangerous: bool = True

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return """写入文件内容。

注意：此工具可能覆盖现有文件，需要审批。

参数：
- path: 文件路径（必需）
- content: 文件内容（必需）
- mode: 写入模式（write 或 append，默认 write）
- encoding: 编码格式（可选，默认 utf-8）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "文件内容",
                },
                "mode": {
                    "type": "string",
                    "enum": ["write", "append"],
                    "description": "写入模式",
                    "default": "write",
                },
                "encoding": {
                    "type": "string",
                    "description": "编码格式",
                    "default": "utf-8",
                },
            },
            "required": ["path", "content"],
        }

    def execute(
        self,
        tool_call_id: str,
        path: str,
        content: str,
        mode: str = "write",
        encoding: str = "utf-8",
        **kwargs,
    ) -> ToolResult:
        """写入文件。

        Args:
            tool_call_id: 工具调用 ID
            path: 文件路径
            content: 文件内容
            mode: 写入模式
            encoding: 编码格式

        Returns:
            工具执行结果
        """
        try:
            file_path = Path(path)

            # 创建父目录
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            write_mode = "a" if mode == "append" else "w"
            with open(file_path, write_mode, encoding=encoding) as f:
                f.write(content)

            action = "追加" if mode == "append" else "写入"
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"文件{action}成功: {path}",
            )

        except (OSError, PermissionError, FileNotFoundError) as e:
            logger.error(f"文件写入错误: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"文件写入错误: {e}",
                is_error=True,
            )