"""Demo 配置管理模块。

支持从 YAML 文件加载配置，并提供默认值。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class OllamaConfig:
    """Ollama 服务配置。"""

    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2"
    timeout: float = 600.0


@dataclass
class AgentConfig:
    """Agent 配置。"""

    system_prompt: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class MemoryConfig:
    """记忆系统配置。"""

    store_path: str = "./memory_store"
    auto_extract: bool = False


@dataclass
class DelegationConfig:
    """委托系统配置。"""

    max_concurrent: int = 3
    max_depth: int = 2


@dataclass
class DemoConfig:
    """Demo 总配置。"""

    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    delegation: DelegationConfig = field(default_factory=DelegationConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DemoConfig":
        """从 YAML 文件加载配置。

        Args:
            path: 配置文件路径

        Returns:
            DemoConfig 实例
        """
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls(
            ollama=OllamaConfig(
                base_url=data.get("ollama", {}).get("base_url", "http://localhost:11434/v1"),
                model=data.get("ollama", {}).get("model", "llama3.2"),
                timeout=data.get("ollama", {}).get("timeout", 600.0),
            ),
            agent=AgentConfig(
                system_prompt=data.get("agent", {}).get("system_prompt", ""),
                max_tokens=data.get("agent", {}).get("max_tokens", 4096),
                temperature=data.get("agent", {}).get("temperature", 0.7),
            ),
            memory=MemoryConfig(
                store_path=data.get("memory", {}).get("store_path", "./memory_store"),
                auto_extract=data.get("memory", {}).get("auto_extract", False),
            ),
            delegation=DelegationConfig(
                max_concurrent=data.get("delegation", {}).get("max_concurrent", 3),
                max_depth=data.get("delegation", {}).get("max_depth", 2),
            ),
        )

    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> "DemoConfig":
        """加载配置。

        按以下顺序查找配置文件：
        1. 指定的路径
        2. 当前目录的 demo/config.yaml
        3. 项目根目录的 demo/config.yaml

        Args:
            config_path: 配置文件路径（可选）

        Returns:
            DemoConfig 实例
        """
        search_paths = []

        if config_path:
            search_paths.append(Path(config_path))

        # 当前目录
        search_paths.append(Path("config.yaml"))
        search_paths.append(Path("demo/config.yaml"))

        # 项目根目录（相对于此文件）
        project_root = Path(__file__).parent.parent
        search_paths.append(project_root / "demo" / "config.yaml")

        for path in search_paths:
            if path.exists():
                return cls.from_yaml(path)

        return cls()


# 全局配置实例
_config: Optional[DemoConfig] = None


def get_config(config_path: Optional[str | Path] = None) -> DemoConfig:
    """获取配置实例。

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        DemoConfig 实例
    """
    global _config
    if _config is None:
        _config = DemoConfig.load(config_path)
    return _config


def reload_config(config_path: Optional[str | Path] = None) -> DemoConfig:
    """重新加载配置。

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        DemoConfig 实例
    """
    global _config
    _config = DemoConfig.load(config_path)
    return _config
