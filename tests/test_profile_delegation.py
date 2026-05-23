"""Profile 委托集成测试。"""

import pytest
from hai_agent.delegation import DelegationManager, DelegationConfig
from hai_agent.delegation.config import TaskSpec
from hai_agent.profiles import AgentProfile, ProfileRegistry, ProviderRegistry


class TestProfileDelegation:
    """Profile 委托集成测试。"""

    def test_resolve_profile(self):
        """测试 Profile 解析。"""
        provider_registry = ProviderRegistry()
        # 注册凭证使 Provider 可用
        from hai_agent.profiles.provider_registry import ProviderCredentials
        provider_registry.register("openai", ProviderCredentials(
            provider="openai",
            api_key="test-key",
        ))

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

    def test_resolve_profile_without_provider(self):
        """测试解析无 Provider 配置的 Profile。"""
        provider_registry = ProviderRegistry()
        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        # 无 Provider 配置的 Profile
        profile = AgentProfile(
            name="no-provider-profile",
            temperature=0.5,
        )
        profile_registry.register(profile)

        manager = DelegationManager(
            config=DelegationConfig(),
            profile_registry=profile_registry,
            provider_registry=provider_registry,
        )

        result = manager._resolve_profile("no-provider-profile", TaskSpec(goal="test"))

        assert result is not None
        assert result.name == "no-provider-profile"

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
        # 注册凭证使 Provider 可用
        from hai_agent.profiles.provider_registry import ProviderCredentials
        provider_registry.register("anthropic", ProviderCredentials(
            provider="anthropic",
            api_key="test-key",
        ))

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

        resolved_profile = manager._resolve_profile("test", task)
        provider, model, settings = manager._resolve_child_config(
            task, resolved_profile, "基础提示"
        )

        # 验证 Profile 配置覆盖父 Agent
        assert provider == "anthropic"  # Profile 的 provider
        assert model == "claude-3-opus"  # Profile 的 model
        assert settings["temperature"] == 0.3  # Profile 的 temperature
        assert settings["max_tokens"] == 2048  # Profile 的 max_tokens

    def test_resolve_child_config_with_task_override(self):
        """测试 TaskSpec 覆盖 Profile 配置。"""
        provider_registry = ProviderRegistry()
        # 注册凭证使 provider 可用
        from hai_agent.profiles.provider_registry import ProviderCredentials
        provider_registry.register("anthropic", ProviderCredentials(
            provider="anthropic",
            api_key="test-key",
        ))

        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(
            name="test",
            provider="anthropic",
            model="claude-3-opus",
            temperature=0.3,
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
            temperature=0.7,  # 覆盖 Profile
            max_tokens=1000,
        )

        class MockAgent:
            _provider = type("MockProvider", (), {"name": "openai"})()
            _settings = type("MockSettings", (), {"model": "gpt-4", "temperature": 1.0})()

        manager._parent_agent = MockAgent()

        resolved_profile = manager._resolve_profile("test", task)
        provider, model, settings = manager._resolve_child_config(
            task, resolved_profile, "基础提示"
        )

        # Task 覆盖优先
        assert provider == "anthropic"  # Profile provider 可用
        assert model == "claude-3-opus"
        assert settings["temperature"] == 0.7  # Task 覆盖
        assert settings["max_tokens"] == 1000  # Task 覆盖

    def test_resolve_child_config_fallback_to_parent(self):
        """测试无 Profile 时回退到父 Agent 配置。"""
        provider_registry = ProviderRegistry()
        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        manager = DelegationManager(
            config=DelegationConfig(),
            profile_registry=profile_registry,
            provider_registry=provider_registry,
        )

        task = TaskSpec(goal="测试任务")

        class MockAgent:
            _provider = type("MockProvider", (), {"name": "deepseek"})()
            _settings = type("MockSettings", (), {
                "model": "deepseek-chat",
                "temperature": 0.8,
                "max_tokens": 2048,
            })()

        manager._parent_agent = MockAgent()

        provider, model, settings = manager._resolve_child_config(
            task, None, "基础提示"
        )

        # 回退到父 Agent
        assert provider == "deepseek"
        assert model == "deepseek-chat"
        assert settings["temperature"] == 0.8
        assert settings["max_tokens"] == 2048

    def test_resolve_child_config_system_prompt_append(self):
        """测试系统提示追加。"""
        provider_registry = ProviderRegistry()
        profile_registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(
            name="test",
            system_prompt="Profile 专用提示",
        )
        profile_registry.register(profile)

        manager = DelegationManager(
            config=DelegationConfig(),
            profile_registry=profile_registry,
            provider_registry=provider_registry,
        )

        task = TaskSpec(
            goal="测试",
            agent_profile="test",
            system_prompt="Task 追加提示",
        )

        class MockAgent:
            _provider = type("MockProvider", (), {"name": "test"})()
            _settings = type("MockSettings", (), {})

        manager._parent_agent = MockAgent()

        resolved_profile = manager._resolve_profile("test", task)
        _, _, settings = manager._resolve_child_config(
            task, resolved_profile, "基础提示"
        )

        # 验证提示追加
        assert "基础提示" in settings["system_prompt"]
        assert "Profile 专用提示" in settings["system_prompt"]
        assert "Task 追加提示" in settings["system_prompt"]