"""SessionProvider 抽象基类。"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agentforge.session.info import SessionInfo, MessageRecord

logger = logging.getLogger(__name__)


class SessionProvider(ABC):
    """会话存储提供者抽象基类。

    支持会话持久化、消息历史、压缩链追踪。
    参考 hermes-agent/hermes_state.py 的 SessionDB 实现。
    """

    @abstractmethod
    def create_session(
        self,
        session_id: str,
        source: str,
        **kwargs,
    ) -> str:
        """创建新会话。

        Args:
            session_id: 会话 ID
            source: 来源（cli、telegram、discord 等）

        Returns:
            会话 ID
        """
        ...

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息。

        Args:
            session_id: 会话 ID

        Returns:
            会话信息，不存在则返回 None
        """
        ...

    @abstractmethod
    def end_session(self, session_id: str, end_reason: str) -> None:
        """结束会话。

        Args:
            session_id: 会话 ID
            end_reason: 结束原因
        """
        ...

    @abstractmethod
    def append_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        **kwargs,
    ) -> int:
        """追加消息到会话。

        Args:
            session_id: 会话 ID
            role: 角色（user、assistant）
            content: 消息内容

        Returns:
            消息 ID
        """
        ...

    @abstractmethod
    def get_messages(self, session_id: str) -> List[MessageRecord]:
        """获取会话所有消息。

        Args:
            session_id: 会话 ID

        Returns:
            消息记录列表
        """
        ...

    @abstractmethod
    def set_session_title(self, session_id: str, title: str) -> bool:
        """设置会话标题。

        Args:
            session_id: 会话 ID
            title: 标题

        Returns:
            是否成功
        """
        ...

    @abstractmethod
    def get_session_by_title(self, title: str) -> Optional[SessionInfo]:
        """通过标题查找会话。

        Args:
            title: 标题

        Returns:
            会话信息
        """
        ...

    @abstractmethod
    def search_messages(
        self,
        query: str,
        session_id: str = None,
        limit: int = 20,
    ) -> List[MessageRecord]:
        """搜索消息内容。

        Args:
            query: 搜索查询
            session_id: 限定会话 ID（可选）
            limit: 最大结果数

        Returns:
            匹配的消息记录
        """
        ...

    @abstractmethod
    def list_sessions(
        self,
        source: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[SessionInfo]:
        """列出会话。

        Args:
            source: 限定来源（可选）
            limit: 最大数量
            offset: 偏移量

        Returns:
            会话信息列表
        """
        ...

    # 压缩链追踪
    def get_compression_tip(self, session_id: str) -> str:
        """获取压缩链的最新会话 ID。

        压缩链：parent_session_id 链接的会话序列，
        用于上下文压缩后继续对话。

        Args:
            session_id: 起始会话 ID

        Returns:
            链末端的会话 ID
        """
        current = session_id
        for _ in range(100):  # 防止无限循环
            session = self.get_session(current)
            if not session:
                return current
            # 查找子会话（end_reason='compression'）
            child = self._find_compression_child(current)
            if not child:
                return current
            current = child.id
        return current

    def get_session_lineage(self, session_id: str) -> List[str]:
        """获取会话的血统链（从根到当前）。

        Args:
            session_id: 会话 ID

        Returns:
            会话 ID 列表（从根到当前）
        """
        lineage = [session_id]
        current = session_id
        while True:
            session = self.get_session(current)
            if not session or not session.parent_session_id:
                break
            lineage.append(session.parent_session_id)
            current = session.parent_session_id
        return list(reversed(lineage))

    def _find_compression_child(self, session_id: str) -> Optional[SessionInfo]:
        """查找压缩子会话。

        Args:
            session_id: 父会话 ID

        Returns:
            子会话信息
        """
        # 默认实现：遍历所有会话
        # 子类可以优化此方法
        for session in self.list_sessions(limit=1000):
            if session.parent_session_id == session_id:
                parent = self.get_session(session_id)
                if parent and parent.end_reason == "compression":
                    return session
        return None

    # 消息编码/解码（用于多模态内容持久化）
    _CONTENT_JSON_PREFIX = "\x00json:"

    @staticmethod
    def encode_content(content: Any) -> Any:
        """编码内容用于存储。

        多模态内容（List[ContentBlock]）需要序列化为 JSON。
        使用哨兵前缀区分 JSON 编码内容和纯文本。

        Args:
            content: 原始内容

        Returns:
            编码后的内容
        """
        if content is None or isinstance(content, (str, bytes, int, float)):
            return content
        # 使用 NUL 字节作为哨兵前缀（不会出现在正常文本中）
        return SessionProvider._CONTENT_JSON_PREFIX + json.dumps(content)

    @staticmethod
    def decode_content(content: Any) -> Any:
        """解码存储的内容。

        Args:
            content: 存储的内容

        Returns:
            原始内容
        """
        if isinstance(content, str) and content.startswith(SessionProvider._CONTENT_JSON_PREFIX):
            try:
                return json.loads(content[len(SessionProvider._CONTENT_JSON_PREFIX):])
            except json.JSONDecodeError:
                return content
        return content