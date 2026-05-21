"""Web 工具。

提供网络请求功能。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agentforge.tools.base import Tool
from agentforge.types import ToolResult

logger = logging.getLogger(__name__)


class WebFetchTool(Tool):
    """Web 获取工具。"""

    # 工具元信息
    timeout: float = 30.0
    requires_approval: bool = False
    dangerous: bool = False

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return """获取网页内容。

参数：
- url: 网页 URL（必需）
- timeout: 超时时间（秒，可选，默认 30）
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "网页 URL",
                },
                "timeout": {
                    "type": "number",
                    "description": "超时时间（秒）",
                },
            },
            "required": ["url"],
        }

    def execute(
        self,
        tool_call_id: str,
        url: str,
        timeout: float = 30.0,
        **kwargs,
    ) -> ToolResult:
        """获取网页。

        Args:
            tool_call_id: 工具调用 ID
            url: 网页 URL
            timeout: 超时时间

        Returns:
            工具执行结果
        """
        try:
            # 尝试导入 httpx
            try:
                import httpx
                with httpx.Client(timeout=min(timeout, self.timeout)) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    content = response.text
            except ImportError:
                # 回退到 urllib
                import urllib.request
                from urllib.error import URLError, HTTPError

                with urllib.request.urlopen(url, timeout=min(timeout, self.timeout)) as response:
                    content = response.read().decode("utf-8")

            return ToolResult(
                tool_call_id=tool_call_id,
                content=content[:10000],  # 限制内容长度
            )

        except Exception as e:
            logger.error(f"网页获取错误: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"网页获取错误: {e}",
                is_error=True,
            )