"""文件持久化会话提供者。"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentforge.session.base import SessionProvider
from agentforge.session.info import SessionInfo, MessageRecord

logger = logging.getLogger(__name__)


class FileBasedSessionProvider(SessionProvider):
    """基于文件的会话持久化提供者。

    会话数据以 JSON 文件形式存储在指定目录中。
    支持增量写入和自动备份。

    目录结构：
        base_dir/
        ├── sessions.json          # 会话索引
        ├── {session_id}/
        │   ├── meta.json          # 会话元数据
        │   └── messages.jsonl     # 消息记录（JSONL 格式，支持增量追加）
        └── backups/               # 自动备份目录

    使用示例：
        provider = FileBasedSessionProvider("./sessions")
        session_id = provider.create_session("chat-001", "cli")
        provider.append_message(session_id, "user", "你好")
    """

    def __init__(
        self,
        base_dir: str = "./sessions",
        auto_backup: bool = True,
        backup_interval: int = 10,
    ):
        """初始化文件持久化会话提供者。

        Args:
            base_dir: 基础存储目录
            auto_backup: 是否自动备份
            backup_interval: 备份间隔（操作次数）
        """
        self._base_dir = Path(base_dir)
        self._auto_backup = auto_backup
        self._backup_interval = backup_interval
        self._lock = threading.Lock()
        self._message_id_counter = 0
        self._operation_count = 0
        self._title_index: Dict[str, str] = {}

        # 内存缓存
        self._sessions_cache: Dict[str, SessionInfo] = {}
        self._messages_cache: Dict[str, List[MessageRecord]] = {}

        # 初始化目录结构
        self._init_storage()

    def _init_storage(self) -> None:
        """初始化存储目录结构。"""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        (self._base_dir / "backups").mkdir(exist_ok=True)

        # 加载会话索引
        index_file = self._base_dir / "sessions.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._message_id_counter = data.get("message_id_counter", 0)
                    self._title_index = data.get("title_index", {})
            except (OSError, json.JSONDecodeError, ValueError) as e:
                logger.warning(f"加载会话索引失败: {e}")

    def _save_index(self) -> None:
        """保存会话索引。"""
        index_file = self._base_dir / "sessions.json"
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump({
                    "message_id_counter": self._message_id_counter,
                    "title_index": self._title_index,
                }, f, ensure_ascii=False, indent=2)
        except (OSError, PermissionError) as e:
            logger.error(f"保存会话索引失败: {e}")

    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话目录路径。"""
        return self._base_dir / session_id

    def _load_session_meta(self, session_id: str) -> Optional[SessionInfo]:
        """加载会话元数据。"""
        meta_file = self._get_session_dir(session_id) / "meta.json"
        if not meta_file.exists():
            return None
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return SessionInfo(**data)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"加载会话元数据失败 {session_id}: {e}")
            return None

    def _save_session_meta(self, session: SessionInfo) -> None:
        """保存会话元数据。"""
        session_dir = self._get_session_dir(session.id)
        session_dir.mkdir(exist_ok=True)
        meta_file = session_dir / "meta.json"

        data = {
            "id": session.id,
            "source": session.source,
            "user_id": session.user_id,
            "model": session.model,
            "model_config": session.model_config,
            "system_prompt": session.system_prompt,
            "title": session.title,
            "message_count": session.message_count,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "end_reason": session.end_reason,
            "parent_session_id": session.parent_session_id,
        }

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_messages(self, session_id: str) -> List[MessageRecord]:
        """加载会话消息。"""
        messages_file = self._get_session_dir(session_id) / "messages.jsonl"
        if not messages_file.exists():
            return []

        messages = []
        try:
            with open(messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        messages.append(MessageRecord(**data))
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"加载会话消息失败 {session_id}: {e}")

        return messages

    def _append_message_to_file(self, record: MessageRecord) -> None:
        """追加消息到文件。"""
        session_dir = self._get_session_dir(record.session_id)
        session_dir.mkdir(exist_ok=True)
        messages_file = session_dir / "messages.jsonl"

        data = {
            "id": record.id,
            "session_id": record.session_id,
            "role": record.role,
            "content": record.content,
            "tool_calls": record.tool_calls,
            "tool_call_id": record.tool_call_id,
            "tool_name": record.tool_name,
            "timestamp": record.timestamp,
            "token_count": record.token_count,
            "finish_reason": record.finish_reason,
            "reasoning": record.reasoning,
        }

        with open(messages_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _check_backup(self) -> None:
        """检查是否需要备份。"""
        if not self._auto_backup:
            return

        self._operation_count += 1
        if self._operation_count >= self._backup_interval:
            self._create_backup()
            self._operation_count = 0

    def _create_backup(self) -> None:
        """创建备份。"""
        import shutil
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self._base_dir / "backups" / timestamp

        try:
            # 复制当前状态到备份目录
            shutil.copytree(
                self._base_dir,
                backup_dir,
                ignore=shutil.ignore_patterns("backups*"),
            )
            logger.info(f"创建备份: {backup_dir}")

            # 清理旧备份（保留最近 10 个）
            backups = sorted((self._base_dir / "backups").iterdir())
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    shutil.rmtree(old_backup)
                    logger.debug(f"删除旧备份: {old_backup}")
        except (OSError, PermissionError) as e:
            logger.error(f"创建备份失败: {e}")

    def create_session(
        self,
        session_id: str,
        source: str,
        **kwargs,
    ) -> str:
        """创建新会话。"""
        with self._lock:
            # 创建会话对象
            session = SessionInfo(
                id=session_id,
                source=source,
                **kwargs,
            )

            # 保存到缓存和文件
            self._sessions_cache[session_id] = session
            self._messages_cache[session_id] = []
            self._save_session_meta(session)
            self._save_index()

            logger.debug(f"创建会话: {session_id}")
            return session_id

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息。"""
        with self._lock:
            return self._get_session_unlocked(session_id)

    def _get_session_unlocked(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息（不持有锁）。"""
        # 先查缓存
        if session_id in self._sessions_cache:
            return self._sessions_cache[session_id]

        # 从文件加载
        session = self._load_session_meta(session_id)
        if session:
            self._sessions_cache[session_id] = session

        return session

    def end_session(self, session_id: str, end_reason: str) -> None:
        """结束会话。"""
        with self._lock:
            session = self.get_session(session_id)
            if session:
                session.ended_at = time.time()
                session.end_reason = end_reason
                self._save_session_meta(session)
                self._check_backup()

    def append_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        **kwargs,
    ) -> int:
        """追加消息到会话。"""
        with self._lock:
            self._message_id_counter += 1

            record = MessageRecord(
                id=self._message_id_counter,
                session_id=session_id,
                role=role,
                content=self.encode_content(content),
                **kwargs,
            )

            # 添加到缓存
            if session_id not in self._messages_cache:
                self._messages_cache[session_id] = []
            self._messages_cache[session_id].append(record)

            # 追加到文件
            self._append_message_to_file(record)

            # 更新会话消息计数
            session = self._get_session_unlocked(session_id)
            if session:
                session.message_count += 1
                self._save_session_meta(session)

            # 保存索引
            self._save_index()
            self._check_backup()

            return record.id

    def get_messages(self, session_id: str) -> List[MessageRecord]:
        """获取会话所有消息。"""
        with self._lock:
            return self._get_messages_unlocked(session_id)

    def _get_messages_unlocked(self, session_id: str) -> List[MessageRecord]:
        """获取会话所有消息（不持有锁）。"""
        # 先查缓存
        if session_id in self._messages_cache:
            messages = self._messages_cache[session_id]
        else:
            # 从文件加载
            messages = self._load_messages(session_id)
            self._messages_cache[session_id] = messages

        # 解码内容
        return [
            MessageRecord(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=self.decode_content(m.content),
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
                tool_name=m.tool_name,
                timestamp=m.timestamp,
                token_count=m.token_count,
                finish_reason=m.finish_reason,
                reasoning=m.reasoning,
            )
            for m in messages
        ]

    def set_session_title(self, session_id: str, title: str) -> bool:
        """设置会话标题。"""
        with self._lock:
            session = self._get_session_unlocked(session_id)
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

            # 保存
            self._save_session_meta(session)
            self._save_index()

            return True

    def get_session_by_title(self, title: str) -> Optional[SessionInfo]:
        """通过标题查找会话。"""
        with self._lock:
            session_id = self._title_index.get(title)
            if session_id:
                return self._get_session_unlocked(session_id)
            return None

    def search_messages(
        self,
        query: str,
        session_id: str = None,
        limit: int = 20,
    ) -> List[MessageRecord]:
        """搜索消息内容。"""
        results = []
        query_lower = query.lower()

        with self._lock:
            if session_id:
                sessions_to_search = [session_id]
            else:
                # 获取所有会话
                sessions_to_search = []
                for item in self._base_dir.iterdir():
                    if item.is_dir() and item.name != "backups":
                        sessions_to_search.append(item.name)

            for sid in sessions_to_search:
                messages = self._get_messages_unlocked(sid)
                for msg in messages:
                    content = msg.content
                    if isinstance(content, str) and query_lower in content.lower():
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
        """列出会话。"""
        with self._lock:
            sessions = []

            # 遍历目录获取所有会话
            for item in self._base_dir.iterdir():
                if item.is_dir() and item.name != "backups":
                    session = self._get_session_unlocked(item.name)
                    if session:
                        if source is None or session.source == source:
                            sessions.append(session)

            # 按开始时间排序
            sessions.sort(key=lambda s: s.started_at, reverse=True)
            return sessions[offset:offset + limit]

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息。

        Args:
            session_id: 会话 ID

        Returns:
            是否成功删除
        """
        import shutil

        with self._lock:
            session_dir = self._get_session_dir(session_id)
            if not session_dir.exists():
                return False

            # 清理缓存
            self._sessions_cache.pop(session_id, None)
            self._messages_cache.pop(session_id, None)

            # 清理标题索引
            session = self._load_session_meta(session_id)
            if session and session.title:
                self._title_index.pop(session.title, None)

            # 删除目录
            shutil.rmtree(session_dir)
            self._save_index()

            logger.debug(f"删除会话: {session_id}")
            return True

    def export_session(self, session_id: str, output_path: str) -> bool:
        """导出会话到单个 JSON 文件。

        Args:
            session_id: 会话 ID
            output_path: 输出文件路径

        Returns:
            是否成功导出
        """
        with self._lock:
            session = self._get_session_unlocked(session_id)
            if not session:
                return False

            messages = self._get_messages_unlocked(session_id)

            data = {
                "session": {
                    "id": session.id,
                    "source": session.source,
                    "user_id": session.user_id,
                    "model": session.model,
                    "model_config": session.model_config,
                    "system_prompt": session.system_prompt,
                    "title": session.title,
                    "message_count": session.message_count,
                    "started_at": session.started_at,
                    "ended_at": session.ended_at,
                    "end_reason": session.end_reason,
                    "parent_session_id": session.parent_session_id,
                },
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": self.decode_content(m.content),
                        "tool_calls": m.tool_calls,
                        "tool_call_id": m.tool_call_id,
                        "tool_name": m.tool_name,
                        "timestamp": m.timestamp,
                        "token_count": m.token_count,
                        "finish_reason": m.finish_reason,
                        "reasoning": m.reasoning,
                    }
                    for m in messages
                ],
            }

            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
            except (OSError, PermissionError, TypeError) as e:
                logger.error(f"导出会话失败: {e}")
                return False

    def import_session(self, input_path: str) -> Optional[str]:
        """从 JSON 文件导入会话。

        Args:
            input_path: 输入文件路径

        Returns:
            导入的会话 ID，失败返回 None
        """
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            session_data = data["session"]
            session_id = session_data["id"]

            # 创建会话
            with self._lock:
                session = SessionInfo(**session_data)
                self._sessions_cache[session_id] = session
                self._save_session_meta(session)

                # 导入消息
                messages = []
                for msg_data in data["messages"]:
                    record = MessageRecord(
                        id=msg_data["id"],
                        session_id=session_id,
                        role=msg_data["role"],
                        content=self.encode_content(msg_data["content"]),
                        tool_calls=msg_data.get("tool_calls"),
                        tool_call_id=msg_data.get("tool_call_id"),
                        tool_name=msg_data.get("tool_name"),
                        timestamp=msg_data.get("timestamp", time.time()),
                        token_count=msg_data.get("token_count"),
                        finish_reason=msg_data.get("finish_reason"),
                        reasoning=msg_data.get("reasoning"),
                    )
                    messages.append(record)
                    self._append_message_to_file(record)

                self._messages_cache[session_id] = messages

                if session.title:
                    self._title_index[session.title] = session_id

                self._save_index()

            return session_id
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"导入会话失败: {e}")
            return None

    def shutdown(self) -> None:
        """关闭会话，确保状态已持久化。"""
        pass


__all__ = ["FileBasedSessionProvider"]
