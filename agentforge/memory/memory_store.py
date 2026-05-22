"""长期记忆存储。

实现有界的长期记忆存储，支持冻结快照和安全扫描。
参考 hermes-agent/tools/memory_tool.py 的 MemoryStore 实现。
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 记忆威胁模式（用于安全扫描）
_MEMORY_THREAT_PATTERNS = [
    (r'ignore\s+(all\s+)?(previous|prior|above)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'disregard\s+(all|any)\s+(prior|previous)', "ignore_directive"),
    (r'forget\s+(everything|all|previous)', "forget_command"),
    (r'system\s*:\s*you', "system_impersonation"),
    (r'<\|.*?\|>', "special_token"),
    (r'```.*?```', "code_block_injection"),
]

# 条目分隔符
ENTRY_DELIMITER = "\n§\n"

# 默认字符限制
DEFAULT_MEMORY_CHAR_LIMIT = 2200
DEFAULT_USER_CHAR_LIMIT = 1375


class MemoryStore:
    """长期记忆存储。

    实现有界的长期记忆存储，支持：
    - 有界字符限制（MEMORY: 2200 chars, USER: 1375 chars）
    - 冻结快照模式（会话启动时注入，保持 LLM 前缀缓存）
    - 条目分隔符解析
    - 安全扫描（检测注入攻击模式）
    - 原子写入（临时文件 + 原子替换）

    存储格式：
        memories/
        ├── MEMORY.md    # 事实记忆
        └── USER.md      # 用户偏好

    使用示例：
        store = MemoryStore("./memories")
        store.load_from_disk()

        # 获取冻结快照（用于系统提示）
        prompt = store.format_for_system_prompt("memory")

        # 添加新条目
        store.add_entry("memory", "用户喜欢使用 Python")

        # 同步到磁盘
        store.sync_to_disk()
    """

    def __init__(
        self,
        base_path: str = "./memories",
        memory_char_limit: int = DEFAULT_MEMORY_CHAR_LIMIT,
        user_char_limit: int = DEFAULT_USER_CHAR_LIMIT,
        auto_load: bool = True,
    ):
        """初始化记忆存储。

        Args:
            base_path: 存储目录路径
            memory_char_limit: MEMORY 文件字符限制
            user_char_limit: USER 文件字符限制
            auto_load: 是否自动加载现有数据
        """
        self._base_path = Path(base_path)
        self._memory_char_limit = memory_char_limit
        self._user_char_limit = user_char_limit
        self._lock = threading.Lock()

        # 记忆条目
        self._memory_entries: List[str] = []
        self._user_entries: List[str] = []

        # 冻结快照（会话启动时捕获，保持前缀缓存）
        self._system_prompt_snapshot: Dict[str, str] = {
            "memory": "",
            "user": "",
        }

        # 初始化目录
        self._base_path.mkdir(parents=True, exist_ok=True)

        # 自动加载
        if auto_load:
            self.load_from_disk()

    @property
    def memory_entries(self) -> List[str]:
        """获取事实记忆条目。"""
        return self._memory_entries.copy()

    @property
    def user_entries(self) -> List[str]:
        """获取用户偏好条目。"""
        return self._user_entries.copy()

    def load_from_disk(self) -> Tuple[int, int]:
        """从磁盘加载记忆数据。

        加载后会自动捕获冻结快照。

        Returns:
            (memory_count, user_count) 加载的条目数
        """
        memory_file = self._base_path / "MEMORY.md"
        user_file = self._base_path / "USER.md"

        with self._lock:
            # 加载 MEMORY
            self._memory_entries = self._load_file(memory_file)

            # 加载 USER
            self._user_entries = self._load_file(user_file)

            # 捕获冻结快照
            self._capture_snapshot()

            counts = (len(self._memory_entries), len(self._user_entries))
            logger.debug(f"加载记忆: MEMORY {counts[0]} 条, USER {counts[1]} 条")

            return counts

    def _load_file(self, file_path: Path) -> List[str]:
        """加载单个记忆文件。

        Args:
            file_path: 文件路径

        Returns:
            条目列表
        """
        if not file_path.exists():
            return []

        try:
            content = file_path.read_text(encoding="utf-8")
            # 使用分隔符解析条目
            entries = self._parse_entries(content)
            return entries
        except Exception as e:
            logger.error(f"加载记忆文件失败 {file_path}: {e}")
            return []

    def _parse_entries(self, content: str) -> List[str]:
        """解析记忆条目。

        Args:
            content: 文件内容

        Returns:
            条目列表（去除空条目和注释）
        """
        # 先按行过滤注释
        lines = content.split("\n")
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            # 跳过空行和注释行
            if not stripped or stripped.startswith("#"):
                continue
            filtered_lines.append(line)

        # 重新组合
        filtered_content = "\n".join(filtered_lines)

        # 使用分隔符分割
        raw_entries = filtered_content.split(ENTRY_DELIMITER)

        # 过滤空条目
        entries = []
        for entry in raw_entries:
            entry = entry.strip()
            if entry:
                entries.append(entry)

        return entries

    def _capture_snapshot(self) -> None:
        """捕获冻结快照。

        冻结快照在会话启动时创建，保持 LLM 前缀缓存。
        后续对记忆的修改不会影响已注入的系统提示。
        """
        self._system_prompt_snapshot = {
            "memory": self._render_block("memory", self._memory_entries),
            "user": self._render_block("user", self._user_entries),
        }
        logger.debug("已捕获记忆冻结快照")

    def _render_block(self, target: str, entries: List[str]) -> str:
        """渲染记忆块。

        Args:
            target: 目标类型（memory/user）
            entries: 条目列表

        Returns:
            渲染后的文本块
        """
        if not entries:
            return ""

        # 添加围栏标记（用于清洗）
        lines = [
            f"<{target}>",
            ENTRY_DELIMITER.join(entries),
            f"</{target}>",
        ]

        return "\n".join(lines)

    def format_for_system_prompt(self, target: str) -> str:
        """获取用于系统提示的记忆块。

        返回冻结快照，保持 LLM 前缀缓存。

        Args:
            target: 目标类型（memory/user）

        Returns:
            记忆块文本，如果不存在或为空则返回空字符串
        """
        return self._system_prompt_snapshot.get(target, "")

    def add_entry(
        self,
        target: str,
        entry: str,
        sync: bool = True,
        check_threats: bool = True,
    ) -> bool:
        """添加记忆条目。

        Args:
            target: 目标类型（memory/user）
            entry: 条目内容
            sync: 是否立即同步到磁盘
            check_threats: 是否检查安全威胁

        Returns:
            是否成功添加
        """
        if target not in ("memory", "user"):
            logger.error(f"无效的目标类型: {target}")
            return False

        # 安全扫描
        if check_threats:
            threats = self.scan_for_threats(entry)
            if threats:
                logger.warning(f"记忆条目包含威胁模式: {threats}")
                return False

        # 清理条目
        entry = entry.strip()
        if not entry:
            return False

        # 去重检查
        entries = self._memory_entries if target == "memory" else self._user_entries
        if entry in entries:
            logger.debug(f"条目已存在，跳过: {entry[:50]}...")
            return False

        with self._lock:
            entries.append(entry)

            # 检查字符限制
            limit = self._memory_char_limit if target == "memory" else self._user_char_limit
            total_chars = sum(len(e) for e in entries) + len(ENTRY_DELIMITER) * (len(entries) - 1)

            if total_chars > limit:
                # 需要裁剪旧条目
                self._trim_entries(target, limit)

            if sync:
                self._sync_target(target)

        logger.debug(f"添加记忆条目 [{target}]: {entry[:50]}...")
        return True

    def remove_entry(self, target: str, entry: str, sync: bool = True) -> bool:
        """移除记忆条目。

        Args:
            target: 目标类型（memory/user）
            entry: 条目内容（或前缀匹配）
            sync: 是否立即同步到磁盘

        Returns:
            是否成功移除
        """
        if target not in ("memory", "user"):
            return False

        with self._lock:
            entries = self._memory_entries if target == "memory" else self._user_entries

            # 查找匹配的条目
            removed = False
            for i, e in enumerate(entries):
                if e == entry or e.startswith(entry):
                    entries.pop(i)
                    removed = True
                    break

            if removed and sync:
                self._sync_target(target)

        return removed

    def clear_entries(self, target: str, sync: bool = True) -> int:
        """清空指定目标的条目。

        Args:
            target: 目标类型（memory/user）
            sync: 是否立即同步到磁盘

        Returns:
            清空的条目数
        """
        if target not in ("memory", "user"):
            return 0

        with self._lock:
            entries = self._memory_entries if target == "memory" else self._user_entries
            count = len(entries)
            entries.clear()

            if sync:
                self._sync_target(target)

        return count

    def _trim_entries(self, target: str, limit: int) -> int:
        """裁剪条目以符合字符限制。

        Args:
            target: 目标类型
            limit: 字符限制

        Returns:
            裁剪的条目数
        """
        entries = self._memory_entries if target == "memory" else self._user_entries

        removed = 0
        while entries:
            total = sum(len(e) for e in entries) + len(ENTRY_DELIMITER) * max(0, len(entries) - 1)
            if total <= limit:
                break
            # 移除最旧的条目
            entries.pop(0)
            removed += 1

        return removed

    def scan_for_threats(self, content: str) -> List[str]:
        """扫描内容中的安全威胁模式。

        Args:
            content: 待扫描内容

        Returns:
            发现的威胁类型列表
        """
        threats = []
        for pattern, threat_type in _MEMORY_THREAT_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                threats.append(threat_type)

        return threats

    def sync_to_disk(self) -> Dict[str, bool]:
        """同步所有记忆到磁盘。

        Returns:
            {"memory": success, "user": success}
        """
        results = {}
        with self._lock:
            results["memory"] = self._sync_target("memory")
            results["user"] = self._sync_target("user")

        return results

    def _sync_target(self, target: str) -> bool:
        """同步指定目标到磁盘。

        Args:
            target: 目标类型

        Returns:
            是否成功
        """
        entries = self._memory_entries if target == "memory" else self._user_entries
        file_name = "MEMORY.md" if target == "memory" else "USER.md"
        file_path = self._base_path / file_name

        # 构建内容
        content = self._build_file_content(target, entries)

        # 原子写入
        try:
            self._atomic_write(file_path, content)
            return True
        except Exception as e:
            logger.error(f"同步记忆失败 {file_path}: {e}")
            return False

    def _build_file_content(self, target: str, entries: List[str]) -> str:
        """构建文件内容。

        Args:
            target: 目标类型
            entries: 条目列表

        Returns:
            文件内容（包含注释头和条目）
        """
        header = f"# {target.upper()} 记忆\n"
        header += "# 此文件由 AgentForge 自动管理\n"
        header += "# 格式: 条目以 § 分隔\n\n"

        if not entries:
            return header + "# (空)\n"

        body = ENTRY_DELIMITER.join(entries)
        return header + body + "\n"

    def _atomic_write(self, path: Path, content: str) -> None:
        """原子写入文件。

        先写入临时文件，然后原子替换目标文件。

        Args:
            path: 目标文件路径
            content: 文件内容
        """
        # 创建临时文件
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            suffix=".tmp",
            prefix=path.stem + "_",
        )

        try:
            # 写入内容
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            # 原子替换
            # Windows 上需要先删除目标文件
            if path.exists():
                path.unlink()
            os.replace(tmp_path, path)

        except Exception:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def get_total_chars(self, target: str) -> int:
        """获取指定目标的字符总数。

        Args:
            target: 目标类型

        Returns:
            字符总数
        """
        entries = self._memory_entries if target == "memory" else self._user_entries
        if not entries:
            return 0
        return sum(len(e) for e in entries) + len(ENTRY_DELIMITER) * (len(entries) - 1)

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息。

        Returns:
            统计信息字典
        """
        return {
            "memory_entries": len(self._memory_entries),
            "memory_chars": self.get_total_chars("memory"),
            "memory_limit": self._memory_char_limit,
            "user_entries": len(self._user_entries),
            "user_chars": self.get_total_chars("user"),
            "user_limit": self._user_char_limit,
            "has_snapshot": bool(self._system_prompt_snapshot.get("memory") or
                                 self._system_prompt_snapshot.get("user")),
        }

    def refresh_snapshot(self) -> None:
        """刷新冻结快照。

        通常在会话结束时调用，为下一次会话准备。
        """
        with self._lock:
            self._capture_snapshot()


__all__ = ["MemoryStore", "ENTRY_DELIMITER", "DEFAULT_MEMORY_CHAR_LIMIT", "DEFAULT_USER_CHAR_LIMIT"]