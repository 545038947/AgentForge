"""会话管理模块。"""

from agentforge.session.base import SessionProvider
from agentforge.session.info import SessionInfo, MessageRecord
from agentforge.session.builtins.in_memory import InMemorySessionProvider
from agentforge.session.builtins.file_based import FileBasedSessionProvider

__all__ = [
    "SessionProvider",
    "SessionInfo",
    "MessageRecord",
    "InMemorySessionProvider",
    "FileBasedSessionProvider",
]