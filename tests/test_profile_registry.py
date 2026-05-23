"""ProfileRegistry 单元测试。"""

import pytest
from pathlib import Path
from hai_agent.profiles.profile import AgentProfile
from hai_agent.profiles.registry import ProfileRegistry
from hai_agent.profiles.provider_registry import ProviderRegistry


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

    def test_inheritance_chain(self):
        """测试多级继承链。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        # 爷爷 Profile
        grandparent = AgentProfile(
            name="root",
            provider="openai",
            model="gpt-4",
            temperature=0.5,
        )
        registry.register(grandparent)

        # 父 Profile
        parent = AgentProfile(
            name="middle",
            extends="root",
            model="gpt-4o",  # 覆盖爷爷的 model
        )
        registry.register(parent)

        # 子 Profile
        child = AgentProfile(
            name="leaf",
            extends="middle",
            temperature=0.1,  # 覆盖爷爷的 temperature
        )
        registry.register(child)

        result = registry.get("leaf")
        assert result is not None
        assert result.provider == "openai"  # 从爷爷继承
        assert result.model == "gpt-4o"  # 从父继承（覆盖爷爷）
        assert result.temperature == 0.1  # 自身配置（覆盖爷爷）

    def test_validate_profiles(self):
        """测试 Profile 验证。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        # 有效 Profile（无 provider）
        valid = AgentProfile(name="valid")
        registry.register(valid)

        # 无效 Profile（空名称）
        invalid = AgentProfile(name="", provider="test")
        registry.register(invalid)

        results = registry.validate()

        assert results["valid"] == ([], [])  # 无错误无警告
        assert len(results[""][0]) > 0  # 有错误

    def test_validate_single_profile(self):
        """测试单个 Profile 验证。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        # 无 provider 的 Profile
        profile = AgentProfile(name="test")
        registry.register(profile)

        # 无凭证时的验证
        results = registry.validate("test")

        # 无 provider 时，不验证 Provider 可用性
        assert results["test"] == ([], [])

    def test_reload_single(self):
        """测试单个 Profile 热重载。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        profile = AgentProfile(name="test", provider="openai")
        registry.register(profile)

        # 确认存在
        assert registry.get("test") is not None

        # 重载
        registry.reload("test")

        # 重载后应从缓存清除
        result = registry.get("test")
        # 由于没有配置文件，重载后不存在
        assert result is None

    def test_reload_all(self):
        """测试全部 Profile 热重载。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        profile1 = AgentProfile(name="test1", provider="openai")
        profile2 = AgentProfile(name="test2", provider="anthropic")
        registry.register(profile1)
        registry.register(profile2)

        # 确认存在
        assert registry.get("test1") is not None
        assert registry.get("test2") is not None

        # 全部重载
        registry.reload()

        # 全部清除
        assert registry.get("test1") is None
        assert registry.get("test2") is None

    def test_list_profiles(self):
        """测试列出所有 Profile。"""
        provider_registry = ProviderRegistry()
        registry = ProfileRegistry(provider_registry=provider_registry)

        profile1 = AgentProfile(name="test1", provider="openai")
        profile2 = AgentProfile(name="test2", provider="anthropic")
        registry.register(profile1)
        registry.register(profile2)

        profiles = registry.list_profiles()

        assert len(profiles) == 2
        assert "test1" in profiles
        assert "test2" in profiles