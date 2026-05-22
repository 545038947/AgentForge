"""Ollama Provider 测试。"""

import pytest
from unittest.mock import MagicMock, patch

from agentforge.providers.builtins.ollama import OllamaProvider, OLLAMA_DEFAULT_BASE_URL
from agentforge.providers.profile import OLLAMA_PROFILE
from agentforge.types import NormalizedResponse


class TestOllamaProvider:
    """测试 Ollama Provider。"""

    def test_create_provider_default(self):
        """测试使用默认参数创建 Provider。"""
        provider = OllamaProvider(model="llama3.2")

        assert provider.name == "ollama"
        assert provider._model == "llama3.2"
        assert provider._base_url == OLLAMA_DEFAULT_BASE_URL

    def test_create_provider_custom_url(self):
        """测试使用自定义 URL 创建 Provider。"""
        provider = OllamaProvider(
            model="gemma4:31b",
            base_url="http://192.168.1.100:11434/v1",
        )

        assert provider._base_url == "http://192.168.1.100:11434/v1"

    def test_create_provider_with_num_ctx(self):
        """测试使用自定义上下文长度。"""
        provider = OllamaProvider(
            model="llama3.2",
            num_ctx=16384,
        )

        assert provider._num_ctx == 16384

    def test_capabilities(self):
        """测试 Provider 能力。"""
        provider = OllamaProvider(model="llama3.2")
        caps = provider.capabilities

        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_parallel_tool_calls is False

    def test_vision_support_detection(self):
        """测试视觉支持检测。"""
        # 支持视觉的模型
        provider_llava = OllamaProvider(model="llava:13b")
        assert provider_llava.capabilities.supports_vision is True

        # 不支持视觉的模型
        provider_llama = OllamaProvider(model="llama3.2")
        assert provider_llama.capabilities.supports_vision is False

    def test_get_server_url(self):
        """测试获取服务器 URL。"""
        provider = OllamaProvider(
            model="llama3.2",
            base_url="http://localhost:11434/v1",
        )

        assert provider._get_server_url() == "http://localhost:11434"

    def test_list_available_models_mock(self):
        """测试列出可用模型（模拟）。"""
        provider = OllamaProvider(model="llama3.2")

        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "models": [
                    {"name": "llama3.2:latest"},
                    {"name": "gemma2:9b"},
                ]
            }

            models = provider.list_available_models()

            assert "llama3.2:latest" in models
            assert "gemma2:9b" in models

    def test_to_dict(self):
        """测试转换为字典。"""
        provider = OllamaProvider(
            model="llama3.2",
            num_ctx=8192,
        )

        result = provider.to_dict()

        assert result["name"] == "ollama"
        assert result["model"] == "llama3.2"
        assert result["num_ctx"] == 8192


class TestOllamaProfile:
    """测试 Ollama Profile。"""

    def test_profile_exists(self):
        """测试 Profile 存在。"""
        assert OLLAMA_PROFILE.name == "ollama"
        assert OLLAMA_PROFILE.base_url == "http://localhost:11434/v1"
        assert OLLAMA_PROFILE.api_mode == "chat_completions"

    def test_profile_no_api_key_required(self):
        """测试 Profile 不需要 API Key。"""
        assert OLLAMA_PROFILE.env_vars == ()

    def test_profile_aliases(self):
        """测试 Profile 别名。"""
        assert "local" in OLLAMA_PROFILE.aliases


class TestOllamaProviderRegistry:
    """测试 Ollama Provider 注册。"""

    def test_provider_registered(self):
        """测试 Provider 已注册。"""
        from agentforge.providers.registry import ProviderRegistry

        assert "ollama" in ProviderRegistry.list()
        assert "local" in ProviderRegistry.list()  # 别名

    def test_create_via_registry(self):
        """测试通过注册表创建 Provider。"""
        from agentforge.providers.registry import ProviderRegistry

        provider = ProviderRegistry.create("ollama", model="llama3.2")
        assert isinstance(provider, OllamaProvider)

    def test_create_via_alias(self):
        """测试通过别名创建 Provider。"""
        from agentforge.providers.registry import ProviderRegistry

        provider = ProviderRegistry.create("local", model="gemma2")
        assert isinstance(provider, OllamaProvider)


class TestOllamaStreamHTTP:
    """测试 Ollama HTTP 流式调用。"""

    def test_stream_http_mock(self):
        """测试 HTTP 流式调用（模拟）。"""
        provider = OllamaProvider(model="llama3.2")
        provider._client = None  # 强制使用 HTTP

        # 模拟 SSE 响应
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}',
            b'data: {"choices": [{"delta": {"content": " world"}, "finish_reason": null}]}',
            b'data: {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]}',
            b'data: [DONE]',
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            messages = [{"role": "user", "content": "Hi"}]
            responses = list(provider.stream(messages))

            # 应该收到多个响应
            assert len(responses) >= 1

    def test_complete_http_mock(self):
        """测试 HTTP 完整调用（模拟）。"""
        provider = OllamaProvider(model="llama3.2")
        provider._client = None

        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}',
            b'data: {"choices": [{"delta": {"content": " world"}, "finish_reason": null}]}',
            b'data: {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]}',
            b'data: [DONE]',
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_response):
            messages = [{"role": "user", "content": "Hi"}]
            response = provider.complete(messages)

            assert isinstance(response, NormalizedResponse)
            assert "Hello world" in response.content
