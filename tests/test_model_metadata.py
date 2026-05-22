"""模型能力系统测试。"""

import pytest

from agentforge.core.model_metadata import (
    ModelCapabilities,
    DefaultModelMetadataProvider,
)


class TestModelCapabilities:
    """ModelCapabilities 测试。"""

    def test_default_capabilities(self):
        """测试默认能力。"""
        caps = ModelCapabilities()

        assert caps.context_length == 128000
        assert caps.supports_tools is True
        assert caps.supports_vision is False

    def test_custom_capabilities(self):
        """测试自定义能力。"""
        caps = ModelCapabilities(
            context_length=200000,
            supports_vision=True,
            supports_reasoning=True,
            reasoning_effort_levels=["low", "medium", "high"],
        )

        assert caps.context_length == 200000
        assert caps.supports_vision is True
        assert "high" in caps.reasoning_effort_levels

    def test_pricing(self):
        """测试价格信息。"""
        caps = ModelCapabilities(
            pricing={
                "input": 0.01,
                "output": 0.03,
            }
        )

        assert caps.pricing is not None
        assert caps.pricing["input"] == 0.01


class TestDefaultModelMetadataProvider:
    """DefaultModelMetadataProvider 测试。"""

    def test_get_gpt4_capabilities(self):
        """测试获取 GPT-4 能力。"""
        provider = DefaultModelMetadataProvider()

        caps = provider.get_model_capabilities("gpt-4")

        assert caps.supports_tools is True
        assert caps.supports_vision is True

    def test_get_claude_capabilities(self):
        """测试获取 Claude 能力。"""
        provider = DefaultModelMetadataProvider()

        caps = provider.get_model_capabilities("claude-opus-4")

        assert caps.context_length == 200000
        assert caps.supports_prompt_caching is True

    def test_get_deepseek_capabilities(self):
        """测试获取 DeepSeek 能力。"""
        provider = DefaultModelMetadataProvider()

        caps = provider.get_model_capabilities("deepseek-v3")

        assert caps.supports_reasoning is True

    def test_estimate_tokens_text(self):
        """测试文本 Token 估算。"""
        provider = DefaultModelMetadataProvider()

        # 100 字符约 25 Token
        tokens = provider.estimate_tokens("a" * 100)

        assert tokens == 25

    def test_estimate_tokens_multimodal(self):
        """测试多模态 Token 估算。"""
        provider = DefaultModelMetadataProvider()

        content = [
            {"type": "text", "text": "hello"},  # ~1 Token
            {"type": "image_url", "image_url": {"url": "..."}},  # ~1600 Token
        ]

        tokens = provider.estimate_tokens(content)

        assert tokens >= 1600

    def test_unknown_model_defaults(self):
        """测试未知模型返回默认值。"""
        provider = DefaultModelMetadataProvider()

        caps = provider.get_model_capabilities("unknown-model-xyz")

        assert caps.context_length == 128000  # 默认值

    def test_prefix_matching(self):
        """测试前缀匹配。"""
        provider = DefaultModelMetadataProvider()

        # gpt-4o-mini 应该匹配 gpt-4o
        caps = provider.get_model_capabilities("gpt-4o-mini")

        assert caps.supports_vision is True

    def test_estimate_tokens_empty(self):
        """测试空内容估算。"""
        provider = DefaultModelMetadataProvider()

        tokens = provider.estimate_tokens("")
        assert tokens == 0

    def test_estimate_tokens_tool_use(self):
        """测试工具调用内容估算。"""
        provider = DefaultModelMetadataProvider()

        content = [
            {"type": "tool_use", "input": {"query": "test query"}},
        ]

        tokens = provider.estimate_tokens(content)
        assert tokens > 0

    def test_estimate_tokens_tool_result(self):
        """测试工具结果内容估算。"""
        provider = DefaultModelMetadataProvider()

        content = [
            {"type": "tool_result", "content": "result content"},
        ]

        tokens = provider.estimate_tokens(content)
        assert tokens > 0