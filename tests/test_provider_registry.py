"""ProviderRegistry 单元测试。"""

import os
import pytest
from pathlib import Path
from hai_agent.profiles.provider_registry import (
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

    def test_is_available_no_api_key(self):
        """测试无 API Key 时的可用性。"""
        registry = ProviderRegistry()
        cred = ProviderCredentials(provider="test")  # 无 api_key

        registry.register("test", cred)

        assert registry.is_available("test") is False

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

    def test_load_from_env_standard_naming(self, monkeypatch):
        """测试标准命名环境变量加载。"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-standard")

        registry = ProviderRegistry()
        result = registry._load_from_env("openai")

        assert result is not None
        assert result.api_key == "sk-standard"

    def test_list_available(self):
        """测试列出可用 Provider。"""
        registry = ProviderRegistry()

        cred1 = ProviderCredentials(provider="openai", api_key="sk-1")
        cred2 = ProviderCredentials(provider="anthropic", api_key="sk-2")
        cred3 = ProviderCredentials(provider="test")  # 无 api_key

        registry.register("openai", cred1)
        registry.register("anthropic", cred2)
        registry.register("test", cred3)

        available = registry.list_available()

        assert "openai" in available
        assert "anthropic" in available
        assert "test" not in available
