"""P0 阶段单元测试。"""

import pytest
from agentforge.types import (
    Message,
    TextContent,
    ImageContent,
    ToolUseContent,
    ToolResultContent,
    NormalizedResponse,
    ToolCall,
    Usage,
    ToolSpec,
    ToolResult,
)
from agentforge.types.errors import (
    AgentForgeError,
    ConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ToolError,
    ToolExecutionError,
    InterruptException,
)
from agentforge.config import Settings, ProviderSettings, SecretManager


class TestMessageTypes:
    """消息类型测试。"""

    def test_text_content(self):
        """测试文本内容块。"""
        content = TextContent(text="Hello")
        assert content.type == "text"
        assert content.text == "Hello"

    def test_image_content_with_url(self):
        """测试图片内容块（URL 格式）。"""
        content = ImageContent(url="https://example.com/image.png")
        assert content.type == "image"
        assert content.url == "https://example.com/image.png"

    def test_image_content_with_base64(self):
        """测试图片内容块（Base64 格式）。"""
        content = ImageContent(base64="iVBORw0KGgo=", media_type="image/png")
        assert content.type == "image"
        assert content.base64 == "iVBORw0KGgo="

    def test_image_content_requires_url_or_base64(self):
        """测试图片内容块必须提供 url 或 base64。"""
        with pytest.raises(ValueError):
            ImageContent()

    def test_tool_use_content(self):
        """测试工具调用内容块。"""
        content = ToolUseContent(id="call_123", name="search", input={"query": "test"})
        assert content.type == "tool_use"
        assert content.id == "call_123"
        assert content.name == "search"

    def test_tool_result_content(self):
        """测试工具结果内容块。"""
        content = ToolResultContent(
            tool_use_id="call_123",
            content="result",
            is_error=False
        )
        assert content.type == "tool_result"
        assert content.tool_use_id == "call_123"

    def test_message_with_text(self):
        """测试纯文本消息。"""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.is_text_only

    def test_message_with_content_blocks(self):
        """测试多模态消息。"""
        msg = Message(
            role="user",
            content=[
                TextContent(text="Look at this"),
                ImageContent(url="https://example.com/image.png")
            ]
        )
        assert msg.role == "user"
        assert not msg.is_text_only
        assert len(msg.content) == 2

    def test_message_invalid_role(self):
        """测试无效角色。"""
        with pytest.raises(ValueError):
            Message(role="invalid", content="test")

    def test_message_to_dict(self):
        """测试消息转字典。"""
        msg = Message(role="user", content="Hello")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"


class TestResponseTypes:
    """响应类型测试。"""

    def test_tool_call(self):
        """测试工具调用。"""
        tc = ToolCall(id="call_123", name="search", arguments='{"query": "test"}')
        assert tc.id == "call_123"
        assert tc.name == "search"
        assert tc.parsed_arguments == {"query": "test"}

    def test_tool_call_function_property(self):
        """测试工具调用的 function 属性（向后兼容）。"""
        tc = ToolCall(id="call_123", name="search", arguments='{}')
        assert tc.function is tc
        assert tc.function.name == "search"

    def test_usage(self):
        """测试 Token 使用统计。"""
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.prompt_tokens == 100
        assert usage.cache_hit_ratio == 0.0

    def test_usage_with_cache(self):
        """测试带缓存的 Token 使用统计。"""
        usage = Usage(prompt_tokens=100, cached_tokens=80)
        assert usage.cache_hit_ratio == 0.8

    def test_normalized_response(self):
        """测试标准化响应。"""
        response = NormalizedResponse(
            content="Hello",
            finish_reason="stop"
        )
        assert response.content == "Hello"
        assert response.is_stopped
        assert not response.has_tool_calls

    def test_normalized_response_with_tool_calls(self):
        """测试带工具调用的响应。"""
        response = NormalizedResponse(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="test", arguments='{}')],
            finish_reason="tool_calls"
        )
        assert response.has_tool_calls
        assert not response.is_stopped


class TestToolTypes:
    """工具类型测试。"""

    def test_tool_spec(self):
        """测试工具规范。"""
        spec = ToolSpec(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }
        )
        assert spec.name == "search"
        assert spec.timeout == 300.0
        assert not spec.requires_approval

    def test_tool_spec_to_openai(self):
        """测试转换为 OpenAI 格式。"""
        spec = ToolSpec(
            name="search",
            description="Search",
            parameters={"type": "object"}
        )
        openai_tool = spec.to_openai_tool()
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "search"

    def test_tool_result(self):
        """测试工具结果。"""
        result = ToolResult(tool_call_id="call_1", content="result")
        assert result.success
        assert not result.is_error

    def test_tool_result_error(self):
        """测试错误工具结果。"""
        result = ToolResult(
            tool_call_id="call_1",
            content="Error occurred",
            is_error=True
        )
        assert not result.success


class TestErrorTypes:
    """错误类型测试。"""

    def test_agent_forge_error(self):
        """测试基础错误。"""
        from agentforge.types.errors import ErrorReason
        error = AgentForgeError("Something went wrong", details={"key": "value"})
        assert error.message == "Something went wrong"
        assert error.details == {"key": "value"}
        assert error.reason == ErrorReason.unknown

    def test_classified_error(self):
        """测试结构化错误分类。"""
        from agentforge.types.errors import ClassifiedError, ErrorReason
        classified = ClassifiedError(
            reason=ErrorReason.rate_limit,
            message="Rate limited",
            status_code=429,
            retryable=True,
        )
        assert classified.is_rate_limit
        assert classified.retryable
        assert classified.status_code == 429

    def test_provider_rate_limit_error(self):
        """测试速率限制错误。"""
        error = ProviderRateLimitError("Rate limited", retry_after=60)
        assert error.retry_after == 60
        assert error.status_code == 429

    def test_tool_execution_error(self):
        """测试工具执行错误。"""
        error = ToolExecutionError(
            "Execution failed",
            tool_name="search",
            tool_call_id="call_1"
        )
        assert error.tool_name == "search"
        assert error.tool_call_id == "call_1"

    def test_interrupt_exception(self):
        """测试中断异常。"""
        error = InterruptException(reason="User cancelled")
        assert error.interrupt_reason == "User cancelled"


class TestConfig:
    """配置测试。"""

    def test_provider_settings(self):
        """测试 Provider 配置。"""
        settings = ProviderSettings(
            api_key="sk-test",
            base_url="https://api.example.com",
            timeout=60.0
        )
        assert settings.timeout == 60.0
        assert settings.max_retries == 3

    def test_provider_settings_invalid_base_url(self):
        """测试无效 base_url。"""
        with pytest.raises(ValueError):
            ProviderSettings(base_url="invalid-url")

    def test_settings(self):
        """测试主配置。"""
        settings = Settings(model="gpt-4")
        assert settings.model == "gpt-4"
        assert settings.max_tokens == 4096
        assert settings.compression.enabled

    def test_settings_from_env(self, monkeypatch):
        """测试从环境变量加载配置。"""
        monkeypatch.setenv("AGENTFORGE_MODEL", "gpt-4")
        monkeypatch.setenv("AGENTFORGE_MAX_TOKENS", "8192")
        monkeypatch.setenv("AGENTFORGE_DEBUG", "true")

        settings = Settings.from_env()
        assert settings.model == "gpt-4"
        assert settings.max_tokens == 8192
        assert settings.debug is True

    def test_settings_get_api_key(self):
        """测试获取 API 密钥。"""
        from pydantic import SecretStr
        settings = Settings(
            model="gpt-4",
            provider=ProviderSettings(api_key=SecretStr("sk-test"))
        )
        assert settings.get_api_key() == "sk-test"


class TestSecretManager:
    """敏感信息管理测试。"""

    def test_set_and_get(self):
        """测试存储和获取。"""
        manager = SecretManager()
        manager.set("api_key", "sk-secret")
        assert manager.get("api_key") == "sk-secret"

    def test_delete(self):
        """测试删除。"""
        manager = SecretManager()
        manager.set("api_key", "sk-secret")
        manager.delete("api_key")
        assert manager.get("api_key") is None

    def test_redact(self):
        """测试脱敏。"""
        manager = SecretManager()
        manager.set("api_key", "sk-secret-key")
        text = "Using sk-secret-key to call API"
        redacted = manager.redact(text)
        assert "sk-secret-key" not in redacted
        assert "[api_key_REDACTED]" in redacted

    def test_redact_dict(self):
        """测试字典脱敏。"""
        manager = SecretManager()
        data = {
            "api_key": "sk-secret",
            "name": "test",
            "nested": {
                "password": "secret123"
            }
        }
        redacted = manager.redact_dict(data)
        assert redacted["api_key"] == "***REDACTED***"
        assert redacted["name"] == "test"
        assert redacted["nested"]["password"] == "***REDACTED***"
