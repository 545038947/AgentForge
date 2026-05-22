"""工具集系统。

支持工具分组和条件启用，参考 hermes-agent/toolsets.py 实现。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolsetDefinition:
    """工具集定义。

    支持工具分组和条件启用。

    Attributes:
        description: 工具集描述
        tools: 包含的工具名称列表
        includes: 包含的其他工具集名称
        check_fn: 运行时检查函数，返回 False 时工具集不可用
        requires_env: 需要的环境变量列表
    """

    description: str
    tools: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    check_fn: Optional[Callable[[], bool]] = None
    requires_env: List[str] = field(default_factory=list)

    def is_available(self) -> bool:
        """检查工具集是否可用。

        Returns:
            如果所有条件满足则返回 True
        """
        # 检查环境变量
        for env_var in self.requires_env:
            if not os.environ.get(env_var):
                logger.debug(f"工具集缺少环境变量: {env_var}")
                return False

        # 检查自定义函数
        if self.check_fn is not None:
            try:
                if not self.check_fn():
                    logger.debug("工具集条件检查未通过")
                    return False
            except Exception as e:
                logger.debug(f"工具集条件检查异常: {e}")
                return False

        return True


class ToolsetRegistry:
    """工具集注册表。

    管理工具集定义和解析。
    """

    def __init__(self):
        self._definitions: Dict[str, ToolsetDefinition] = {}
        self._tool_to_toolset: Dict[str, str] = {}

    def register(self, name: str, definition: ToolsetDefinition) -> None:
        """注册工具集。

        Args:
            name: 工具集名称
            definition: 工具集定义
        """
        self._definitions[name] = definition
        for tool_name in definition.tools:
            self._tool_to_toolset[tool_name] = name
        logger.debug(f"已注册工具集: {name}")

    def get(self, name: str) -> Optional[ToolsetDefinition]:
        """获取工具集定义。

        Args:
            name: 工具集名称

        Returns:
            工具集定义，不存在则返回 None
        """
        return self._definitions.get(name)

    def resolve(self, name: str, visited: Optional[Set[str]] = None) -> List[str]:
        """递归解析工具集，返回所有工具名称。

        Args:
            name: 工具集名称
            visited: 已访问的工具集（防止循环引用）

        Returns:
            工具名称列表
        """
        if visited is None:
            visited = set()

        if name in visited:
            logger.warning(f"检测到工具集循环引用: {name}")
            return []

        visited.add(name)
        definition = self._definitions.get(name)
        if not definition:
            logger.warning(f"工具集不存在: {name}")
            return []

        tools = set(definition.tools)

        # 递归解析包含的工具集
        for included_name in definition.includes:
            included_tools = self.resolve(included_name, visited)
            tools.update(included_tools)

        return sorted(tools)

    def check_requirements(self, name: str) -> Optional[str]:
        """检查工具集要求是否满足。

        Args:
            name: 工具集名称

        Returns:
            错误信息，如果满足要求则返回 None
        """
        definition = self._definitions.get(name)
        if not definition:
            return f"工具集 '{name}' 不存在"

        # 检查环境变量
        missing_env = [
            env for env in definition.requires_env
            if not os.environ.get(env)
        ]
        if missing_env:
            return f"缺少环境变量: {', '.join(missing_env)}"

        # 检查自定义函数
        if definition.check_fn is not None:
            try:
                if not definition.check_fn():
                    return f"工具集 '{name}' 的条件检查未通过"
            except Exception as e:
                return f"工具集 '{name}' 条件检查异常: {e}"

        return None

    def list_available(self) -> List[str]:
        """列出所有可用的工具集。

        Returns:
            可用工具集名称列表
        """
        return [
            name for name, definition in self._definitions.items()
            if definition.is_available()
        ]

    def list_all(self) -> List[str]:
        """列出所有已注册的工具集。

        Returns:
            所有工具集名称列表
        """
        return list(self._definitions.keys())


# 全局注册表
_global_registry = ToolsetRegistry()


def register_toolset(name: str, definition: ToolsetDefinition) -> None:
    """注册工具集到全局注册表。

    Args:
        name: 工具集名称
        definition: 工具集定义
    """
    _global_registry.register(name, definition)


def get_toolset(name: str) -> Optional[ToolsetDefinition]:
    """从全局注册表获取工具集。

    Args:
        name: 工具集名称

    Returns:
        工具集定义
    """
    return _global_registry.get(name)


def resolve_toolset(name: str) -> List[str]:
    """解析工具集获取工具列表。

    Args:
        name: 工具集名称

    Returns:
        工具名称列表
    """
    return _global_registry.resolve(name)


# 预定义工具集
BUILTIN_TOOLSETS = {
    "web": ToolsetDefinition(
        description="网络搜索和内容提取工具",
        tools=["web_search", "web_extract"],
    ),
    "terminal": ToolsetDefinition(
        description="终端命令执行工具",
        tools=["terminal", "process"],
    ),
    "file": ToolsetDefinition(
        description="文件操作工具",
        tools=["read_file", "write_file", "patch", "search_files"],
    ),
    "vision": ToolsetDefinition(
        description="图像分析工具",
        tools=["vision_analyze"],
    ),
    "browser": ToolsetDefinition(
        description="浏览器自动化工具",
        tools=[
            "browser_navigate", "browser_snapshot", "browser_click",
            "browser_type", "browser_scroll", "browser_back",
        ],
        includes=["web"],
    ),
    "delegate": ToolsetDefinition(
        description="子 Agent 委托工具",
        tools=["delegate_task"],
    ),
}

# 注册内置工具集
for name, definition in BUILTIN_TOOLSETS.items():
    register_toolset(name, definition)


__all__ = [
    "ToolsetDefinition",
    "ToolsetRegistry",
    "register_toolset",
    "get_toolset",
    "resolve_toolset",
    "BUILTIN_TOOLSETS",
]
