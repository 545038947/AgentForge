"""技能加载器。

从文件系统加载技能定义。
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from agentforge.skills.base import Skill, SkillMetadata, FunctionSkill
from agentforge.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillLoader:
    """技能加载器。

    功能：
    - 从目录加载技能
    - 从 YAML/JSON 文件加载技能定义
    - 从 Python 模块加载技能类

    使用示例：
        loader = SkillLoader()
        skills = loader.load_from_directory("/path/to/skills")

        # 注册到全局注册表
        for skill in skills:
            register_skill(skill)
    """

    def __init__(self, registry: Optional[SkillRegistry] = None):
        """初始化技能加载器。

        Args:
            registry: 技能注册表（可选，默认使用全局注册表）
        """
        self._registry = registry or SkillRegistry()

    def load_from_directory(
        self,
        directory: str,
        recursive: bool = False,
    ) -> List[Skill]:
        """从目录加载技能。

        Args:
            directory: 目录路径
            recursive: 是否递归加载

        Returns:
            加载的技能列表
        """
        skills = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.warning(f"目录不存在: {directory}")
            return skills

        # 查找技能定义文件
        patterns = ["*.skill.yaml", "*.skill.yml", "*.skill.json", "SKILL.md"]
        if recursive:
            patterns = [f"**/{p}" for p in patterns]

        for pattern in patterns:
            for file_path in dir_path.glob(pattern):
                try:
                    skill = self._load_skill_file(file_path)
                    if skill:
                        skills.append(skill)
                except Exception as e:
                    logger.warning(f"加载技能文件失败 {file_path}: {e}")

        # 查找 Python 模块
        for file_path in dir_path.glob("**/*.py" if recursive else "*.py"):
            if file_path.name.startswith("_"):
                continue
            try:
                skill = self._load_python_module(file_path)
                if skill:
                    skills.append(skill)
            except Exception as e:
                logger.debug(f"加载 Python 模块失败 {file_path}: {e}")

        return skills

    def _load_skill_file(self, file_path: Path) -> Optional[Skill]:
        """从技能定义文件加载。

        Args:
            file_path: 文件路径

        Returns:
            Skill 实例
        """
        if file_path.suffix in (".yaml", ".yml"):
            return self._load_yaml_skill(file_path)
        elif file_path.suffix == ".json":
            return self._load_json_skill(file_path)
        elif file_path.name == "SKILL.md":
            return self._load_markdown_skill(file_path)

        return None

    def _load_yaml_skill(self, file_path: Path) -> Optional[Skill]:
        """从 YAML 文件加载技能。"""
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            return self._create_skill_from_dict(data)
        except ImportError:
            logger.warning("yaml 库未安装，无法加载 YAML 技能文件")
            return None

    def _load_json_skill(self, file_path: Path) -> Optional[Skill]:
        """从 JSON 文件加载技能。"""
        import json
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self._create_skill_from_dict(data)

    def _load_markdown_skill(self, file_path: Path) -> Optional[Skill]:
        """从 Markdown 文件加载技能。"""
        content = file_path.read_text(encoding="utf-8")

        # 提取技能名称（从文件名或内容）
        name = file_path.parent.name

        # 提取描述（从内容）
        lines = content.split("\n")
        description = ""
        for line in lines:
            if line.startswith("#") and not line.startswith("##"):
                description = line.lstrip("#").strip()
                break

        return FunctionSkill(
            name=name,
            description=description,
            prompt_template=content,
        )

    def _create_skill_from_dict(self, data: Dict[str, Any]) -> Optional[Skill]:
        """从字典创建技能。"""
        if not data:
            return None

        name = data.get("name")
        if not name:
            return None

        metadata = SkillMetadata(
            name=name,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
        )

        return FunctionSkill(
            name=name,
            description=metadata.description,
            metadata=metadata,
            prompt_template=data.get("prompt_template"),
        )

    def _load_python_module(self, file_path: Path) -> Optional[Skill]:
        """从 Python 模块加载技能。"""
        module_name = file_path.stem

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 查找 Skill 子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, Skill) and attr is not Skill:
                try:
                    return attr()
                except Exception as e:
                    logger.debug(f"创建技能实例失败 {attr_name}: {e}")

        return None

    def register_loaded_skills(self, skills: List[Skill]) -> None:
        """注册加载的技能。

        Args:
            skills: 技能列表
        """
        for skill in skills:
            self._registry.register(skill)