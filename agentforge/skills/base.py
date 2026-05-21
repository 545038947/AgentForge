"""Skill 抽象基类。

定义技能的统一接口。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """技能元数据。

    属性：
        name: 技能名称
        description: 技能描述
        version: 版本号
        author: 作者
        tags: 标签列表
        dependencies: 依赖列表
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


class Skill(ABC):
    """技能抽象基类。

    技能是一组相关的工具和提示模板，用于完成特定任务。

    使用示例：
        class SearchSkill(Skill):
            @property
            def name(self) -> str:
                return "search"

            @property
            def metadata(self) -> SkillMetadata:
                return SkillMetadata(
                    name="search",
                    description="搜索技能",
                )

            def get_tools(self) -> List[Tool]:
                return [SearchTool()]

            def get_prompt_template(self) -> str:
                return "使用搜索工具查找相关信息。"
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """技能名称（唯一标识）。"""
        ...

    @property
    def metadata(self) -> SkillMetadata:
        """技能元数据。"""
        return SkillMetadata(name=self.name)

    def get_tools(self) -> List[Any]:
        """获取技能包含的工具。

        Returns:
            工具列表
        """
        return []

    def get_prompt_template(self) -> Optional[str]:
        """获取提示模板。

        Returns:
            提示模板文本
        """
        return None

    def get_system_prompt(self) -> Optional[str]:
        """获取系统提示。

        Returns:
            系统提示文本
        """
        return None

    def get_examples(self) -> List[Dict[str, Any]]:
        """获取示例。

        Returns:
            示例列表
        """
        return []

    def validate_config(self, config: Dict[str, Any]) -> Optional[str]:
        """验证配置。

        Args:
            config: 配置字典

        Returns:
            错误消息（如果验证失败），None 表示验证通过
        """
        return None

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化技能。

        Args:
            config: 配置字典（可选）
        """
        pass

    def cleanup(self) -> None:
        """清理技能资源。"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "metadata": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "version": self.metadata.version,
                "author": self.metadata.author,
                "tags": self.metadata.tags,
            },
            "tools": [t.name for t in self.get_tools()],
            "prompt_template": self.get_prompt_template(),
        }


class FunctionSkill(Skill):
    """基于函数的技能实现。

    将普通 Python 函数包装为 Skill 实例。

    使用示例：
        skill = FunctionSkill(
            name="search",
            tools=[search_tool],
            prompt_template="使用搜索工具查找信息。",
        )
    """

    def __init__(
        self,
        name: str,
        tools: Optional[List[Any]] = None,
        prompt_template: Optional[str] = None,
        description: str = "",
        metadata: Optional[SkillMetadata] = None,
    ):
        """初始化 FunctionSkill。

        Args:
            name: 技能名称
            tools: 工具列表
            prompt_template: 提示模板
            description: 描述
            metadata: 元数据
        """
        self._name = name
        self._tools = tools or []
        self._prompt_template = prompt_template
        self._metadata = metadata or SkillMetadata(
            name=name,
            description=description,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def metadata(self) -> SkillMetadata:
        return self._metadata

    def get_tools(self) -> List[Any]:
        return self._tools

    def get_prompt_template(self) -> Optional[str]:
        return self._prompt_template