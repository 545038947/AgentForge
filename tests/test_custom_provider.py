"""自定义 Provider 测试。"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

from hai_agent.providers.custom import CustomProvider
from hai_agent.providers.registry import (
    load_custom_providers,
    create_custom_provider,
)
from hai_agent.providers.profile import ProviderProfile, register_profile, get_profile


class TestCustomProvider:
    """CustomProvider 测试。"""

    def test_create_openai_compatible(self):
        """测试创建 OpenAI 兼容的 Provider。"""
        provider = CustomProvider(
            name="my-openai",
            api_mode="chat_completions",
            api_key="test-key",
            base_url="https://api.example.com/v1",
            model="gpt-4",
        )

        assert provider.name == "my-openai"
        assert provider._api_mode == "chat_completions"
        assert provider.capabilities.supports_tools is True

    def test_create_anthropic_compatible(self):
        """测试创建 Anthropic 兼容的 Provider。"""
        provider = CustomProvider(
            name="my-anthropic",
            api_mode="anthropic_messages",
            api_key="test-key",
            base_url="https://api.example.com/anthropic",
        )

        assert provider.name == "my-anthropic"
        assert provider._api_mode == "anthropic_messages"

    def test_from_config(self):
        """测试从配置创建。"""
        config = {
            "name": "openrouter",
            "api_mode": "chat_completions",
            "api_key": "sk-test",
            "base_url": "https://openrouter.ai/api/v1",
            "supports_vision": True,
        }

        provider = CustomProvider.from_config(config)

        assert provider.name == "openrouter"
        assert provider._base_url == "https://openrouter.ai/api/v1"
        assert provider.capabilities.supports_vision is True

    def test_from_profile(self):
        """测试从 Profile 创建。"""
        profile = ProviderProfile(
            name="test-provider",
            api_mode="chat_completions",
            base_url="https://api.test.com/v1",
            supports_tools=True,
            supports_vision=True,
        )

        provider = CustomProvider.from_profile(profile, api_key="test-key")

        assert provider.name == "test-provider"
        assert provider.capabilities.supports_tools is True
        assert provider.capabilities.supports_vision is True

    def test_to_dict(self):
        """测试转换为字典。"""
        provider = CustomProvider(
            name="test",
            api_mode="chat_completions",
            base_url="https://api.test.com/v1",
            model="test-model",
        )

        result = provider.to_dict()

        assert result["name"] == "test"
        assert result["api_mode"] == "chat_completions"
        assert result["model"] == "test-model"


class TestCustomProviderStreaming:
    """CustomProvider 流式测试。"""

    def test_stream_openai_mock(self):
        """测试 OpenAI 兼容流式调用（模拟）。"""
        provider = CustomProvider(
            name="test-openai",
            api_mode="chat_completions",
            api_key="test-key",
            base_url="https://api.test.com/v1",
        )

        # 模拟响应
        @dataclass
        class MockMessage:
            content: str
            tool_calls: list = None

            def __post_init__(self):
                if self.tool_calls is None:
                    self.tool_calls = []

        @dataclass
        class MockChoice:
            message: MockMessage
            finish_reason: str = "stop"

        @dataclass
        class MockChunk:
            choices: list
            usage: dict = None

        mock_chunk = MockChunk(
            choices=[MockChoice(message=MockMessage(content="Hello"))],
        )

        with patch.object(provider, '_do_stream', return_value=iter([mock_chunk])):
            responses = list(provider.stream([{"role": "user", "content": "Hi"}]))
            assert len(responses) >= 1
            assert "Hello" in responses[0].content


class TestLoadCustomProviders:
    """load_custom_providers 测试。"""

    def test_load_from_yaml(self, tmp_path):
        """测试从 YAML 加载自定义 Provider。"""
        yaml_content = """
providers:
  my-provider:
    api_mode: chat_completions
    base_url: https://api.my-provider.com/v1
    env_vars: [MY_PROVIDER_API_KEY]
    supports_tools: true
    supports_vision: false
"""
        config_path = tmp_path / "custom_providers.yaml"
        config_path.write_text(yaml_content)

        with patch.dict("os.environ", {"MY_PROVIDER_API_KEY": "test-key"}):
            providers = load_custom_providers(config_path)

        assert "my-provider" in providers
        assert providers["my-provider"].name == "my-provider"

    def test_load_with_env_var_reference(self, tmp_path):
        """测试环境变量引用。"""
        yaml_content = """
providers:
  env-provider:
    api_mode: chat_completions
    api_key: ${CUSTOM_API_KEY}
    base_url: https://api.custom.com/v1
"""
        config_path = tmp_path / "custom_providers.yaml"
        config_path.write_text(yaml_content)

        with patch.dict("os.environ", {"CUSTOM_API_KEY": "env-test-key"}):
            providers = load_custom_providers(config_path)

        assert "env-provider" in providers

    def test_load_nonexistent_file(self, tmp_path):
        """测试加载不存在的文件。"""
        result = load_custom_providers(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_load_anthropic_mode(self, tmp_path):
        """测试 Anthropic 模式。"""
        yaml_content = """
providers:
  my-anthropic:
    api_mode: anthropic_messages
    base_url: https://my-anthropic-proxy.example.com
    env_vars: [MY_ANTHROPIC_KEY]
"""
        config_path = tmp_path / "custom_providers.yaml"
        config_path.write_text(yaml_content)

        with patch.dict("os.environ", {"MY_ANTHROPIC_KEY": "test-key"}):
            providers = load_custom_providers(config_path)

        assert "my-anthropic" in providers
        assert providers["my-anthropic"]._api_mode == "anthropic_messages"


class TestCreateCustomProvider:
    """create_custom_provider 便捷函数测试。"""

    def test_create_simple(self):
        """测试简单创建。"""
        provider = create_custom_provider(
            name="simple",
            base_url="https://api.simple.com/v1",
        )

        assert provider.name == "simple"
        assert provider._api_mode == "chat_completions"

    def test_create_with_all_options(self):
        """测试完整配置创建。"""
        provider = create_custom_provider(
            name="full",
            api_mode="anthropic_messages",
            api_key="test-key",
            base_url="https://api.full.com",
            supports_vision=True,
            supports_caching=True,
        )

        assert provider.name == "full"
        assert provider.capabilities.supports_vision is True
        assert provider.capabilities.supports_caching is True


class TestProfileRegistration:
    """Profile 注册测试。"""

    def test_profile_registered_on_load(self, tmp_path):
        """测试加载时 Profile 自动注册。"""
        yaml_content = """
providers:
  auto-profile:
    api_mode: chat_completions
    base_url: https://api.auto.com/v1
    env_vars: [AUTO_API_KEY]
"""
        config_path = tmp_path / "custom_providers.yaml"
        config_path.write_text(yaml_content)

        with patch.dict("os.environ", {"AUTO_API_KEY": "test"}):
            load_custom_providers(config_path)

        # 验证 Profile 已注册
        profile = get_profile("auto-profile")
        assert profile is not None
        assert profile.name == "auto-profile"
