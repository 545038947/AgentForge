"""Agent Profile 数据类。

定义专家 Agent 的声明式配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from hai_agent.profiles.registry import ProfileRegistry
    from hai_agent.profiles.provider_registry import ProviderRegistry


@dataclass
class AgentProfile:
    """专家 Agent 的声明式配置。

    不持有敏感信息（API Key 等），只定义行为配置。

    属性：
        name: Profile 名称（必需）
        description: 描述
        extends: 继承的父 Profile 名称
        provider: Provider 名称
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大输出 token
        reasoning_effort: 推理深度 (low/medium/high/max)
        toolsets: 可用工具集列表
        blocked_tools: 禁止的工具列表
        system_prompt: 系统提示
        inherit_memory: 是否继承父 Agent 记忆
        inherit_tools: 是否继承父 Agent 工具
        enabled: 是否启用
    """

    # 基本信息
    name: str
    description: str = ""
    extends: Optional[str] = None

    # Provider 配置
    provider: Optional[str] = None
    model: Optional[str] = None

    # 模型参数
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning_effort: Optional[str] = None

    # 工具配置
    toolsets: Optional[List[str]] = None
    blocked_tools: Optional[List[str]] = None

    # 行为配置
    system_prompt: Optional[str] = None
    inherit_memory: bool = False
    inherit_tools: bool = True

    # 状态
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。"""
        result = {"name": self.name}

        if self.description:
            result["description"] = self.description
        if self.extends:
            result["extends"] = self.extends
        if self.provider:
            result["provider"] = self.provider
        if self.model:
            result["model"] = self.model
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens
        if self.reasoning_effort:
            result["reasoning_effort"] = self.reasoning_effort
        if self.toolsets:
            result["toolsets"] = self.toolsets
        if self.blocked_tools:
            result["blocked_tools"] = self.blocked_tools
        if self.system_prompt:
            result["system_prompt"] = self.system_prompt
        if not self.inherit_memory:
            result["inherit_memory"] = self.inherit_memory
        if not self.inherit_tools:
            result["inherit_tools"] = self.inherit_tools
        if not self.enabled:
            result["enabled"] = self.enabled

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentProfile":
        """从字典创建 Profile。

        Args:
            data: 字典数据

        Returns:
            AgentProfile 实例
        """
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            extends=data.get("extends"),
            provider=data.get("provider"),
            model=data.get("model"),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
            reasoning_effort=data.get("reasoning_effort"),
            toolsets=data.get("toolsets"),
            blocked_tools=data.get("blocked_tools"),
            system_prompt=data.get("system_prompt"),
            inherit_memory=data.get("inherit_memory", False),
            inherit_tools=data.get("inherit_tools", True),
            enabled=data.get("enabled", True),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "AgentProfile":
        """从 YAML 文件加载 Profile。

        Args:
            path: YAML 文件路径

        Returns:
            AgentProfile 实例
        """
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            return cls.from_dict(data)
        raise ValueError(f"无效的 Profile 格式: {path}")

    def resolve(
        self,
        registry: Optional["ProfileRegistry"],
    ) -> "AgentProfile":
        """解析继承关系，返回完整配置。

        如果有 extends 字段，从 registry 获取父 Profile 并合并。

        Args:
            registry: Profile 注册表

        Returns:
            解析后的完整 Profile
        """
        if self.extends is None or registry is None:
            return self

        parent = registry.get(self.extends)
        if parent is None:
            return self

        # 递归解析父 Profile
        parent_resolved = parent.resolve(registry)

        # 合并配置（子配置覆盖父配置）
        return self._merge(parent_resolved)

    def _merge(self, parent: "AgentProfile") -> "AgentProfile":
        """与父 Profile 合并。

        子 Profile 的非 None 值覆盖父 Profile。

        Args:
            parent: 父 Profile

        Returns:
            合并后的 Profile
        """
        return AgentProfile(
            name=self.name,
            description=self.description or parent.description,
            extends=None,  # 解析后清除 extends
            provider=self.provider or parent.provider,
            model=self.model or parent.model,
            temperature=self.temperature if self.temperature is not None else parent.temperature,
            max_tokens=self.max_tokens if self.max_tokens is not None else parent.max_tokens,
            reasoning_effort=self.reasoning_effort or parent.reasoning_effort,
            toolsets=self.toolsets if self.toolsets is not None else parent.toolsets,
            blocked_tools=self.blocked_tools if self.blocked_tools is not None else parent.blocked_tools,
            system_prompt=self.system_prompt or parent.system_prompt,
            inherit_memory=self.inherit_memory,
            inherit_tools=self.inherit_tools,
            enabled=self.enabled,
        )

    def validate(
        self,
        provider_registry: Optional["ProviderRegistry"],
    ) -> Tuple[List[str], List[str]]:
        """验证 Profile 配置有效性。

        Args:
            provider_registry: Provider 注册表（可选）

        Returns:
            (errors, warnings): 错误列表和警告列表
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 基本验证
        if not self.name:
            errors.append("Profile 名称不能为空")

        # Provider 验证
        if self.provider and provider_registry:
            if not provider_registry.is_available(self.provider):
                errors.append(f"Provider '{self.provider}' 凭证未配置")

        # 模型验证
        if self.provider and not self.model:
            warnings.append(f"Profile '{self.name}' 指定了 provider 但未指定 model")

        # temperature 范围验证
        if self.temperature is not None:
            if not 0 <= self.temperature <= 2:
                errors.append(f"temperature 必须在 [0, 2] 范围内，当前: {self.temperature}")

        # reasoning_effort 验证
        if self.reasoning_effort:
            valid_efforts = {"low", "medium", "high", "max"}
            if self.reasoning_effort not in valid_efforts:
                errors.append(
                    f"reasoning_effort 必须是 {valid_efforts} 之一，当前: {self.reasoning_effort}"
                )

        return errors, warnings