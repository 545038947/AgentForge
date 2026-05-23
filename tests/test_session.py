"""会话管理系统测试。"""

import time

import pytest

from hai_agent.session import (
    SessionProvider,
    SessionInfo,
    MessageRecord,
    InMemorySessionProvider,
)


class TestSessionInfo:
    """SessionInfo 测试。"""

    def test_create_session_info(self):
        """测试创建会话信息。"""
        info = SessionInfo(
            id="session-1",
            source="cli",
        )

        assert info.id == "session-1"
        assert info.source == "cli"
        assert info.message_count == 0

    def test_parent_session(self):
        """测试父会话链接（压缩链）。"""
        info = SessionInfo(
            id="session-2",
            source="cli",
            parent_session_id="session-1",
        )

        assert info.parent_session_id == "session-1"

    def test_to_dict_and_from_dict(self):
        """测试序列化和反序列化。"""
        info = SessionInfo(
            id="session-1",
            source="cli",
            model="gpt-4",
            message_count=5,
        )

        data = info.to_dict()
        assert data["id"] == "session-1"
        assert data["model"] == "gpt-4"

        restored = SessionInfo.from_dict(data)
        assert restored.id == "session-1"
        assert restored.model == "gpt-4"


class TestMessageRecord:
    """MessageRecord 测试。"""

    def test_create_record(self):
        """测试创建消息记录。"""
        record = MessageRecord(
            id=1,
            session_id="session-1",
            role="user",
            content="你好",
        )

        assert record.id == 1
        assert record.role == "user"
        assert record.content == "你好"

    def test_multimodal_content(self):
        """测试多模态内容编码。"""
        content = [
            {"type": "text", "text": "看这张图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        ]

        record = MessageRecord(
            id=1,
            session_id="session-1",
            role="user",
            content=content,
        )

        # 编码后存储
        encoded = SessionProvider.encode_content(content)
        assert encoded.startswith("\x00json:")

        # 解码后恢复
        decoded = SessionProvider.decode_content(encoded)
        assert decoded == content


class TestInMemorySessionProvider:
    """InMemorySessionProvider 测试。"""

    def test_create_session(self):
        """测试创建会话。"""
        provider = InMemorySessionProvider()

        session_id = provider.create_session("test-session", "cli")

        assert session_id == "test-session"
        info = provider.get_session("test-session")
        assert info is not None
        assert info.source == "cli"

    def test_append_and_get_messages(self):
        """测试追加和获取消息。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")

        provider.append_message("test-session", "user", "你好")
        provider.append_message("test-session", "assistant", "你好！")

        messages = provider.get_messages("test-session")

        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_set_and_get_title(self):
        """测试设置和获取标题。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")

        provider.set_session_title("test-session", "测试会话")

        info = provider.get_session("test-session")
        assert info.title == "测试会话"

        # 通过标题查找
        found = provider.get_session_by_title("测试会话")
        assert found is not None
        assert found.id == "test-session"

    def test_end_session(self):
        """测试结束会话。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")

        provider.end_session("test-session", "completed")

        info = provider.get_session("test-session")
        assert info.ended_at is not None
        assert info.end_reason == "completed"

    def test_compression_chain(self):
        """测试压缩链追踪。"""
        provider = InMemorySessionProvider()

        # 创建原始会话
        provider.create_session("session-1", "cli")

        # 创建压缩后的会话
        provider.create_session(
            "session-2",
            "cli",
            parent_session_id="session-1",
        )
        provider.end_session("session-1", "compression")

        # 获取压缩链末端
        tip = provider.get_compression_tip("session-1")
        assert tip == "session-2"

    def test_list_sessions(self):
        """测试列出会话。"""
        provider = InMemorySessionProvider()

        provider.create_session("session-1", "cli")
        provider.create_session("session-2", "telegram")
        provider.create_session("session-3", "cli")

        # 列出所有
        all_sessions = provider.list_sessions()
        assert len(all_sessions) == 3

        # 按来源过滤
        cli_sessions = provider.list_sessions(source="cli")
        assert len(cli_sessions) == 2

    def test_search_messages(self):
        """测试搜索消息。"""
        provider = InMemorySessionProvider()
        provider.create_session("session-1", "cli")

        provider.append_message("session-1", "user", "Python 是一门编程语言")
        provider.append_message("session-1", "assistant", "是的，Python 很流行")
        provider.append_message("session-1", "user", "JavaScript 怎么样？")

        # 搜索
        results = provider.search_messages("Python")
        assert len(results) == 2

    def test_multimodal_message_storage(self):
        """测试多模态消息存储。"""
        provider = InMemorySessionProvider()
        provider.create_session("test-session", "cli")

        # 多模态内容
        content = [
            {"type": "text", "text": "分析这张图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]

        provider.append_message("test-session", "user", content)

        messages = provider.get_messages("test-session")
        assert len(messages) == 1
        # 内容应该被正确解码
        assert messages[0].content == content