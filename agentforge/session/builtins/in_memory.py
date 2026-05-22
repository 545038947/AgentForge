"""内存会话提供者。"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from agentforge.session.base import SessionProvider
from agentforge.session.info import SessionInfo, MessageRecord

logger = logging.getLogger(__name__)


class InMemorySessionProvider(SessionProvider):
    """内存会话提供者。

    默认实现，适用于测试和短期会话。
    """

    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._messages: Dict[str, List[MessageRecord]] = {}
        self._title_index: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._message_id_counter = 0

    def create_session(
        self,
        session_id: str,
        source: str,
        **kwargs,
    ) -> str:
        with self._lock:
            session = SessionInfo(
                id=session_id,
                source=source,
                **kwargs,
            )
            self._sessions[session_id] = session
            self._messages[session_id] = []
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        with self._lock:
            return self._sessions.get(session_id)

    def end_session(self, session_id: str, end_reason: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.ended_at = time.time()
                session.end_reason = end_reason

    def append_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        **kwargs,
    ) -> int:
        with self._lock:
            self._message_id_counter += 1
            record = MessageRecord(
                id=self._message_id_counter,
                session_id=session_id,
                role=role,
                content=self.encode_content(content),
                **kwargs,
            )
            self._messages.setdefault(session_id, []).append(record)

            session = self._sessions.get(session_id)
            if session:
                session.message_count += 1

            return record.id

    def get_messages(self, session_id: str) -> List[MessageRecord]:
        with self._lock:
            messages = self._messages.get(session_id, [])
            # 解码内容
            return [
                MessageRecord(
                    **{k: self.decode_content(v) if k == "content" else v
                       for k, v in dataclasses.asdict(m).items()}
                )
                for m in messages
            ]

    def set_session_title(self, session_id: str, title: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            # 检查标题唯一性
            if title in self._title_index and self._title_index[title] != session_id:
                raise ValueError(f"标题 '{title}' 已被其他会话使用")
            # 清除旧标题索引
            if session.title:
                self._title_index.pop(session.title, None)
            session.title = title
            self._title_index[title] = session_id
            return True

    def get_session_by_title(self, title: str) -> Optional[SessionInfo]:
        with self._lock:
            session_id = self._title_index.get(title)
            if session_id:
                return self._sessions.get(session_id)
            return None

    def search_messages(
        self,
        query: str,
        session_id: str = None,
        limit: int = 20,
    ) -> List[MessageRecord]:
        results = []
        with self._lock:
            sessions_to_search = [session_id] if session_id else list(self._messages.keys())
            for sid in sessions_to_search:
                for msg in self._messages.get(sid, []):
                    content = self.decode_content(msg.content)
                    if isinstance(content, str) and query.lower() in content.lower():
                        results.append(msg)
                        if len(results) >= limit:
                            return results
        return results

    def list_sessions(
        self,
        source: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[SessionInfo]:
        with self._lock:
            sessions = list(self._sessions.values())
            if source:
                sessions = [s for s in sessions if s.source == source]
            sessions.sort(key=lambda s: s.started_at, reverse=True)
            return sessions[offset:offset + limit]