"""配置验证与加载。

使用 Pydantic 进行配置验证，支持从文件、环境变量加载配置。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator


class ProviderSettings(BaseModel):
    """Provider 配置。"""
    api_key: Optional[SecretStr] = None
    base_url: Optional[str] = None
    timeout: float = Field(default=300.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    default_model: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头")
        return v


class CompressionSettings(BaseModel):
    """上下文压缩配置。"""
    enabled: bool = True
    max_tokens: int = Field(default=128000, gt=0)
    head_protect_ratio: float = Field(default=0.1, ge=0, le=1)
    tail_protect_ratio: float = Field(default=0.3, ge=0, le=1)
    strategy: str = "summarize"  # "prune" | "summarize"

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        valid = ("prune", "summarize")
        if v not in valid:
            raise ValueError(f"strategy 必须是 {valid} 之一")
        return v


class DelegationSettings(BaseModel):
    """委托配置。"""
    max_depth: int = Field(default=1, ge=0)
    inherit_tools: bool = True
    inherit_memory: bool = False
    blocked_tools: FrozenSet[str] = Field(
        default_factory=lambda: frozenset([
            "delegate_task",
            "clarify",
            "memory",
            "send_message",
            "execute_code",
        ])
    )
    timeout: float = Field(default=300.0, gt=0)
    heartbeat_interval: float = Field(default=30.0, gt=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_to_parent: bool = True


class ExecutorSettings(BaseModel):
    """工具执行器配置。"""
    max_workers: int = Field(default=10, gt=0, le=50)
    queue_size: int = Field(default=100, gt=0)
    default_timeout: float = Field(default=300.0, gt=0)


class Settings(BaseModel):
    """Agent 主配置。"""
    model: str
    max_tokens: int = Field(default=4096, gt=0)
    temperature: float = Field(default=1.0, ge=0, le=2)

    # 执行控制
    max_retries: int = Field(default=3, ge=0)
    max_iterations: int = Field(default=10, ge=1)

    # 子配置
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    compression: CompressionSettings = Field(default_factory=CompressionSettings)
    delegation: DelegationSettings = Field(default_factory=DelegationSettings)
    executor: ExecutorSettings = Field(default_factory=ExecutorSettings)

    # 其他配置
    system_prompt: Optional[str] = None
    debug: bool = False

    @classmethod
    def from_file(cls, path: Path) -> "Settings":
        """从 YAML/JSON 文件加载配置。

        支持环境变量引用：${ENV_VAR} 格式。
        """
        import json

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        content = path.read_text(encoding="utf-8")

        # 替换环境变量引用
        content = cls._expand_env_vars(content)

        # 解析 JSON 或 YAML
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(content)
            except ImportError:
                # YAML 不可用时尝试 JSON 解析
                data = json.loads(content)
        else:
            data = json.loads(content)

        return cls(**data)

    @classmethod
    def from_env(cls, prefix: str = "AGENTFORGE_") -> "Settings":
        """从环境变量加载配置。

        环境变量命名规则：
        - AGENTFORGE_MODEL: model
        - AGENTFORGE_MAX_TOKENS: max_tokens
        - AGENTFORGE_PROVIDER_API_KEY: provider.api_key
        - AGENTFORGE_PROVIDER_BASE_URL: provider.base_url
        """
        data: Dict[str, Any] = {}

        # 遍历环境变量
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue

            # 移除前缀，转换为配置路径
            config_path = key[len(prefix):].lower()

            # 解析嵌套路径（如 PROVIDER_API_KEY -> provider.api_key）
            parts = config_path.split("_")

            # 特殊处理：MAX_TOKENS 是单个配置项，不是嵌套
            if len(parts) == 1:
                # 顶层配置
                data[parts[0]] = cls._parse_env_value(value)
            elif len(parts) == 2 and parts[0] in ("max", "temperature", "debug", "system"):
                # 处理 max_tokens, temperature 等两单词顶层配置
                combined_key = f"{parts[0]}_{parts[1]}"
                data[combined_key] = cls._parse_env_value(value)
            else:
                # 嵌套配置（如 provider_api_key -> provider.api_key）
                parent_key = parts[0]
                child_key = "_".join(parts[1:])
                if parent_key not in data:
                    data[parent_key] = {}
                data[parent_key][child_key] = cls._parse_env_value(value)

        return cls(**data)

    @staticmethod
    def _expand_env_vars(content: str) -> str:
        """展开配置文件中的环境变量引用。

        格式：${ENV_VAR} 或 ${ENV_VAR:default_value}
        """
        pattern = r"\$\{([^}:]+)(?:([^}]*))?\}"

        def replace(match):
            env_var = match.group(1)
            default = match.group(2) if match.group(2) else ""
            return os.environ.get(env_var, default)

        return re.sub(pattern, replace, content)

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """解析环境变量值。

        尝试转换为适当类型：
        - 数字: int/float
        - 布尔: true/false
        - 列表:逗号分隔
        - 字符串: 原值
        """
        # 布尔值
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # 数字
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # 列表（逗号分隔）
        if "," in value:
            return [v.strip() for v in value.split(",")]

        # 字符串
        return value

    def get_api_key(self) -> Optional[str]:
        """获取 API 密钥（解密 SecretStr）。"""
        if self.provider.api_key:
            return self.provider.api_key.get_secret_value()
        return None