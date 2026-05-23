# Agent Profile System 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现声明式的专家 Agent Profile 系统，支持主 Agent 调度具有不同 Provider/模型/能力的子 Agent。

**Architecture:** 三层分离（Profile 配置 → ProviderRegistry 认证 → DelegationManager 执行），懒加载缓存，Profile 继承，回退机制。

**Tech Stack:** Python 3.10+, Pydantic, dataclasses, YAML 配置

---

## 文件结构

```
agentforge/profiles/
├── __init__.py              # 模块导出
├── profile.py               # AgentProfile 数据类
├── provider_registry.py     # Provider 认证注册表
└── registry.py              # Profile 注册表（懒加载+缓存）

agentforge/delegation/
├── config.py                # 修改：扩展 TaskSpec
└── manager.py               # 修改：集成 Profile 解析

agentforge/events/
└── types.py                 # 修改：新增 Profile 相关事件

agentforge/
└── agent.py                 # 修改：支持 profile_registry 参数

agentforge/
└── __init__.py              # 修改：导出 profiles 模块

tests/
├── test_agent_profile.py    # 新建：AgentProfile 测试
├── test_provider_registry.py # 新建：ProviderRegistry 测试
└── test_profile_registry.py  # 新建：ProfileRegistry 测试
```

---

## Task 1: 创建 AgentProfile 数据类

**Files:**
- Create: `agentforge/profiles/__init__.py` (空文件占位)
- Create: `agentforge/profiles/profile.py`
- Create: `tests/test_agent_profile.py`

- [ ] **Step 1: 创建 profiles 目录和 __init__.py**

```bash
mkdir -p agentforge/profiles
touch agentforge/profiles/__init__.py
```

- [ ] **Step 2: 编写 AgentProfile 测试**

创建 `tests/test_agent_profile.py`:

```python
"""AgentProfile 单元测试。"""

import pytest
from agentforge.profiles.profile import AgentProfile


class TestAgentProfile:
    """AgentProfile 测试。"""

    def test_create_minimal_profile(self):
        """测试创建最小 Profile。"""
        profile = AgentProfile(name="test-profile")

        assert profile.name == "test-profile"
        assert profile.description == ""
        assert profile.provider is None
        assert profile.model is None
        assert profile.enabled is True

    def test_create_full_profile(self):
        """测试创建完整 Profile。"""
        profile = AgentProfile(
            name="security-reviewer",
            description="安全审查专家",
            provider="deepseek",
            model="deepseek-reasoner",
            temperature=0.3,
            max_tokens=4096,
            toolsets=["read", "terminal"],
            system_prompt="你是安全工程师...",
            inherit_memory=False,
            inherit_tools=True,
        )

        assert profile.name == "security-reviewer"
        assert profile.provider == "deepseek"
        assert profile.model == "deepseek-reasoner"
        assert profile.temperature == 0.3
        assert profile.toolsets == ["read", "terminal"]

    def test_to_dict(self):
        """测试序列化为字典。"""
        profile = AgentProfile(
            name="test",
            provider="openai",
            model="gpt-4",
        )

        result = profile.to_dict()

        assert result["name"] == "test"
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4"

    def test_from_dict(self):
        """测试从字典反序列化。"""
        data = {
            "name": "test",
            "provider": "anthropic",
            "model": "claude-3-opus",
            "temperature": 0.7,
        }

        profile = AgentProfile.from_dict(data)

        assert profile.name == "test"
        assert profile.provider == "anthropic"
        assert profile.model == "claude-3-opus"
        assert profile.temperature == 0.7

    def test_resolve_no_inheritance(self):
        """测试无继承时的 resolve。"""
        profile = AgentProfile(
            name="test",
            provider="openai",
            model="gpt-4",
        )

        # 无继承时，resolve 返回自身
        resolved = profile.resolve(None)

        assert resolved is profile

    def test_validate_valid_profile(self):
        """测试有效 Profile 的验证。"""
        profile = AgentProfile(
            name="test",
            provider="openai",
            model="gpt-4",
        )

        errors, warnings = profile.validate(None)

        # 无 ProviderRegistry 时，只做基本验证
        assert errors == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_agent_profile.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'agentforge.profiles'"

- [ ] **Step 4: 实现 AgentProfile 数据类**

创建 `agentforge/profiles/profile.py`:

```python
"""Agent Profile 数据类。

定义专家 Agent 的声明式配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from agentforge.profiles.registry import ProfileRegistry
    from agentforge.profiles.provider_registry import ProviderRegistry


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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_agent_profile.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add agentforge/profiles/__init__.py agentforge/profiles/profile.py tests/test_agent_profile.py
git commit -m "feat(profiles): 添加 AgentProfile 数据类

- 支持声明式配置专家 Agent
- 支持 Profile 继承和合并
- 支持配置验证"
```

---

## Task 2: 创建 ProviderRegistry

**Files:**
- Create: `agentforge/profiles/provider_registry.py`
- Create: `tests/test_provider_registry.py`

- [ ] **Step 1: 编写 ProviderCredentials 和 ProviderRegistry 测试**

创建 `tests/test_provider_registry.py`:

```python
"""ProviderRegistry 单元测试。"""

import os
import pytest
from pathlib import Path
from agentforge.profiles.provider_registry import (
    ProviderCredentials,
    ProviderRegistry,
)


class TestProviderCredentials:
    """ProviderCredentials 测试。"""

    def test_create_credentials(self):
        """测试创建凭证。"""
        cred = ProviderCredentials(
            provider="openai",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )

        assert cred.provider == "openai"
        assert cred.api_key == "sk-test"
        assert cred.base_url == "https://api.openai.com/v1"

    def test_create_minimal_credentials(self):
        """测试创建最小凭证。"""
        cred = ProviderCredentials(provider="test")

        assert cred.provider == "test"
        assert cred.api_key is None


class TestProviderRegistry:
    """ProviderRegistry 测试。"""

    def test_register_and_get_credentials(self):
        """测试注册和获取凭证。"""
        registry = ProviderRegistry()
        cred = ProviderCredentials(
            provider="openai",
            api_key="sk-test",
        )

        registry.register("openai", cred)
        result = registry.get_credentials("openai")

        assert result is not None
        assert result.api_key == "sk-test"

    def test_get_nonexistent_credentials(self):
        """测试获取不存在的凭证。"""
        registry = ProviderRegistry()
        result = registry.get_credentials("nonexistent")

        assert result is None

    def test_is_available(self):
        """测试检查可用性。"""
        registry = ProviderRegistry()
        cred = ProviderCredentials(provider="openai", api_key="sk-test")

        registry.register("openai", cred)

        assert registry.is_available("openai") is True
        assert registry.is_available("nonexistent") is False

    def test_priority_runtime_over_config(self):
        """测试优先级：运行时覆盖 > 配置文件。"""
        registry = ProviderRegistry()

        # 配置文件凭证
        config_cred = ProviderCredentials(provider="openai", api_key="config-key")
        registry._config_credentials["openai"] = config_cred

        # 运行时覆盖
        runtime_cred = ProviderCredentials(provider="openai", api_key="runtime-key")
        registry.register("openai", runtime_cred, override=True)

        result = registry.get_credentials("openai")
        assert result.api_key == "runtime-key"

    def test_load_from_env(self, monkeypatch):
        """测试从环境变量加载。"""
        monkeypatch.setenv("TEST_PROVIDER_API_KEY", "env-test-key")

        registry = ProviderRegistry()
        # 模拟 ProviderProfile 的 env_vars
        registry._provider_profiles = {
            "test-provider": {"env_vars": ["TEST_PROVIDER_API_KEY"], "base_url": None}
        }

        result = registry._load_from_env("test-provider")
        assert result is not None
        assert result.api_key == "env-test-key"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_provider_registry.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 实现 ProviderRegistry**

创建 `agentforge/profiles/provider_registry.py`:

```python
"""Provider 认证注册表。

管理 Provider 的认证信息，支持多来源优先级。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import yaml


@dataclass
class ProviderCredentials:
    """Provider 认证凭证。

    不直接暴露 API Key，通过属性访问。

    属性：
        provider: Provider 名称
        api_key: API 密钥
        base_url: API 基础 URL
        api_mode: API 模式 (chat_completions / anthropic / etc)
        extra_headers: 额外的请求头
    """

    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_mode: Optional[str] = None
    extra_headers: Dict[str, str] = field(default_factory=dict)


class ProviderRegistry:
    """Provider 认证信息注册表。

    认证优先级（从高到低）：
    1. 运行时覆盖（代码显式传入）
    2. 配置文件（providers.yaml）
    3. 环境变量

    使用示例：
        registry = ProviderRegistry()
        registry.register("openai", ProviderCredentials(
            provider="openai",
            api_key="sk-xxx",
        ))
        registry.load_from_config("providers.yaml")

        if registry.is_available("openai"):
            cred = registry.get_credentials("openai")
    """

    def __init__(self):
        """初始化注册表。"""
        # 运行时覆盖（最高优先级）
        self._runtime_overrides: Dict[str, ProviderCredentials] = {}
        # 配置文件凭证
        self._config_credentials: Dict[str, ProviderCredentials] = {}
        # Provider Profile 信息（用于环境变量加载）
        self._provider_profiles: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        provider: str,
        credentials: ProviderCredentials,
        override: bool = False,
    ) -> None:
        """注册 Provider 凭证。

        Args:
            provider: Provider 名称
            credentials: 凭证对象
            override: 是否作为运行时覆盖（优先级最高）
        """
        if override:
            self._runtime_overrides[provider] = credentials
        else:
            self._config_credentials[provider] = credentials

    def get_credentials(self, provider: str) -> Optional[ProviderCredentials]:
        """获取 Provider 凭证（按优先级）。

        优先级：运行时覆盖 > 配置文件 > 环境变量

        Args:
            provider: Provider 名称

        Returns:
            凭证对象，如果不存在则返回 None
        """
        # 1. 运行时覆盖
        if cred := self._runtime_overrides.get(provider):
            return cred

        # 2. 配置文件
        if cred := self._config_credentials.get(provider):
            return cred

        # 3. 环境变量
        return self._load_from_env(provider)

    def is_available(self, provider: str) -> bool:
        """检查 Provider 是否可用（有凭证）。

        Args:
            provider: Provider 名称

        Returns:
            是否可用
        """
        cred = self.get_credentials(provider)
        return cred is not None and cred.api_key is not None

    @contextmanager
    def acquire(self, provider: str) -> Iterator[Optional[ProviderCredentials]]:
        """获取执行槽位。

        预留用于 Rate Limit 控制。

        Args:
            provider: Provider 名称

        Yields:
            凭证对象
        """
        yield self.get_credentials(provider)

    def load_from_config(self, path: Path) -> None:
        """从配置文件加载凭证。

        支持环境变量引用：${ENV_VAR}

        Args:
            path: 配置文件路径
        """
        if not path.exists():
            return

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        providers = data.get("providers", {})
        for provider_name, config in providers.items():
            if not isinstance(config, dict):
                continue

            # 解析环境变量引用
            api_key = config.get("api_key")
            if api_key and isinstance(api_key, str) and api_key.startswith("${"):
                env_var = api_key[2:-1]  # 提取 ${...} 中的变量名
                api_key = os.getenv(env_var)

            cred = ProviderCredentials(
                provider=provider_name,
                api_key=api_key,
                base_url=config.get("base_url"),
                api_mode=config.get("api_mode"),
                extra_headers=config.get("extra_headers", {}),
            )
            self._config_credentials[provider_name] = cred

    def _load_from_env(self, provider: str) -> Optional[ProviderCredentials]:
        """从环境变量加载凭证。

        Args:
            provider: Provider 名称

        Returns:
            凭证对象，如果不存在则返回 None
        """
        # 尝试从 ProviderProfile 获取环境变量名
        profile = self._provider_profiles.get(provider, {})
        env_vars = profile.get("env_vars", [])

        # 也尝试标准命名
        provider_upper = provider.upper().replace("-", "_")
        env_vars = env_vars or [f"{provider_upper}_API_KEY"]

        for env_var in env_vars:
            api_key = os.getenv(env_var)
            if api_key:
                return ProviderCredentials(
                    provider=provider,
                    api_key=api_key,
                    base_url=profile.get("base_url"),
                )

        return None

    def set_provider_profile(
        self,
        provider: str,
        profile: Dict[str, Any],
    ) -> None:
        """设置 Provider Profile 信息。

        用于环境变量加载时获取 env_vars 和 base_url。

        Args:
            provider: Provider 名称
            profile: Profile 信息
        """
        self._provider_profiles[provider] = profile

    def list_available(self) -> list[str]:
        """列出所有可用的 Provider。

        Returns:
            可用的 Provider 名称列表
        """
        all_providers = set(self._runtime_overrides.keys())
        all_providers.update(self._config_credentials.keys())
        all_providers.update(self._provider_profiles.keys())

        return [p for p in all_providers if self.is_available(p)]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_provider_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add agentforge/profiles/provider_registry.py tests/test_provider_registry.py
git commit -m "feat(profiles): 添加 ProviderRegistry 认证管理

- 支持多来源优先级（运行时 > 配置 > 环境变量）
- 支持配置文件加载
- 支持环境变量自动读取"
```

---

## Task 3: 创建 ProfileRegistry

**Files:**
- Create: `agentforge/profiles/registry.py`
- Create: `tests/test_profile_registry.py`

- [ ] **Step 1: 编写 ProfileRegistry 测试**

创建 `tests/test_profile_registry.py`:

```python
"""ProfileRegistry 单元测试。"""

import pytest
from pathlib import Path
from agentforge.profiles.profile import AgentProfile
from agentforge.profiles.registry import ProfileRegistry
from agentforge.profiles.provider_registry import ProviderRegistry


class TestProfileRegistry:
    """ProfileRegistry 测试。"""

    def test_register_and_get(self):
        """测试注册和获取 Profile。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(name="test", provider="openai")
        registry.register(profile)

        result = registry.get("test")
        assert result is not None
        assert result.name == "test"

    def test_get_nonexistent(self):
        """测试获取不存在的 Profile。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        result = registry.get("nonexistent")
        assert result is None

    def test_inheritance_resolution(self):
        """测试继承解析。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        # 父 Profile
        parent = AgentProfile(
            name="base",
            provider="deepseek",
            model="deepseek-reasoner",
            temperature=0.3,
        )
        registry.register(parent)

        # 子 Profile
        child = AgentProfile(
            name="security-reviewer",
            extends="base",
            system_prompt="你是安全工程师...",
        )
        registry.register(child)

        # 获取子 Profile（应自动解析继承）
        result = registry.get("security-reviewer")
        assert result is not None
        assert result.provider == "deepseek"  # 从父 Profile 继承
        assert result.model == "deepseek-reasoner"  # 从父 Profile 继承
        assert result.system_prompt == "你是安全工程师..."  # 自身配置

    def test_validate_profiles(self):
        """测试 Profile 验证。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        # 有效 Profile
        valid = AgentProfile(name="valid", provider="openai")
        registry.register(valid)

        # 无效 Profile（空名称）
        invalid = AgentProfile(name="", provider="test")
        registry.register(invalid)

        results = registry.validate()

        assert results["valid"] == ([], [])  # 无错误无警告
        assert len(results[""][0]) > 0  # 有错误

    def test_reload(self):
        """测试热重载。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(name="test", provider="openai")
        registry.register(profile)

        # 确认存在
        assert registry.get("test") is not None

        # 重载
        registry.reload("test")

        # 重载后应从缓存清除
        # （实际文件加载需要配置 config_paths）
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_profile_registry.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 实现 ProfileRegistry**

创建 `agentforge/profiles/registry.py`:

```python
"""Profile 注册表。

支持懒加载、缓存、继承解析和热重载。
"""

from __future__ import annotations

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

        except Exception as e:
            logger.error(f"加载 Profile 配置失败: {path}, 错误: {e}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_profile_registry.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add agentforge/profiles/registry.py tests/test_profile_registry.py
git commit -m "feat(profiles): 添加 ProfileRegistry 注册表

- 支持懒加载和缓存
- 支持 Profile 继承解析
- 支持热重载
- 支持配置验证"
```

---

## Task 4: 扩展 TaskSpec

**Files:**
- Modify: `agentforge/delegation/config.py`
- Modify: `tests/test_p5_delegation.py`

- [ ] **Step 1: 编写 TaskSpec 扩展测试**

在 `tests/test_p5_delegation.py` 中添加测试类：

```python
class TestTaskSpecProfile:
    """TaskSpec Profile 相关测试。"""

    def test_task_spec_with_profile(self):
        """测试带 Profile 的 TaskSpec。"""
        spec = TaskSpec(
            goal="审查代码",
            agent_profile="security-reviewer",
        )

        assert spec.agent_profile == "security-reviewer"
        assert spec.to_dict()["agent_profile"] == "security-reviewer"

    def test_task_spec_with_overrides(self):
        """测试带覆盖参数的 TaskSpec。"""
        spec = TaskSpec(
            goal="测试",
            agent_profile="test-profile",
            temperature=0.5,
            max_tokens=2048,
            system_prompt="额外提示",
        )

        assert spec.temperature == 0.5
        assert spec.max_tokens == 2048
        assert spec.system_prompt == "额外提示"

    def test_task_spec_to_dict_with_new_fields(self):
        """测试新字段序列化。"""
        spec = TaskSpec(
            goal="测试",
            agent_profile="test",
            temperature=0.7,
            max_tokens=1000,
            system_prompt="提示",
        )

        result = spec.to_dict()

        assert result["agent_profile"] == "test"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 1000
        assert result["system_prompt"] == "提示"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_p5_delegation.py::TestTaskSpecProfile -v`
Expected: FAIL with "TypeError: __init__() got an unexpected keyword argument 'agent_profile'"

- [ ] **Step 3: 扩展 TaskSpec 数据类**

修改 `agentforge/delegation/config.py` 中的 TaskSpec：

```python
@dataclass
class TaskSpec:
    """任务规格。

    定义单个委托任务的参数。

    属性：
        goal: 任务目标
        context: 任务上下文（可选）
        toolsets: 工具集列表（可选）
        role: 角色（leaf 或 orchestrator）
        model: 模型名称（可选）
        agent_profile: Profile 名称（可选）
        temperature: 运行时温度覆盖（可选）
        max_tokens: 运行时 max_tokens 覆盖（可选）
        system_prompt: 追加到 Profile 的 system_prompt（可选）
    """

    goal: str
    context: Optional[str] = None
    toolsets: Optional[List[str]] = None
    role: str = "leaf"
    model: Optional[str] = None

    # Profile 相关字段
    agent_profile: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        result = {
            "goal": self.goal,
            "context": self.context,
            "toolsets": self.toolsets,
            "role": self.role,
            "model": self.model,
        }

        # 添加 Profile 相关字段
        if self.agent_profile:
            result["agent_profile"] = self.agent_profile
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens
        if self.system_prompt:
            result["system_prompt"] = self.system_prompt

        return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_p5_delegation.py::TestTaskSpecProfile -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add agentforge/delegation/config.py tests/test_p5_delegation.py
git commit -m "feat(delegation): 扩展 TaskSpec 支持 Profile

- 添加 agent_profile 字段
- 添加 temperature/max_tokens/system_prompt 覆盖字段"
```

---

## Task 5: 扩展 EventType

**Files:**
- Modify: `agentforge/events/types.py`

- [ ] **Step 1: 添加 Profile 相关事件类型**

修改 `agentforge/events/types.py`，在 EventType 枚举中添加：

```python
    # 记忆系统
    MEMORY_PREFETCH = "memory.prefetch"
    MEMORY_PREFETCH_DONE = "memory.prefetch_done"
    MEMORY_SYNC = "memory.sync"
    MEMORY_SYNC_DONE = "memory.sync_done"

    # Profile 系统
    PROFILE_LOADED = "profile.loaded"
    PROFILE_INVALID = "profile.invalid"
    PROFILE_RELOADED = "profile.reloaded"
```

- [ ] **Step 2: 提交**

```bash
git add agentforge/events/types.py
git commit -m "feat(events): 添加 Profile 相关事件类型"
```

---

## Task 6: 更新 profiles 模块导出

**Files:**
- Modify: `agentforge/profiles/__init__.py`

- [ ] **Step 1: 更新 __init__.py 导出**

修改 `agentforge/profiles/__init__.py`：

```python
"""Profile 系统模块。

提供专家 Agent 的声明式配置管理。
"""

from agentforge.profiles.profile import AgentProfile
from agentforge.profiles.provider_registry import (
    ProviderCredentials,
    ProviderRegistry,
)
from agentforge.profiles.registry import ProfileRegistry

__all__ = [
    "AgentProfile",
    "ProviderCredentials",
    "ProviderRegistry",
    "ProfileRegistry",
]
```

- [ ] **Step 2: 提交**

```bash
git add agentforge/profiles/__init__.py
git commit -m "feat(profiles): 导出模块公共 API"
```

---

## Task 7: 扩展 DelegationManager

**Files:**
- Modify: `agentforge/delegation/manager.py`
- Create: `tests/test_profile_delegation.py`

- [ ] **Step 1: 编写 DelegationManager Profile 集成测试**

创建 `tests/test_profile_delegation.py`:

```python
"""Profile 委托集成测试。"""

import pytest
from agentforge.delegation import DelegationManager, DelegationConfig
from agentforge.delegation.config import TaskSpec
from agentforge.profiles import AgentProfile, ProfileRegistry, ProviderRegistry


class TestProfileDelegation:
    """Profile 委托集成测试。"""

    def test_resolve_profile(self):
        """测试 Profile 解析。"""
        provider_registry = ProviderRegistry()
        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(
            name="test-profile",
            provider="openai",
            model="gpt-4",
            temperature=0.5,
        )
        profile_registry.register(profile)

        manager = DelegationManager(
            config=DelegationConfig(),
            profile_registry=profile_registry,
            provider_registry=provider_registry,
        )

        # 模拟父 Agent
        class MockAgent:
            _provider = type("MockProvider", (), {"name": "default"})()
            _settings = type("MockSettings", (), {"model": "default-model", "temperature": 1.0})()

        manager._parent_agent = MockAgent()

        result = manager._resolve_profile("test-profile", TaskSpec(goal="test"))

        assert result is not None
        assert result.name == "test-profile"
        assert result.provider == "openai"

    def test_resolve_nonexistent_profile(self):
        """测试解析不存在的 Profile。"""
        provider_registry = ProviderRegistry()
        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        manager = DelegationManager(
            config=DelegationConfig(),
            profile_registry=profile_registry,
            provider_registry=provider_registry,
        )

        result = manager._resolve_profile("nonexistent", TaskSpec(goal="test"))

        assert result is None

    def test_resolve_child_config_with_profile(self):
        """测试使用 Profile 解析子 Agent 配置。"""
        provider_registry = ProviderRegistry()
        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(
            name="test",
            provider="anthropic",
            model="claude-3-opus",
            temperature=0.3,
            max_tokens=2048,
        )
        profile_registry.register(profile)

        manager = DelegationManager(
            config=DelegationConfig(),
            profile_registry=profile_registry,
            provider_registry=provider_registry,
        )

        task = TaskSpec(
            goal="测试任务",
            agent_profile="test",
        )

        # 模拟父 Agent
        class MockAgent:
            _provider = type("MockProvider", (), {"name": "openai"})()
            _settings = type(
                "MockSettings",
                (),
                {"model": "gpt-4", "temperature": 1.0, "max_tokens": 4096},
            )()

        manager._parent_agent = MockAgent()

        profile = manager._resolve_profile("test", task)
        # 验证 Profile 配置
        assert profile.provider == "anthropic"
        assert profile.model == "claude-3-opus"
        assert profile.temperature == 0.3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_profile_delegation.py -v`
Expected: FAIL with "TypeError: __init__() got an unexpected keyword argument"

- [ ] **Step 3: 扩展 DelegationManager 构造函数**

在 `agentforge/delegation/manager.py` 的 `DelegationManager.__init__` 中添加参数：

找到 `__init__` 方法（约第 61 行），添加新参数：

```python
    def __init__(
        self,
        config: Optional[DelegationConfig] = None,
        parent_agent: Optional["Agent"] = None,
        event_dispatcher: Optional[Any] = None,
        profile_registry: Optional["ProfileRegistry"] = None,      # 新增
        provider_registry: Optional["ProviderRegistry"] = None,    # 新增
    ):
        """初始化委托管理器。

        Args:
            config: 委托配置
            parent_agent: 父 Agent
            event_dispatcher: 事件分发器
            profile_registry: Profile 注册表
            provider_registry: Provider 注册表
        """
        self._config = config or DelegationConfig()
        self._parent_agent = parent_agent
        self._event_dispatcher = event_dispatcher
        self._profile_registry = profile_registry              # 新增
        self._provider_registry = provider_registry            # 新增

        # 活跃子 Agent 注册表
        self._active_children: Dict[str, Any] = {}
        self._active_children_lock = threading.Lock()

        # 暂停标志
        self._spawn_paused = False
        self._spawn_paused_lock = threading.Lock()
```

同时在文件顶部添加类型导入：

```python
if TYPE_CHECKING:
    from agentforge.agent import Agent
    from agentforge.config import Settings
    from agentforge.providers import Provider
    from agentforge.profiles import ProfileRegistry, ProviderRegistry  # 新增
```

- [ ] **Step 4: 实现 _resolve_profile 方法**

在 `DelegationManager` 类中添加方法（在 `_build_child_prompt` 方法之后）：

```python
    def _resolve_profile(
        self,
        profile_name: str,
        task: TaskSpec,
    ) -> Optional[AgentProfile]:
        """解析并验证 Profile。

        Args:
            profile_name: Profile 名称
            task: 任务规格

        Returns:
            解析后的 Profile，如果无效则返回 None
        """
        if self._profile_registry is None:
            logger.debug("ProfileRegistry 未配置")
            return None

        profile = self._profile_registry.get(profile_name)
        if profile is None:
            logger.warning(f"Profile '{profile_name}' 不存在")
            self._emit_event(EventType.PROFILE_INVALID, {
                "profile": profile_name,
                "errors": ["Profile 不存在"],
            })
            return None

        # 验证 Profile
        errors, warnings = profile.validate(self._provider_registry)
        if errors:
            logger.error(f"Profile '{profile_name}' 验证失败: {errors}")
            self._emit_event(EventType.PROFILE_INVALID, {
                "profile": profile_name,
                "errors": errors,
                "warnings": warnings,
            })
            return None

        if warnings:
            logger.warning(f"Profile '{profile_name}' 警告: {warnings}")

        # 发射加载事件
        self._emit_event(EventType.PROFILE_LOADED, {
            "profile": profile_name,
            "provider": profile.provider,
            "model": profile.model,
        })

        return profile
```

- [ ] **Step 5: 实现 _resolve_child_config 方法**

在 `_resolve_profile` 方法之后添加：

```python
    def _resolve_child_config(
        self,
        task: TaskSpec,
        profile: Optional[AgentProfile],
        system_prompt: str,
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """解析子 Agent 的最终配置。

        优先级：task 覆盖 > Profile 配置 > 父 Agent 回退

        Args:
            task: 任务规格
            profile: Profile 对象（可选）
            system_prompt: 基础系统提示

        Returns:
            (provider_name, model, settings_dict)
        """
        # 默认从父 Agent 获取
        parent_provider = getattr(
            getattr(self._parent_agent, "_provider", None),
            "name",
            None
        )
        parent_model = getattr(self._parent_agent, "_settings", None)
        parent_model = getattr(parent_model, "model", None) if parent_model else None
        parent_temp = getattr(self._parent_agent, "_settings", None)
        parent_temp = getattr(parent_temp, "temperature", 1.0) if parent_temp else 1.0
        parent_tokens = getattr(self._parent_agent, "_settings", None)
        parent_tokens = getattr(parent_tokens, "max_tokens", 4096) if parent_tokens else 4096

        # Provider: task > profile > 父 Agent
        provider_name = None
        if profile and profile.provider:
            if self._provider_registry and self._provider_registry.is_available(profile.provider):
                provider_name = profile.provider
        if provider_name is None:
            provider_name = parent_provider

        # Model: task > profile > 父 Agent
        model = task.model
        if model is None and profile:
            model = profile.model
        if model is None:
            model = parent_model

        # Temperature: task > profile > 父 Agent
        temperature = task.temperature
        if temperature is None and profile:
            temperature = profile.temperature
        if temperature is None:
            temperature = parent_temp

        # Max tokens: task > profile > 父 Agent
        max_tokens = task.max_tokens
        if max_tokens is None and profile:
            max_tokens = profile.max_tokens
        if max_tokens is None:
            max_tokens = parent_tokens

        # System prompt: base + profile + task append
        final_prompt = system_prompt
        if profile and profile.system_prompt:
            final_prompt = f"{system_prompt}\n\n{profile.system_prompt}"
        if task.system_prompt:
            final_prompt = f"{final_prompt}\n\n{task.system_prompt}"

        settings_dict = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system_prompt": final_prompt,
        }

        return provider_name, model, settings_dict
```

- [ ] **Step 6: 更新导入**

在文件顶部添加必要的导入：

```python
from agentforge.delegation.config import DelegationConfig, IsolationConfig, TaskSpec
from agentforge.delegation.result import (
    DelegationResult,
    DelegationStatus,
    DelegationStrategy,
    ExitReason,
    TaskResult,
)
from agentforge.events import EventType
from agentforge.interrupt import InterruptToken
from agentforge.types import NormalizedResponse

# 新增
from agentforge.profiles.profile import AgentProfile
```

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest tests/test_profile_delegation.py -v`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add agentforge/delegation/manager.py tests/test_profile_delegation.py
git commit -m "feat(delegation): 集成 Profile 解析到 DelegationManager

- 添加 profile_registry 和 provider_registry 参数
- 实现 _resolve_profile 方法
- 实现 _resolve_child_config 方法
- 支持配置优先级：task > profile > 父 Agent"
```

---

## Task 8: 扩展 Agent 类

**Files:**
- Modify: `agentforge/agent.py`

- [ ] **Step 1: 添加 profile_registry 和 provider_registry 参数**

在 `Agent.__init__` 方法中添加参数（约第 95 行）：

找到 `__init__` 方法的参数列表，添加新参数：

```python
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        provider: Optional["Provider"] = None,
        settings: Optional[Settings] = None,
        tools: Optional[List[Union[Tool, Callable]]] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        fallback_chain: Optional[FallbackChain] = None,
        memory_manager: Optional["MemoryManager"] = None,
        skill_registry: Optional["SkillRegistry"] = None,
        session_provider: Optional["SessionProvider"] = None,
        session_id: Optional[str] = None,
        profile_registry: Optional["ProfileRegistry"] = None,      # 新增
        provider_registry: Optional["ProviderRegistry"] = None,    # 新增
    ):
```

在方法文档字符串中添加说明：

```python
        Args:
            model: 模型名称（简化方式）
            api_key: API 密钥（简化方式）
            provider: Provider 实例（完整方式）
            settings: 配置对象（可选）
            tools: 工具列表（可选）
            approval_callback: 审批回调（可选）
            fallback_chain: 回退链（可选）
            memory_manager: 记忆管理器（可选）
            skill_registry: 技能注册表（可选）
            session_provider: 会话提供者（可选，用于持久化）
            session_id: 会话 ID（可选，用于恢复会话）
            profile_registry: Profile 注册表（可选，用于专家 Agent）  # 新增
            provider_registry: Provider 注册表（可选，用于专家 Agent）  # 新增
```

在方法体中存储新参数（在 `_delegation_manager` 初始化之后）：

```python
        # 委托管理器
        self._delegation_manager = DelegationManager(
            config=self._settings.delegation,
            parent_agent=self,
            event_dispatcher=self._event_dispatcher,
            profile_registry=profile_registry,      # 新增
            provider_registry=provider_registry,    # 新增
        )

        # 存储 Profile 相关引用
        self._profile_registry = profile_registry
        self._provider_registry = provider_registry
```

同时在 `TYPE_CHECKING` 块中添加导入：

```python
if TYPE_CHECKING:
    from agentforge.providers import Provider
    from agentforge.memory import MemoryManager, MemoryProvider
    from agentforge.skills import Skill, SkillRegistry
    from agentforge.profiles import ProfileRegistry, ProviderRegistry  # 新增
```

- [ ] **Step 2: 添加 validate_profiles 方法**

在 `Agent` 类中添加公共方法：

```python
    def validate_profiles(self) -> Dict[str, Tuple[List[str], List[str]]]:
        """验证所有 Profile 的健康状态。

        Returns:
            {profile_name: (errors, warnings)}
        """
        if self._profile_registry is None:
            return {}
        return self._profile_registry.validate()
```

- [ ] **Step 3: 提交**

```bash
git add agentforge/agent.py
git commit -m "feat(agent): 支持 Profile 注册表参数

- 添加 profile_registry 和 provider_registry 参数
- 传递给 DelegationManager
- 添加 validate_profiles 方法"
```

---

## Task 9: 更新主模块导出

**Files:**
- Modify: `agentforge/__init__.py`

- [ ] **Step 1: 导出 profiles 模块**

在 `agentforge/__init__.py` 中添加导出：

在导入部分添加：

```python
# Profile 系统
from agentforge.profiles import (
    AgentProfile,
    ProviderCredentials,
    ProviderRegistry,
    ProfileRegistry,
)
```

在 `__all__` 列表中添加：

```python
    # Profile 系统
    "AgentProfile",
    "ProviderCredentials",
    "ProviderRegistry",
    "ProfileRegistry",
```

- [ ] **Step 2: 运行完整测试确认无回归**

Run: `pytest tests/ -v --tb=short`
Expected: PASS (所有测试)

- [ ] **Step 3: 提交**

```bash
git add agentforge/__init__.py
git commit -m "feat: 导出 profiles 模块到公共 API"
```

---

## Task 10: 编写用户文档

**Files:**
- Create: `docs/user-guide/profiles.md`

- [ ] **Step 1: 编写 profiles.md 文档**

创建 `docs/user-guide/profiles.md`:

```markdown
# Profile 系统指南

Profile 系统允许你定义具有不同能力的专家 Agent，并在运行时动态调度它们。

## 快速开始

### 1. 定义 Profile

创建 `profiles.yaml` 文件：

\`\`\`yaml
security-reviewer:
  description: "代码安全审查专家"
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.3
  toolsets: [read, terminal]
  system_prompt: |
    你是一位资深安全工程师，专注于代码安全审查。

test-writer:
  description: "测试编写专家"
  provider: openai
  model: gpt-4o
  temperature: 0.5
  toolsets: [read, write, terminal]
  system_prompt: |
    你是一位测试工程师，专注于编写高质量的测试代码。
\`\`\`

### 2. 配置 Provider 凭证

创建 `providers.yaml` 文件：

\`\`\`yaml
providers:
  openai:
    api_key: \${OPENAI_API_KEY}
  
  deepseek:
    api_key: \${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1
\`\`\`

### 3. 使用 Profile

\`\`\`python
from agentforge import Agent
from agentforge.profiles import ProfileRegistry, ProviderRegistry

# 初始化
provider_registry = ProviderRegistry()
provider_registry.load_from_config("providers.yaml")

profile_registry = ProfileRegistry(
    provider_registry=provider_registry,
    config_paths=["profiles.yaml"],
)

# 创建 Agent
agent = Agent(
    model="gpt-4o",
    profile_registry=profile_registry,
    provider_registry=provider_registry,
)

# 运行（LLM 自动选择专家）
agent.run("请审查 auth.py 的安全性")
\`\`\`

## Profile 继承

使用 `extends` 字段实现配置复用：

\`\`\`yaml
_base-reasoner:
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.3
  toolsets: [read, terminal]

security-reviewer:
  extends: _base-reasoner
  description: "安全审查专家"
  system_prompt: "你是安全工程师..."

performance-analyzer:
  extends: _base-reasoner
  description: "性能分析专家"
  system_prompt: "你是性能专家..."
\`\`\`

## 运行时覆盖

在委托时可以覆盖 Profile 配置：

\`\`\`python
# 通过 TaskSpec 覆盖
result = delegation_manager.delegate(
    goal="审查代码",
    agent_profile="security-reviewer",
    temperature=0.1,  # 覆盖 Profile 的 temperature
    system_prompt="重点关注 SQL 注入",  # 追加到 Profile 的 system_prompt
)
\`\`\`

## 配置优先级

配置按以下优先级合并（高优先级覆盖低优先级）：

1. TaskSpec 参数（运行时覆盖）
2. Profile 配置
3. 父 Agent 配置（回退）

## API 参考

### AgentProfile

\`\`\`python
@dataclass
class AgentProfile:
    name: str                    # Profile 名称
    description: str = ""        # 描述
    extends: Optional[str] = None # 继承的父 Profile
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    toolsets: Optional[List[str]] = None
    blocked_tools: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    inherit_memory: bool = False
    inherit_tools: bool = True
    enabled: bool = True
\`\`\`

### ProfileRegistry

\`\`\`python
class ProfileRegistry:
    def register(profile: AgentProfile) -> None
    def get(name: str) -> Optional[AgentProfile]
    def reload(name: Optional[str] = None) -> None
    def validate(name: Optional[str] = None) -> Dict[str, Tuple[List[str], List[str]]]
    def list_profiles() -> List[str]
\`\`\`

### ProviderRegistry

\`\`\`python
class ProviderRegistry:
    def register(provider: str, credentials: ProviderCredentials, override: bool = False) -> None
    def get_credentials(provider: str) -> Optional[ProviderCredentials]
    def is_available(provider: str) -> bool
    def load_from_config(path: Path) -> None
\`\`\`
\`\`\`

- [ ] **Step 2: 提交**

```bash
git add docs/user-guide/profiles.md
git commit -m "docs: 添加 Profile 系统用户指南"
```

---

## 验证

### 单元测试

\`\`\`bash
pytest tests/test_agent_profile.py tests/test_provider_registry.py tests/test_profile_registry.py tests/test_profile_delegation.py -v
\`\`\`

### 集成测试

\`\`\`python
# 测试完整的 Profile 流程
from agentforge import Agent
from agentforge.profiles import ProfileRegistry, ProviderRegistry, AgentProfile

# 1. 初始化
provider_registry = ProviderRegistry()
profile_registry = ProfileRegistry(provider_registry=provider_registry)

# 2. 注册 Profile
profile = AgentProfile(
    name="test-profile",
    provider="openai",
    model="gpt-4",
    temperature=0.5,
)
profile_registry.register(profile)

# 3. 创建 Agent
agent = Agent(
    model="gpt-4o",
    profile_registry=profile_registry,
    provider_registry=provider_registry,
)

# 4. 验证 Profile 可用
assert profile_registry.get("test-profile") is not None

# 5. 验证健康状态
results = agent.validate_profiles()
assert results["test-profile"] == ([], [])
\`\`\`

---

## 后续扩展（Phase 2）

- Rate Limiter：Provider 级别的请求限流
- Credential Pool：凭证轮换，支持多 API Key
- Profile 市场：从远程仓库加载 Profile
- Profile 继承链深度限制
