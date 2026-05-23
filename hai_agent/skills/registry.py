"""技能注册表。

管理技能的注册、发现和创建。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Type

from hai_agent.skills.base import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册表。

    功能：
    - 注册/移除技能
    - 按名称/标签查找技能
    - 支持插件发现

    使用示例：
        registry = SkillRegistry()
        registry.register(SearchSkill())

        # 查找技能
        skill = registry.get("search")
        skills = registry.find_by_tag("research")
    """

    def __init__(self):
        """初始化技能注册表。"""
        self._skills: Dict[str, Skill] = {}
        self._lock = threading.Lock()

    def register(self, skill: Skill) -> None:
        """注册技能。

        Args:
            skill: Skill 实例
        """
        with self._lock:
            name = skill.name
            if name in self._skills:
                logger.warning(f"技能 {name} 已存在，将被覆盖")
            self._skills[name] = skill

    def unregister(self, name: str) -> bool:
        """取消注册技能。

        Args:
            name: 技能名称

        Returns:
            True 如果成功移除
        """
        with self._lock:
            if name in self._skills:
                skill = self._skills[name]
                skill.cleanup()
                del self._skills[name]
                return True
            return False

    def get(self, name: str) -> Optional[Skill]:
        """获取技能。

        Args:
            name: 技能名称

        Returns:
            Skill 实例，如果不存在则返回 None
        """
        return self._skills.get(name)

    def list(self) -> List[str]:
        """列出所有已注册技能名称。"""
        return list(self._skills.keys())

    def find_by_tag(self, tag: str) -> List[Skill]:
        """按标签查找技能。

        Args:
            tag: 标签名称

        Returns:
            匹配的技能列表
        """
        with self._lock:
            results = []
            for skill in self._skills.values():
                if tag in skill.metadata.tags:
                    results.append(skill)
            return results

    def find_by_description(self, query: str) -> List[Skill]:
        """按描述搜索技能。

        Args:
            query: 搜索查询

        Returns:
            匹配的技能列表
        """
        with self._lock:
            results = []
            query_lower = query.lower()
            for skill in self._skills.values():
                if query_lower in skill.metadata.description.lower():
                    results.append(skill)
            return results

    def get_all(self) -> Dict[str, Skill]:
        """获取所有技能。"""
        return self._skills.copy()

    def get_tools_for_skill(self, name: str) -> List[Any]:
        """获取技能的工具列表。

        Args:
            name: 技能名称

        Returns:
            工具列表
        """
        skill = self.get(name)
        if skill is None:
            return []
        return skill.get_tools()

    def get_prompt_for_skill(self, name: str) -> Optional[str]:
        """获取技能的提示模板。

        Args:
            name: 技能名称

        Returns:
            提示模板文本
        """
        skill = self.get(name)
        if skill is None:
            return None
        return skill.get_prompt_template()

    def clear(self) -> None:
        """清空注册表。"""
        with self._lock:
            for skill in self._skills.values():
                skill.cleanup()
            self._skills.clear()


# 全局技能注册表
_global_registry = SkillRegistry()


def register_skill(skill: Skill) -> None:
    """注册技能到全局注册表。"""
    _global_registry.register(skill)


def get_skill(name: str) -> Optional[Skill]:
    """从全局注册表获取技能。"""
    return _global_registry.get(name)


def list_skills() -> List[str]:
    """列出全局注册表中的所有技能。"""
    return _global_registry.list()