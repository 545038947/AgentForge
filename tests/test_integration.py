"""集成测试：验证所有组件协同工作。"""

import pytest

from agentforge import (
    Agent,
    ToolsetDefinition,
    register_toolset,
    InMemorySessionProvider,
    ModelCapabilities,
    DefaultModelMetadataProvider,
    Settings,
)
from agentforge.providers.builtins import OpenAIProvider


class TestIntegration:
    """集成测试。"""

    def test_agent_with_toolsets(self):
        """测试 Agent 使用工具集。"""
        # 注册自定义工具集
        register_toolset("custom", ToolsetDefinition(
            description="自定义工具集",
            tools=["custom_tool"],
        ))

        # 创建 Agent
        provider = OpenAIProvider(api_key="test-key")
        settings = Settings(model="gpt-4")
        agent = Agent(provider=provider, settings=settings)

        # 验证工具集已注册
        from agentforge.tools.toolsets import get_toolset
        toolset = get_toolset("custom")
        assert toolset is not None

    def test_agent_with_session(self):
        """测试 Agent 使用会话管理。"""
        provider = OpenAIProvider(api_key="test-key")
        settings = Settings(model="gpt-4")
        agent = Agent(provider=provider, settings=settings)

        # 添加会话提供者
        session_provider = InMemorySessionProvider()
        agent.add_memory("session", session_provider)

        # 验证可以访问
        assert agent.get_memory("session") is not None

    def test_model_capabilities_integration(self):
        """测试模型能力集成。"""
        meta_provider = DefaultModelMetadataProvider()

        # 获取 GPT-4 能力
        caps = meta_provider.get_model_capabilities("gpt-4")

        assert caps.supports_tools is True
        assert caps.supports_vision is True

        # 估算 Token
        tokens = meta_provider.estimate_tokens("Hello world")
        assert tokens > 0

    def test_activity_tracking_integration(self):
        """测试活动追踪集成。"""
        provider = OpenAIProvider(api_key="test-key")
        settings = Settings(model="gpt-4")
        agent = Agent(provider=provider, settings=settings)

        # 更新活动状态
        agent._touch_activity("集成测试")

        # 获取摘要
        summary = agent.get_activity_summary()

        assert summary["last_activity_desc"] == "集成测试"
        assert "seconds_since_activity" in summary

    def test_session_provider_workflow(self):
        """测试会话提供者工作流。"""
        provider = InMemorySessionProvider()

        # 创建会话
        provider.create_session("test-session", "cli")

        # 添加消息
        provider.append_message("test-session", "user", "你好")
        provider.append_message("test-session", "assistant", "你好！")

        # 获取消息
        messages = provider.get_messages("test-session")
        assert len(messages) == 2

        # 设置标题
        provider.set_session_title("test-session", "测试会话")
        info = provider.get_session("test-session")
        assert info.title == "测试会话"

    def test_toolset_resolution(self):
        """测试工具集解析。"""
        from agentforge.tools.toolsets import resolve_toolset

        # browser 工具集包含 web
        tools = resolve_toolset("browser")

        # 应该包含 browser 和 web 的工具
        assert "browser_navigate" in tools
        assert "web_search" in tools

    def test_event_types_available(self):
        """测试事件类型可用。"""
        from agentforge.events import EventType

        # 验证新事件类型
        assert hasattr(EventType, "AGENT_THINKING")
        assert hasattr(EventType, "TOOL_PROGRESS")
        assert hasattr(EventType, "STREAM_DELTA")
        assert hasattr(EventType, "CLARIFY_REQUEST")

    def test_all_exports_accessible(self):
        """测试所有导出可访问。"""
        from agentforge import (
            # 类型
            Message,
            NormalizedResponse,
            ToolSpec,
            # 配置
            Settings,
            # Agent
            Agent,
            # 工具
            Tool,
            FunctionTool,
            # 事件
            EventType,
            Event,
            # 记忆
            MemoryProvider,
            InMemoryProvider,
            # 技能
            Skill,
            SkillRegistry,
            # 核心功能
            IterationBudget,
            FallbackChain,
            ExecutionEngine,
            CredentialPool,
            # 新增
            ToolsetDefinition,
            SessionProvider,
            ModelCapabilities,
        )

        # 如果导入成功，测试通过
        assert True