"""Shell 工具。

提供命令行执行功能。
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any, Dict

from hai_agent.tools.base import Tool
from hai_agent.types import ToolResult

logger = logging.getLogger(__name__)


class ShellTool(Tool):
    """Shell 工具。

    执行系统命令。

    使用示例：
        tool = ShellTool()

        result = tool.execute(
            tool_call_id="call-1",
            command="ls -la",
        )
    """

    # 工具元信息
    timeout: float = 60.0
    requires_approval: bool = True
    dangerous: bool = True

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return """执行系统命令。

注意：此工具可能执行危险操作，需要审批。

参数：
- command: 要执行的命令（必需）
- timeout: 超时时间（秒，可选，默认 60）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令",
                },
                "timeout": {
                    "type": "number",
                    "description": "超时时间（秒）",
                },
            },
            "required": ["command"],
        }

    def should_approve(self, args: Dict[str, Any]) -> bool:
        """判断是否需要审批。

        Args:
            args: 工具参数

        Returns:
            True 如果需要审批
        """
        command = args.get("command", "")

        # 危险命令列表
        dangerous_commands = [
            "rm -rf",
            "rm -r",
            "del /",
            "format",
            "mkfs",
            "dd if=",
            "> /dev/",
            "chmod 777",
            "chown",
        ]

        for dangerous in dangerous_commands:
            if dangerous in command.lower():
                return True

        return self.requires_approval

    def execute(
        self,
        tool_call_id: str,
        command: str,
        timeout: float = 60.0,
        **kwargs,
    ) -> ToolResult:
        """执行命令。

        Args:
            tool_call_id: 工具调用 ID
            command: 要执行的命令
            timeout: 超时时间

        Returns:
            工具执行结果
        """
        start_time = time.time()

        try:
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=min(timeout, self.timeout),
            )

            duration = time.time() - start_time

            # 构建输出
            output_parts = []

            if result.stdout:
                output_parts.append(f"标准输出:\n{result.stdout}")

            if result.stderr:
                output_parts.append(f"标准错误:\n{result.stderr}")

            output_parts.append(f"退出码: {result.returncode}")
            output_parts.append(f"执行时间: {duration:.2f}s")

            content = "\n".join(output_parts)

            if result.returncode == 0:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=content,
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"命令执行失败:\n{content}",
                    is_error=True,
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"命令执行超时（{timeout}s）",
                is_error=True,
            )

        except (OSError, subprocess.SubprocessError, PermissionError) as e:
            logger.error(f"命令执行错误: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"命令执行错误: {e}",
                is_error=True,
            )