"""会话管理模块。"""

from hai_agent.session.base import SessionProvider
from hai_agent.session.info import SessionInfo, MessageRecord
from hai_agent.session.builtins.in_memory import InMemorySessionProvider
from hai_agent.session.builtins.file_based import FileBasedSessionProvider

__all__ = [
    "SessionProvider",
    "SessionInfo",
    "MessageRecord",
    "InMemorySessionProvider",
    "FileBasedSessionProvider",
]