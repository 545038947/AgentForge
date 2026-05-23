"""Profile 注册表。

支持懒加载、缓存、继承解析和热重载。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import yaml

from agentforge.profiles.profile import AgentProfile

if TYPE_CHECKING:
    from agentforge.profiles.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class ProfileRegistry:
    """Agent Profile 注册表。

    支持：
    - 懒加载：首次访问时加载
    - 缓存：避免重复加载
    - 继承解析：自动解析 extends 链
    - 热重载：运行时更新配置
    - 验证：检查配置有效性

    使用示例：
        registry = ProfileRegistry(
            provider_registry=provider_registry,
            config_paths=["profiles.yaml"],
        )

        profile = registry.get("security-reviewer")
        errors, warnings = registry.validate("security-reviewer")
        registry.reload()  # 热重载
    """

    def __init__(
        self,
        provider_registry: Optional["ProviderRegistry"] = None,
        config_paths: Optional[List[Path]] = None,
    ):
        """初始化注册表。

        Args:
            provider_registry: Provider 注册表（用于验证）
            config_paths: 配置文件路径列表
        """
        self._provider_registry = provider_registry
        self._config_paths = config_paths or []
        self._cache: Dict[str, AgentProfile] = {}
        self._loaded_from_file = False

    def register(self, profile: AgentProfile) -> None:
        """注册 Profile。

        Args:
            profile: Profile 对象
        """
        self._cache[profile.name] = profile

    def get(self, name: str) -> Optional[AgentProfile]:
        """获取 Profile（懒加载）。

        首次访问时从配置文件加载（如果配置了 config_paths）。

        Args:
            name: Profile 名称

        Returns:
            Profile 对象，如果不存在则返回 None
        """
        # 首次访问时加载配置文件
        if not self._loaded_from_file and self._config_paths:
            self._load_all()
            self._loaded_from_file = True

        if name not in self._cache:
            return None

        profile = self._cache[name]

        # 解析继承
        if profile.extends:
            resolved = profile.resolve(self)
            self._cache[name] = resolved
            return resolved

        return profile

    def reload(self, name: Optional[str] = None) -> None:
        """热重载 Profile。

        Args:
            name: 指定 Profile 名称，None 表示重载全部
        """
        if name:
            self._cache.pop(name, None)
            logger.info(f"已重载 Profile: {name}")
        else:
            self._cache.clear()
            self._loaded_from_file = False
            logger.info("已重载所有 Profile")

    def validate(
        self,
        name: Optional[str] = None,
    ) -> Dict[str, Tuple[List[str], List[str]]]:
        """验证 Profile 有效性。

        Args:
            name: 指定 Profile 名称，None 表示验证全部

        Returns:
            {profile_name: (errors, warnings)}
        """
        results: Dict[str, Tuple[List[str], List[str]]] = {}

        if name:
            profile = self.get(name)
            if profile:
                results[name] = profile.validate(self._provider_registry)
        else:
            # 确保加载所有
            if not self._loaded_from_file and self._config_paths:
                self._load_all()
                self._loaded_from_file = True

            for profile_name, profile in self._cache.items():
                results[profile_name] = profile.validate(self._provider_registry)

        return results

    def list_profiles(self) -> List[str]:
        """列出所有 Profile 名称。

        Returns:
            Profile 名称列表
        """
        # 确保加载
        if not self._loaded_from_file and self._config_paths:
            self._load_all()
            self._loaded_from_file = True

        return list(self._cache.keys())

    def _load_all(self) -> None:
        """从配置文件加载所有 Profile。"""
        for config_path in self._config_paths:
            self._load_from_file(Path(config_path))

    def _load_from_file(self, path: Path) -> None:
        """从单个文件加载 Profile。

        Args:
            path: 配置文件路径
        """
        if not path.exists():
            logger.warning(f"Profile 配置文件不存在: {path}")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for profile_name, profile_data in data.items():
                if not isinstance(profile_data, dict):
                    continue

                profile_data["name"] = profile_name
                profile = AgentProfile.from_dict(profile_data)
                self._cache[profile_name] = profile

            logger.info(f"已从 {path} 加载 {len(data)} 个 Profile")

        except (OSError, yaml.YAMLError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"加载 Profile 配置失败: {path}, 错误: {e}")