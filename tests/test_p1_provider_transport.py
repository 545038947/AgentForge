"""P1 阶段单元测试：Provider 与 Transport。"""

import pytest
from unittest.mock import MagicMock, patch

from agentforge.providers.transports.base import (
    Transport,
    register_transport,
    get_transport,
    list_transports,
)
from agentforge.providers.transports.chat_completions import ChatCompletionsTransport
from agentforge.providers.base import Provider, ProviderCapabilities
from agentforge.providers.registry import (
    ProviderRegistry,
    register_provider,
    get_provider,
    list_providers,
    create_provider,
)
from agentforge.types import NormalizedResponse, ToolCall, Usage


class TestTransportBase:
    """Transport 基类测试。"""

    def test_register_and_get_transport(self):
        """测试 Transport 注册和获取。"""
        # ChatCompletionsTransport 已在导入时注册
        transport_class = get_transport("chat_completions")
        assert transport_class is ChatCompletionsTransport

    def test_list_transports(self):
        """测试列出已注册 Transport。"""
        transports = list_transports()
        assert "chat_completions" in transports

    def test_get_nonexistent_transport(self):
        """测试获取不存在的 Transport。"""
        result = get_transport("nonexistent")
        assert result is None


class TestChatCompletionsTransport:
    """ChatCompletionsTransport 测试。"""

    def test_api_mode(self):
        """测试 API 模式标识。"""
        transport = ChatCompletionsTransport()
        assert transport.api_mode == "chat_completions"

    def test_convert_messages_identity(self):
        """测试消息转换（恒等）。"""
        transport = ChatCompletionsTransport()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        converted = transport.convert_messages(messages)
        assert converted == messages

    def test_convert_messages_sanitizes_internal_fields(self):
        """测试消息转换剥离内部字段。"""
        transport = ChatCompletionsTransport()
        messages = [
            {"role": "user", "content": "Hello", "tool_name": "test"},
        ]
        converted = transport.convert_messages(messages)
        assert "tool_name" not in converted[0]

    def test_convert_tools_identity(self):
        """测试工具转换（恒等）。"""
        transport = ChatCompletionsTransport()
        tools = [
            {"type": "function", "function": {"name": "test", "parameters": {}}}
        ]
        converted = transport.convert_tools(tools)
        assert converted == tools

    def test_build_kwargs_basic(self):
        """测试基本 kwargs 构建。"""
        transport = ChatCompletionsTransport()
        kwargs = transport.build_kwargs(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert kwargs["model"] == "gpt-4"
        assert kwargs["messages"] == [{"role": "user", "content": "Hello"}]

    def test_build_kwargs_with_tools(self):
        """测试带工具的 kwargs 构建。"""
        transport = ChatCompletionsTransport()
        tools = [{"type": "function", "function": {"name": "test"}}]
        kwargs = transport.build_kwargs(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
        )
        assert kwargs["tools"] == tools

    def test_build_kwargs_with_params(self):
        """测试带参数的 kwargs 构建。"""
        transport = ChatCompletionsTransport()
        kwargs = transport.build_kwargs(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1000,
            temperature=0.7,
            stream=True,
        )
        assert kwargs["max_tokens"] == 1000
        assert kwargs["temperature"] == 0.7
        assert kwargs["stream"] is True

    def test_normalize_response(self):
        """测试响应标准化。"""
        transport = ChatCompletionsTransport()

        # Mock OpenAI 响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, how can I help?"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30

        normalized = transport.normalize_response(mock_response)

        assert isinstance(normalized, NormalizedResponse)
        assert normalized.content == "Hello, how can I help?"
        assert normalized.finish_reason == "stop"
        assert normalized.usage.prompt_tokens == 10

    def test_normalize_response_with_tool_calls(self):
        """测试带工具调用的响应标准化。"""
        transport = ChatCompletionsTransport()

        # Mock OpenAI 响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].finish_reason = "tool_calls"

        # Mock tool call
        mock_tc = MagicMock()
        mock_tc.id = "call_123"
        mock_tc.function.name = "search"
        mock_tc.function.arguments = '{"query": "test"}'
        mock_response.choices[0].message.tool_calls = [mock_tc]

        normalized = transport.normalize_response(mock_response)

        assert normalized.tool_calls is not None
        assert len(normalized.tool_calls) == 1
        assert normalized.tool_calls[0].id == "call_123"
        assert normalized.tool_calls[0].name == "search"

    def test_validate_response(self):
        """测试响应验证。"""
        transport = ChatCompletionsTransport()

        # 有效响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        assert transport.validate_response(mock_response) is True

        # 无效响应
        assert transport.validate_response(None) is False
        assert transport.validate_response(MagicMock(choices=None)) is False
        assert transport.validate_response(MagicMock(choices=[])) is False


class TestProviderCapabilities:
    """ProviderCapabilities 测试。"""

    def test_default_capabilities(self):
        """测试默认能力。"""
        caps = ProviderCapabilities()
        assert caps.supports_tools is True
        assert caps.supports_streaming is True
        assert caps.supports_vision is False

    def test_supports_method(self):
        """测试 supports 方法。"""
        caps = ProviderCapabilities(supports_vision=True)
        assert caps.supports("vision") is True
        assert caps.supports("reasoning") is False
        assert caps.supports("unknown") is False

    def test_to_dict(self):
        """测试转换为字典。"""
        caps = ProviderCapabilities(supports_tools=True, supports_vision=True)
        d = caps.to_dict()
        assert d["tools"] is True
        assert d["vision"] is True


class TestProviderBase:
    """Provider 基类测试。"""

    def test_provider_subclass(self):
        """测试 Provider 子类实现。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        provider = MockProvider(api_key="test-key")
        assert provider.name == "mock"
        assert provider.transport.api_mode == "chat_completions"

    def test_provider_supports(self):
        """测试 Provider supports 方法。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities(supports_vision=True)

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        provider = MockProvider()
        assert provider.supports("vision") is True
        assert provider.supports("reasoning") is False


class TestProviderRegistry:
    """ProviderRegistry 测试。"""

    def setup_method(self):
        """每个测试前清空注册表。"""
        ProviderRegistry.clear()

    def test_register_and_get(self):
        """测试注册和获取。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        ProviderRegistry.register("mock", MockProvider)
        assert ProviderRegistry.get("mock") is MockProvider

    def test_register_duplicate(self):
        """测试重复注册。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        ProviderRegistry.register("mock", MockProvider)

        with pytest.raises(Exception):  # ConfigurationError
            ProviderRegistry.register("mock", MockProvider)

    def test_get_nonexistent(self):
        """测试获取不存在的 Provider。"""
        with pytest.raises(Exception):  # ConfigurationError
            ProviderRegistry.get("nonexistent")

    def test_list_providers(self):
        """测试列出 Provider。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        ProviderRegistry.register("mock", MockProvider)
        names = ProviderRegistry.list()
        assert "mock" in names

    def test_create_provider(self):
        """测试创建 Provider 实例。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        ProviderRegistry.register("mock", MockProvider)
        provider = ProviderRegistry.create("mock", api_key="test-key")
        assert isinstance(provider, MockProvider)

    def test_register_decorator(self):
        """测试注册装饰器。"""
        @register_provider("decorated")
        class DecoratedProvider(Provider):
            name = "decorated"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        assert ProviderRegistry.get("decorated") is DecoratedProvider


class TestConvenienceFunctions:
    """便捷函数测试。"""

    def setup_method(self):
        """每个测试前清空注册表。"""
        ProviderRegistry.clear()

    def test_get_provider(self):
        """测试 get_provider 函数。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        ProviderRegistry.register("mock", MockProvider)
        assert get_provider("mock") is MockProvider

    def test_list_providers_func(self):
        """测试 list_providers 函数。"""
        class MockProvider(Provider):
            name = "mock"
            capabilities = ProviderCapabilities()

            def _default_transport(self):
                return ChatCompletionsTransport()

            def _create_client(self):
                return MagicMock()

            def _do_stream(self, messages, tools=None, **kwargs):
                yield MagicMock()

        ProviderRegistry.register("mock", MockProvider)
        names = list_providers()
        assert "mock" in names
