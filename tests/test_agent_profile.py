"""AgentProfile 单元测试。"""

import pytest
from hai_agent.profiles.profile import AgentProfile


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

    def test_validate_empty_name(self):
        """测试空名称的验证。"""
        profile = AgentProfile(name="")

        errors, warnings = profile.validate(None)

        assert len(errors) > 0
        assert "名称不能为空" in errors[0]

    def test_validate_temperature_range(self):
        """测试温度范围验证。"""
        profile = AgentProfile(
            name="test",
            temperature=3.0,  # 超出范围
        )

        errors, warnings = profile.validate(None)

        assert len(errors) > 0
        assert "temperature" in errors[0]

    def test_validate_reasoning_effort(self):
        """测试 reasoning_effort 验证。"""
        profile = AgentProfile(
            name="test",
            reasoning_effort="invalid",
        )

        errors, warnings = profile.validate(None)

        assert len(errors) > 0
        assert "reasoning_effort" in errors[0]

    def test_merge_with_parent(self):
        """测试与父 Profile 合并。"""
        parent = AgentProfile(
            name="parent",
            provider="deepseek",
            model="deepseek-reasoner",
            temperature=0.3,
            toolsets=["read", "terminal"],
        )

        child = AgentProfile(
            name="child",
            extends="parent",
            system_prompt="你是安全工程师...",
        )

        merged = child._merge(parent)

        assert merged.name == "child"
        assert merged.provider == "deepseek"  # 从父继承
        assert merged.model == "deepseek-reasoner"  # 从父继承
        assert merged.system_prompt == "你是安全工程师..."  # 自身配置

    def test_merge_override_parent(self):
        """测试子 Profile 覆盖父 Profile。"""
        parent = AgentProfile(
            name="parent",
            provider="deepseek",
            model="deepseek-reasoner",
            temperature=0.3,
        )

        child = AgentProfile(
            name="child",
            extends="parent",
            provider="openai",
            temperature=0.7,
        )

        merged = child._merge(parent)

        assert merged.provider == "openai"  # 子覆盖
        assert merged.model == "deepseek-reasoner"  # 从父继承
        assert merged.temperature == 0.7  # 子覆盖
