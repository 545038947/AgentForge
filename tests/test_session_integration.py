"""SessionProvider 集成测试。"""

import tempfile
import shutil
from unittest.mock import MagicMock

import pytest

from agentforge.agent import Agent
from agentforge.session import (
    SessionProvider,
    InMemorySessionProvider,
    FileBasedSessionProvider,
    SessionInfo,
    MessageRecord,
)
from agentforge.types import NormalizedResponse, Usage


class TestInMemorySessionProvider:
    """测试 InMemorySessionProvider。"""

    def test_create_session(self):
        """测试创建会话。"""
        provider = InMemorySessionProvider()
        session_id = provider.create_session(
            session_id="test-001",
            source="cli",
            model="gpt-4",
        )

        assert session_id == "test-001"

        session = provider.get_session(session_id)
        assert session is not None
        assert session.id == "test-001"
        assert session.source == "cli"
        assert session.model == "gpt-4"

    def test_append_message(self):
        """测试追加消息。"""
        provider = InMemorySessionProvider()
        session_id = provider.create_session("test-001", "cli")

        msg_id = provider.append_message(session_id, "user", "你好")
        assert msg_id > 0

        provider.append_message(session_id, "assistant", "你好！")

        messages = provider.get_messages(session_id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "你好"
        assert messages[1].role == "assistant"

    def test_set_session_title(self):
        """测试设置标题。"""
        provider = InMemorySessionProvider()
        session_id = provider.create_session("test-001", "cli")

        result = provider.set_session_title(session_id, "测试会话")
        assert result is True

        session = provider.get_session(session_id)
        assert session.title == "测试会话"

        # 通过标题查找
        found = provider.get_session_by_title("测试会话")
        assert found is not None
        assert found.id == session_id

    def test_search_messages(self):
        """测试搜索消息。"""
        provider = InMemorySessionProvider()
        session_id = provider.create_session("test-001", "cli")

        provider.append_message(session_id, "user", "Python 教程")
        provider.append_message(session_id, "assistant", "好的，我来介绍 Python")
        provider.append_message(session_id, "user", "JavaScript 教程")

        results = provider.search_messages("Python")
        # "Python 教程" 和 "好的，我来介绍 Python" 都包含 Python
        assert len(results) == 2
        assert "Python" in results[0].content
        assert "Python" in results[1].content

    def test_list_sessions(self):
        """测试列出会话。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-001", "cli")
        provider.create_session("test-002", "telegram")
        provider.create_session("test-003", "cli")

        # 按来源过滤
        cli_sessions = provider.list_sessions(source="cli")
        assert len(cli_sessions) == 2

        all_sessions = provider.list_sessions()
        assert len(all_sessions) == 3

    def test_end_session(self):
        """测试结束会话。"""
        provider = InMemorySessionProvider()
        session_id = provider.create_session("test-001", "cli")

        provider.end_session(session_id, "completed")

        session = provider.get_session(session_id)
        assert session.end_reason == "completed"
        assert session.ended_at is not None


class TestFileBasedSessionProvider:
    """测试 FileBasedSessionProvider。"""

    def test_create_session(self):
        """测试创建会话。"""
        tmpdir = tempfile.mkdtemp()
        try:
            provider = FileBasedSessionProvider(tmpdir, auto_backup=False)
            session_id = provider.create_session(
                session_id="test-001",
                source="cli",
                model="gpt-4",
            )

            assert session_id == "test-001"

            session = provider.get_session(session_id)
            assert session is not None
            assert session.id == "test-001"
            assert session.source == "cli"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_persistence(self):
        """测试数据持久化。"""
        tmpdir = tempfile.mkdtemp()
        try:
            # 创建并写入数据
            provider1 = FileBasedSessionProvider(tmpdir, auto_backup=False)
            session_id = provider1.create_session("test-001", "cli")
            provider1.append_message(session_id, "user", "你好")
            provider1.append_message(session_id, "assistant", "你好！")
            provider1.set_session_title(session_id, "测试会话")

            # 创建新的 provider 读取数据
            provider2 = FileBasedSessionProvider(tmpdir, auto_backup=False)
            session = provider2.get_session(session_id)
            assert session is not None
            assert session.title == "测试会话"
            assert session.message_count == 2

            messages = provider2.get_messages(session_id)
            assert len(messages) == 2
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_delete_session(self):
        """测试删除会话。"""
        tmpdir = tempfile.mkdtemp()
        try:
            provider = FileBasedSessionProvider(tmpdir, auto_backup=False)
            session_id = provider.create_session("test-001", "cli")
            provider.append_message(session_id, "user", "你好")

            result = provider.delete_session(session_id)
            assert result is True

            session = provider.get_session(session_id)
            assert session is None
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_export_import(self):
        """测试导出导入。"""
        tmpdir = tempfile.mkdtemp()
        try:
            provider = FileBasedSessionProvider(tmpdir, auto_backup=False)
            session_id = provider.create_session("test-001", "cli", model="gpt-4")
            provider.append_message(session_id, "user", "你好")
            provider.append_message(session_id, "assistant", "你好！")
            provider.set_session_title(session_id, "导出测试")

            # 导出
            export_path = f"{tmpdir}/export.json"
            result = provider.export_session(session_id, export_path)
            assert result is True

            # 删除原会话
            provider.delete_session(session_id)

            # 导入
            imported_id = provider.import_session(export_path)
            assert imported_id == session_id

            session = provider.get_session(session_id)
            assert session is not None
            assert session.title == "导出测试"

            messages = provider.get_messages(session_id)
            assert len(messages) == 2
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestAgentSessionIntegration:
    """测试 Agent 与 SessionProvider 集成。"""

    def test_agent_with_session_provider(self):
        """测试 Agent 使用 SessionProvider。"""
        # 创建 mock provider
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.capabilities.supports_tools = True
        mock_provider.capabilities.supports_streaming = True
        mock_provider.complete.return_value = NormalizedResponse(
            content="Hello!",
            finish_reason="stop",
        )

        # 创建内存 SessionProvider
        session_provider = InMemorySessionProvider()

        agent = Agent(
            provider=mock_provider,
            session_provider=session_provider,
            session_id="test-session",
        )

        # 验证会话已创建
        session = session_provider.get_session("test-session")
        assert session is not None
        assert session.source == "agentforge"

        # 运行对话
        response = agent.run("你好")
        assert response.content == "Hello!"

        # 验证消息已保存
        messages = session_provider.get_messages("test-session")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "你好"
        assert messages[1].role == "assistant"

    def test_agent_restore_session(self):
        """测试 Agent 恢复会话。"""
        # 创建 mock provider
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.capabilities.supports_tools = True
        mock_provider.capabilities.supports_streaming = True
        mock_provider.complete.return_value = NormalizedResponse(
            content="回答",
            finish_reason="stop",
        )

        # 创建 SessionProvider 并预填充数据
        session_provider = InMemorySessionProvider()
        session_provider.create_session("existing-session", "cli")
        session_provider.append_message("existing-session", "user", "之前的消息")
        session_provider.append_message("existing-session", "assistant", "之前的回答")

        # 创建 Agent 恢复会话
        agent = Agent(
            provider=mock_provider,
            session_provider=session_provider,
            session_id="existing-session",
        )

        # 运行新对话
        response = agent.run("新问题")

        # 验证消息历史
        messages = session_provider.get_messages("existing-session")
        assert len(messages) == 4  # 之前 2 条 + 新 2 条

    def test_agent_session_methods(self):
        """测试 Agent 会话方法。"""
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.capabilities.supports_tools = True
        mock_provider.capabilities.supports_streaming = True
        mock_provider.complete.return_value = NormalizedResponse(
            content="OK",
            finish_reason="stop",
        )

        session_provider = InMemorySessionProvider()

        agent = Agent(
            provider=mock_provider,
            session_provider=session_provider,
            session_id="test-session",
        )

        # 测试 get_session_id
        assert agent.get_session_id() == "test-session"

        # 测试 get_session_info
        info = agent.get_session_info()
        assert info is not None
        assert info.id == "test-session"

        # 测试 set_session_title
        result = agent.set_session_title("新标题")
        assert result is True

        session = session_provider.get_session("test-session")
        assert session.title == "新标题"

    def test_agent_with_file_based_session(self):
        """测试 Agent 使用 FileBasedSessionProvider。"""
        tmpdir = tempfile.mkdtemp()
        try:
            mock_provider = MagicMock()
            mock_provider.name = "mock"
            mock_provider.capabilities.supports_tools = True
            mock_provider.capabilities.supports_streaming = True
            mock_provider.complete.return_value = NormalizedResponse(
                content="响应",
                finish_reason="stop",
            )
            mock_provider._model = "mock-model"  # 设置字符串值

            session_provider = FileBasedSessionProvider(tmpdir, auto_backup=False)

            agent = Agent(
                provider=mock_provider,
                session_provider=session_provider,
                session_id="file-session",
                model="mock-model",  # 明确指定 model
            )

            agent.run("问题1")
            agent.run("问题2")

            # 创建新的 Agent 实例恢复会话
            agent2 = Agent(
                provider=mock_provider,
                session_provider=session_provider,
                session_id="file-session",
                model="mock-model",  # 明确指定 model
            )

            # 验证历史已恢复
            messages = session_provider.get_messages("file-session")
            assert len(messages) == 4  # 2 个 user + 2 个 assistant
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestSessionProviderBaseMethods:
    """测试 SessionProvider 基类方法。"""

    def test_encode_decode_content(self):
        """测试内容编码解码。"""
        # 纯文本
        text = "你好"
        encoded = SessionProvider.encode_content(text)
        decoded = SessionProvider.decode_content(encoded)
        assert decoded == text

        # 多模态内容
        multimodal = [
            {"type": "text", "text": "看这张图"},
            {"type": "image_url", "image_url": {"url": "http://example.com/image.png"}},
        ]
        encoded = SessionProvider.encode_content(multimodal)
        decoded = SessionProvider.decode_content(encoded)
        assert decoded == multimodal

    def test_compression_tip(self):
        """测试压缩链追踪。"""
        provider = InMemorySessionProvider()

        # 创建压缩链
        provider.create_session("session-1", "cli")
        provider.create_session("session-2", "cli", parent_session_id="session-1")

        # 结束父会话（压缩）
        provider.end_session("session-1", "compression")

        tip = provider.get_compression_tip("session-1")
        assert tip == "session-2"

    def test_session_lineage(self):
        """测试会话血统。"""
        provider = InMemorySessionProvider()

        provider.create_session("root", "cli")
        provider.create_session("child", "cli", parent_session_id="root")
        provider.create_session("grandchild", "cli", parent_session_id="child")

        lineage = provider.get_session_lineage("grandchild")
        assert lineage == ["root", "child", "grandchild"]