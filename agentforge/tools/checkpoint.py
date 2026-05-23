"""Checkpoint Manager - 基于 Git 的文件系统快照管理。

在文件变更操作前自动创建工作目录快照，支持回滚到任意 checkpoint。
这是透明基础设施，LLM 不直接调用。

存储布局（单一共享存储，git 对象跨项目去重）：

    ~/.agentforge/checkpoints/
        store/                          — 单一 bare-ish git 仓库
            HEAD, config, objects/      — 标准 git 内部结构（共享）
            refs/agentforge/<hash16>    — 每项目分支尖端
            indexes/<hash16>            — 每项目 git index
            projects/<hash16>.json      — {workdir, created_at, last_touch}
            info/exclude                — 默认排除规则（共享）

为什么使用单一存储？
    v1 设计为每个工作目录维护一个完整的 shadow repo。每个都在自己的
    objects/ 树下存储项目的大部分文件，同一项目的多个 worktree 之间
    零共享。一个用户有同一仓库的十几个 worktree 会每个消耗约 40 MB
    （总计约 500 MB）重复存储相同的 blob。单一共享存储让 git 的
    内容寻址对象数据库跨项目、跨轮次去重，添加新 worktree 成本接近零。

参考 hermes-agent/tools/checkpoint_manager.py。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 默认 checkpoint 存储基础目录
def _get_checkpoint_base() -> Path:
    """获取 checkpoint 存储基础目录。"""
    return Path.home() / ".agentforge" / "checkpoints"


# 存储目录名
_STORE_DIRNAME = "store"
_REFS_PREFIX = "refs/agentforge"
_INDEXES_DIRNAME = "indexes"
_PROJECTS_DIRNAME = "projects"
_LEGACY_PREFIX = "legacy-"
_PRUNE_MARKER_NAME = ".last_prune"

# 默认排除列表
DEFAULT_EXCLUDES = [
    # 依赖/构建输出
    "node_modules/",
    "dist/",
    "build/",
    "target/",
    "out/",
    ".next/",
    ".nuxt/",
    # 缓存
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".cache/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "coverage/",
    ".coverage",
    # 虚拟环境
    ".venv/",
    "venv/",
    "env/",
    # VCS
    ".git/",
    ".hg/",
    ".svn/",
    # Worktrees
    ".worktrees/",
    # 原生/编译二进制
    "*.so",
    "*.dylib",
    "*.dll",
    "*.o",
    "*.a",
    "*.jar",
    "*.class",
    "*.exe",
    "*.obj",
    # 媒体/大型二进制
    "*.mp4",
    "*.mov",
    "*.mkv",
    "*.webm",
    "*.zip",
    "*.tar",
    "*.tar.gz",
    "*.tgz",
    "*.7z",
    "*.rar",
    "*.iso",
    # 密钥
    ".env",
    ".env.*",
    ".env.local",
    ".env.*.local",
    # OS 垃圾
    ".DS_Store",
    "Thumbs.db",
    # 日志
    "*.log",
]

# Git 子进程超时（秒）
_GIT_TIMEOUT: int = max(10, min(60, int(os.getenv("AGENTFORGE_CHECKPOINT_TIMEOUT", "30"))))

# 最大文件数 — 跳过巨大目录以避免减速
_MAX_FILES = 50_000

# 有效 git commit hash 模式：4-40 个十六进制字符
_COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


# ---------------------------------------------------------------------------
# 输入验证辅助函数
# ---------------------------------------------------------------------------

def _validate_commit_hash(commit_hash: str) -> Optional[str]:
    """验证 commit hash 以防止 git 参数注入。

    如果无效返回错误字符串，有效返回 None。
    以 '-' 开头的值会被解释为 git 标志（如 '--patch', '-p'）而不是修订说明符。
    """
    if not commit_hash or not commit_hash.strip():
        return "空的 commit hash"
    if commit_hash.startswith("-"):
        return f"无效的 commit hash（不能以 '-' 开头）：{commit_hash!r}"
    if not _COMMIT_HASH_RE.match(commit_hash):
        return f"无效的 commit hash（需要 4-64 个十六进制字符）：{commit_hash!r}"
    return None


def _validate_file_path(file_path: str, working_dir: str) -> Optional[str]:
    """验证文件路径以防止路径遍历逃逸工作目录。

    如果无效返回错误字符串，有效返回 None。
    """
    if not file_path or not file_path.strip():
        return "空的文件路径"
    if os.path.isabs(file_path):
        return f"文件路径必须是相对路径，得到绝对路径：{file_path!r}"
    abs_workdir = _normalize_path(working_dir)
    resolved = (abs_workdir / file_path).resolve()
    try:
        resolved.relative_to(abs_workdir)
    except ValueError:
        return f"文件路径通过遍历逃逸工作目录：{file_path!r}"
    return None


# ---------------------------------------------------------------------------
# 路径/哈希辅助函数
# ---------------------------------------------------------------------------

def _normalize_path(path_value: str) -> Path:
    """返回用于 checkpoint 操作的规范化绝对路径。"""
    return Path(path_value).expanduser().resolve()


def _project_hash(working_dir: str) -> str:
    """确定性每项目哈希：sha256(abs_path)[:16]。"""
    abs_path = str(_normalize_path(working_dir))
    return hashlib.sha256(abs_path.encode()).hexdigest()[:16]


def _store_path(base: Optional[Path] = None) -> Path:
    """返回单一共享 shadow 存储路径。"""
    return (base or _get_checkpoint_base()) / _STORE_DIRNAME


def _index_path(store: Path, dir_hash: str) -> Path:
    """返回每项目 index 文件路径。"""
    return store / _INDEXES_DIRNAME / dir_hash


def _ref_name(dir_hash: str) -> str:
    """返回每项目 ref 名称。"""
    return f"{_REFS_PREFIX}/{dir_hash}"


def _project_meta_path(store: Path, dir_hash: str) -> Path:
    """返回每项目元数据文件路径。"""
    return store / _PROJECTS_DIRNAME / f"{dir_hash}.json"


# ---------------------------------------------------------------------------
# Git 环境
# ---------------------------------------------------------------------------

def _git_env(
    store: Path,
    working_dir: str,
    index_file: Optional[Path] = None,
) -> dict:
    """构建重定向 git 到共享存储的环境字典。

    共享存储是 AgentForge 内部基础设施 — 不能继承用户的全局或系统
    git 配置。用户级别的设置如 commit.gpgsign = true、签名 hooks 或
    credential helpers 会破坏后台快照，或者更糟，每次写入文件时
    弹出交互式提示（pinentry GUI 窗口）。

    隔离策略：
    * GIT_CONFIG_GLOBAL=<os.devnull> — 忽略 ~/.gitconfig（git 2.32+）
    * GIT_CONFIG_SYSTEM=<os.devnull> — 忽略 /etc/gitconfig（git 2.32+）
    * GIT_CONFIG_NOSYSTEM=1 — 旧版 git 的额外保护
    """
    normalized_working_dir = _normalize_path(working_dir)
    env = os.environ.copy()
    env["GIT_DIR"] = str(store)
    env["GIT_WORK_TREE"] = str(normalized_working_dir)
    env.pop("GIT_NAMESPACE", None)
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    if index_file is not None:
        env["GIT_INDEX_FILE"] = str(index_file)
    else:
        env.pop("GIT_INDEX_FILE", None)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _run_git(
    args: List[str],
    store: Path,
    working_dir: str,
    timeout: int = _GIT_TIMEOUT,
    allowed_returncodes: Optional[Set[int]] = None,
    index_file: Optional[Path] = None,
) -> Tuple[bool, str, str]:
    """对共享存储运行 git 命令。返回 (ok, stdout, stderr)。

    allowed_returncodes 抑制已知/预期的非零退出的错误日志，
    同时保持正常的 ok = (returncode == 0) 约定。
    例如：git diff --cached --quiet 在有变更时返回 1。
    """
    normalized_working_dir = _normalize_path(working_dir)
    if not normalized_working_dir.exists():
        msg = f"工作目录不存在：{normalized_working_dir}"
        logger.error("Git 命令跳过：%s (%s)", " ".join(["git"] + list(args)), msg)
        return False, "", msg
    if not normalized_working_dir.is_dir():
        msg = f"工作目录不是目录：{normalized_working_dir}"
        logger.error("Git 命令跳过：%s (%s)", " ".join(["git"] + list(args)), msg)
        return False, "", msg

    env = _git_env(store, str(normalized_working_dir), index_file=index_file)
    cmd = ["git"] + list(args)
    allowed_returncodes = allowed_returncodes or set()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(normalized_working_dir),
        )
        ok = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if not ok and result.returncode not in allowed_returncodes:
            logger.error(
                "Git 命令失败：%s (rc=%d) stderr=%s",
                " ".join(cmd), result.returncode, stderr,
            )
        return ok, stdout, stderr
    except subprocess.TimeoutExpired:
        msg = f"git 在 {timeout}s 后超时：{' '.join(cmd)}"
        logger.error(msg, exc_info=True)
        return False, "", msg
    except FileNotFoundError as exc:
        missing_target = getattr(exc, "filename", None)
        if missing_target == "git":
            logger.error("找不到 git 可执行文件：%s", " ".join(cmd), exc_info=True)
            return False, "", "找不到 git"
        msg = f"工作目录不存在：{normalized_working_dir}"
        logger.error("Git 命令执行前失败：%s (%s)", " ".join(cmd), msg, exc_info=True)
        return False, "", msg
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("运行 %s 时发生意外 git 错误：%s", " ".join(cmd), exc, exc_info=True)
        return False, "", str(exc)


# ---------------------------------------------------------------------------
# 存储初始化
# ---------------------------------------------------------------------------

def _init_store(store: Path, working_dir: str) -> Optional[str]:
    """初始化共享 shadow 存储（如需要）。返回错误或 None。"""
    base = store.parent

    if not store.exists():
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"无法创建 checkpoint 基础目录：{exc}"

    if (store / "HEAD").exists():
        return None

    store.mkdir(parents=True, exist_ok=True)
    (store / _INDEXES_DIRNAME).mkdir(exist_ok=True)
    (store / _PROJECTS_DIRNAME).mkdir(exist_ok=True)

    # git init --bare 拒绝 GIT_WORK_TREE，所以这里不能用 _run_git
    # 使用原始 subprocess 和配置隔离环境变量
    init_env = os.environ.copy()
    init_env["GIT_CONFIG_GLOBAL"] = os.devnull
    init_env["GIT_CONFIG_SYSTEM"] = os.devnull
    init_env["GIT_CONFIG_NOSYSTEM"] = "1"
    # 移除任何继承的 GIT_* 变量
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_NAMESPACE",
              "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        init_env.pop(k, None)
    try:
        result = subprocess.run(
            ["git", "init", "--bare", str(store)],
            capture_output=True, text=True,
            env=init_env, timeout=_GIT_TIMEOUT,
        )
        if result.returncode != 0:
            return f"Shadow 存储初始化失败：{result.stderr.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return f"Shadow 存储初始化失败：{exc}"

    # 每存储配置（由上述环境变量隔离，但双重保护）
    cfg_wd = str(base)
    _run_git(["config", "user.email", "agentforge@local"], store, cfg_wd)
    _run_git(["config", "user.name", "AgentForge Checkpoint"], store, cfg_wd)
    _run_git(["config", "commit.gpgsign", "false"], store, cfg_wd)
    _run_git(["config", "tag.gpgSign", "false"], store, cfg_wd)
    _run_git(["config", "gc.auto", "0"], store, cfg_wd)

    info_dir = store / "info"
    info_dir.mkdir(exist_ok=True)
    (info_dir / "exclude").write_text(
        "\n".join(DEFAULT_EXCLUDES) + "\n", encoding="utf-8"
    )

    logger.debug("在 %s 初始化 checkpoint 存储", store)
    return None


def _register_project(store: Path, working_dir: str) -> None:
    """创建或更新 projects/<hash>.json，包含 workdir + 时间戳。"""
    dir_hash = _project_hash(working_dir)
    meta_path = _project_meta_path(store, dir_hash)
    now = time.time()
    meta: Dict = {
        "workdir": str(_normalize_path(working_dir)),
        "created_at": now,
        "last_touch": now
    }
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                meta["created_at"] = existing.get("created_at", now)
        except (OSError, ValueError):
            pass
    try:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except OSError as exc:
        logger.debug("无法写入项目元数据 %s：%s", meta_path, exc)


def _touch_project(store: Path, working_dir: str) -> None:
    """更新项目的 last_touch，保留 created_at。"""
    dir_hash = _project_hash(working_dir)
    meta_path = _project_meta_path(store, dir_hash)
    if not meta_path.exists():
        _register_project(store, working_dir)
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["workdir"] = str(_normalize_path(working_dir))
    meta["last_touch"] = time.time()
    meta.setdefault("created_at", meta["last_touch"])
    try:
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except OSError as exc:
        logger.debug("无法更新项目元数据 %s：%s", meta_path, exc)


def _list_projects(store: Path) -> List[Dict]:
    """返回存储下所有已注册项目。"""
    projects_dir = store / _PROJECTS_DIRNAME
    if not projects_dir.exists():
        return []
    out: List[Dict] = []
    for meta_path in projects_dir.glob("*.json"):
        dir_hash = meta_path.stem
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        meta["_hash"] = dir_hash
        out.append(meta)
    return out


def _dir_file_count(path: str) -> int:
    """快速文件数估算（超过 _MAX_FILES 时提前停止）。"""
    count = 0
    try:
        for _ in Path(path).rglob("*"):
            count += 1
            if count > _MAX_FILES:
                return count
    except (PermissionError, OSError):
        pass
    return count


def _dir_size_bytes(path: Path) -> int:
    """尽力计算递归大小（字节）。错误时返回 0。"""
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------

class CheckpointManager:
    """管理自动文件系统 checkpoint。

    设计为由 AIAgent 持有。在每个对话轮次开始时调用 new_turn()，
    在任何文件变更工具调用前调用 ensure_checkpoint(dir, reason)。
    管理器去重，每轮次每个目录最多拍一次快照。

    参数
    ----------
    enabled : bool
        主开关（来自配置 / CLI 标志）。
    max_snapshots : int
        每个目录最多保留的 checkpoint 数。
    max_total_size_mb : int
        存储总大小的硬上限。commit 后存储超过此值时，
        每项目最旧的 checkpoint 会被删除。
    max_file_size_mb : int
        跳过添加任何超过此大小的单个文件到 checkpoint。
    """

    def __init__(
        self,
        enabled: bool = False,
        max_snapshots: int = 20,
        max_total_size_mb: int = 500,
        max_file_size_mb: int = 10,
        checkpoint_base: Optional[Path] = None,
    ):
        """初始化 Checkpoint Manager。

        Args:
            enabled: 是否启用 checkpoint
            max_snapshots: 每个目录最多保留的 checkpoint 数
            max_total_size_mb: 存储总大小上限（MB）
            max_file_size_mb: 单文件最大大小上限（MB）
            checkpoint_base: checkpoint 存储基础目录
        """
        self.enabled = enabled
        self.max_snapshots = max(1, int(max_snapshots))
        self.max_total_size_mb = max(0, int(max_total_size_mb))
        self.max_file_size_mb = max(0, int(max_file_size_mb))
        self._checkpoint_base = checkpoint_base
        self._checkpointed_dirs: Set[str] = set()
        self._git_available: Optional[bool] = None  # 延迟探测

    @property
    def _base(self) -> Path:
        """获取 checkpoint 基础目录。"""
        return self._checkpoint_base or _get_checkpoint_base()

    # ------------------------------------------------------------------
    # 轮次生命周期
    # ------------------------------------------------------------------

    def new_turn(self) -> None:
        """重置每轮去重。在每个 agent 迭代开始时调用。"""
        self._checkpointed_dirs.clear()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def ensure_checkpoint(self, working_dir: str, reason: str = "auto") -> bool:
        """如果启用且本轮未创建，则拍一个 checkpoint。

        Args:
            working_dir: 工作目录
            reason: checkpoint 原因

        Returns:
            如果拍了 checkpoint 返回 True，否则 False。
            从不抛出异常 — 所有错误静默记录日志。
        """
        if not self.enabled:
            return False

        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
            if not self._git_available:
                logger.debug("Checkpoint 已禁用：找不到 git")
        if not self._git_available:
            return False

        abs_dir = str(_normalize_path(working_dir))

        # 跳过根目录、home 和其他过于宽泛的目录
        if abs_dir in {"/", str(Path.home())}:
            logger.debug("Checkpoint 跳过：目录过于宽泛（%s）", abs_dir)
            return False

        if abs_dir in self._checkpointed_dirs:
            return False

        self._checkpointed_dirs.add(abs_dir)

        try:
            return self._take(abs_dir, reason)
        except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug("Checkpoint 失败（非致命）：%s", e)
            return False

    def list_checkpoints(self, working_dir: str) -> List[Dict]:
        """列出目录的可用 checkpoint（最新在前）。

        Args:
            working_dir: 工作目录

        Returns:
            checkpoint 列表
        """
        abs_dir = str(_normalize_path(working_dir))
        store = _store_path(self._base)

        if not (store / "HEAD").exists():
            return []

        ref = _ref_name(_project_hash(abs_dir))
        ok, stdout, _ = _run_git(
            ["log", ref, f"--format=%H|%h|%aI|%s", "-n", str(self.max_snapshots)],
            store, abs_dir,
            allowed_returncodes={128, 129},
        )

        if not ok or not stdout:
            return []

        results: List[Dict] = []
        for line in stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                entry = {
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "timestamp": parts[2],
                    "reason": parts[3],
                    "files_changed": 0,
                    "insertions": 0,
                    "deletions": 0,
                }
                stat_ok, stat_out, _ = _run_git(
                    ["diff", "--shortstat", f"{parts[0]}~1", parts[0]],
                    store, abs_dir,
                    allowed_returncodes={128, 129},
                )
                if stat_ok and stat_out:
                    self._parse_shortstat(stat_out, entry)
                results.append(entry)
        return results

    @staticmethod
    def _parse_shortstat(stat_line: str, entry: Dict) -> None:
        """解析 git --shortstat 输出到 entry 字典。"""
        m = re.search(r"(\d+) file", stat_line)
        if m:
            entry["files_changed"] = int(m.group(1))
        m = re.search(r"(\d+) insertion", stat_line)
        if m:
            entry["insertions"] = int(m.group(1))
        m = re.search(r"(\d+) deletion", stat_line)
        if m:
            entry["deletions"] = int(m.group(1))

    def diff(self, working_dir: str, commit_hash: str) -> Dict:
        """显示 checkpoint 和当前工作树之间的差异。

        Args:
            working_dir: 工作目录
            commit_hash: checkpoint 的 commit hash

        Returns:
            差异信息字典
        """
        hash_err = _validate_commit_hash(commit_hash)
        if hash_err:
            return {"success": False, "error": hash_err}

        abs_dir = str(_normalize_path(working_dir))
        store = _store_path(self._base)

        if not (store / "HEAD").exists():
            return {"success": False, "error": "此目录没有 checkpoint"}

        ok, _, err = _run_git(
            ["cat-file", "-t", commit_hash], store, abs_dir,
        )
        if not ok:
            return {"success": False, "error": f"找不到 checkpoint '{commit_hash}'"}

        dir_hash = _project_hash(abs_dir)
        index_file = _index_path(store, dir_hash)

        # 将当前状态暂存到每项目 index 以便比较
        _run_git(["add", "-A"], store, abs_dir,
                 timeout=_GIT_TIMEOUT * 2, index_file=index_file)

        ok_stat, stat_out, _ = _run_git(
            ["diff", "--stat", commit_hash, "--cached"],
            store, abs_dir, index_file=index_file,
        )
        ok_diff, diff_out, _ = _run_git(
            ["diff", commit_hash, "--cached", "--no-color"],
            store, abs_dir, index_file=index_file,
        )

        # 重置暂存树回项目的最后一个 checkpoint，避免 index 与 ref 不同步
        ref = _ref_name(dir_hash)
        _run_git(["read-tree", ref], store, abs_dir,
                 index_file=index_file,
                 allowed_returncodes={128})

        if not ok_stat and not ok_diff:
            return {"success": False, "error": "无法生成 diff"}

        return {
            "success": True,
            "stat": stat_out if ok_stat else "",
            "diff": diff_out if ok_diff else "",
        }

    def restore(self, working_dir: str, commit_hash: str, file_path: str = None) -> Dict:
        """恢复文件到 checkpoint 状态。

        Args:
            working_dir: 工作目录
            commit_hash: checkpoint 的 commit hash
            file_path: 要恢复的单个文件（可选）

        Returns:
            恢复结果字典
        """
        hash_err = _validate_commit_hash(commit_hash)
        if hash_err:
            return {"success": False, "error": hash_err}

        abs_dir = str(_normalize_path(working_dir))

        if file_path:
            path_err = _validate_file_path(file_path, abs_dir)
            if path_err:
                return {"success": False, "error": path_err}

        store = _store_path(self._base)

        if not (store / "HEAD").exists():
            return {"success": False, "error": "此目录没有 checkpoint"}

        ok, _, err = _run_git(
            ["cat-file", "-t", commit_hash], store, abs_dir,
        )
        if not ok:
            return {"success": False, "error": f"找不到 checkpoint '{commit_hash}'",
                    "debug": err or None}

        # 拍一个回滚前快照以便撤销撤销
        self._take(abs_dir, f"回滚前快照（恢复到 {commit_hash[:8]}）")

        dir_hash = _project_hash(abs_dir)
        index_file = _index_path(store, dir_hash)

        restore_target = file_path if file_path else "."
        ok, stdout, err = _run_git(
            ["checkout", commit_hash, "--", restore_target],
            store, abs_dir, timeout=_GIT_TIMEOUT * 2,
            index_file=index_file,
        )

        if not ok:
            return {"success": False, "error": f"恢复失败：{err}",
                    "debug": err or None}

        ok2, reason_out, _ = _run_git(
            ["log", "--format=%s", "-1", commit_hash], store, abs_dir,
        )
        reason = reason_out if ok2 else "unknown"

        result = {
            "success": True,
            "restored_to": commit_hash[:8],
            "reason": reason,
            "directory": abs_dir,
        }
        if file_path:
            result["file"] = file_path
        return result

    def get_working_dir_for_path(self, file_path: str) -> str:
        """将文件路径解析为其工作目录以便 checkpoint。

        Args:
            file_path: 文件路径

        Returns:
            工作目录路径
        """
        path = _normalize_path(file_path)
        if path.is_dir():
            candidate = path
        else:
            candidate = path.parent

        markers = {".git", "pyproject.toml", "package.json", "Cargo.toml",
                   "go.mod", "Makefile", "pom.xml", ".hg", "Gemfile"}
        check = candidate
        while check != check.parent:
            if any((check / m).exists() for m in markers):
                return str(check)
            check = check.parent

        return str(candidate)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _take(self, working_dir: str, reason: str) -> bool:
        """拍一个快照。成功返回 True。"""
        store = _store_path(self._base)

        err = _init_store(store, working_dir)
        if err:
            logger.debug("Checkpoint 存储初始化失败：%s", err)
            return False

        _touch_project(store, working_dir)

        # 快速大小保护 — 不尝试快照巨大目录
        if _dir_file_count(working_dir) > _MAX_FILES:
            logger.debug("Checkpoint 跳过：%s 中超过 %d 个文件", _MAX_FILES, working_dir)
            return False

        dir_hash = _project_hash(working_dir)
        index_file = _index_path(store, dir_hash)
        ref = _ref_name(dir_hash)

        # 从最后一个 checkpoint（如有）种子每项目 index，
        # 这样 diff/commit 机制只看到自此以来的变更。
        # 首次调用时，清空 index 让 git add -A 产生干净的树。
        if index_file.exists():
            # 重置 index 到当前 ref 尖端以避免累积过期路径
            ok_ref, ref_commit, _ = _run_git(
                ["rev-parse", "--verify", ref + "^{commit}"],
                store, working_dir,
                allowed_returncodes={128},
            )
            if ok_ref and ref_commit:
                _run_git(
                    ["read-tree", ref_commit],
                    store, working_dir,
                    index_file=index_file,
                    allowed_returncodes={128},
                )
            else:
                try:
                    index_file.unlink()
                except OSError:
                    pass
        else:
            # 此项目的首次快照
            index_file.parent.mkdir(parents=True, exist_ok=True)

        # 使用每项目 index 暂存
        ok, _, err = _run_git(
            ["add", "-A"], store, working_dir,
            timeout=_GIT_TIMEOUT * 2, index_file=index_file,
        )
        if not ok:
            logger.debug("Checkpoint git-add 失败：%s", err)
            return False

        if self.max_file_size_mb > 0:
            self._drop_oversize_from_index(store, working_dir, index_file)

        # 与当前 ref 尖端比较（不是 HEAD — HEAD 指向一个
        # 在 bare store 上不存在的分支，所以对 HEAD 的 diff --cached
        # 会为每个暂存路径显示 "new file"）
        ok_ref, ref_commit, _ = _run_git(
            ["rev-parse", "--verify", ref + "^{commit}"],
            store, working_dir,
            allowed_returncodes={128},
        )
        has_ref = ok_ref and bool(ref_commit)

        if has_ref:
            ok_diff, _, _ = _run_git(
                ["diff-index", "--cached", "--quiet", ref_commit],
                store, working_dir,
                allowed_returncodes={1},
                index_file=index_file,
            )
            if ok_diff:
                logger.debug("Checkpoint 跳过：%s 中无变更", working_dir)
                return False
        else:
            # 还没有 ref — 仅当 index 为空时跳过
            ok_ls, ls_out, _ = _run_git(
                ["ls-files", "--cached"],
                store, working_dir,
                index_file=index_file,
            )
            if ok_ls and not ls_out.strip():
                logger.debug("Checkpoint 跳过：%s 中空树", working_dir)
                return False

        # 从每项目 index 写入树
        ok_tree, tree_sha, err = _run_git(
            ["write-tree"], store, working_dir,
            index_file=index_file,
        )
        if not ok_tree or not tree_sha:
            logger.debug("Checkpoint write-tree 失败：%s", err)
            return False

        # 构建 commit（parent = 当前 ref 尖端，如有）
        commit_args = ["commit-tree", tree_sha, "-m", reason, "--no-gpg-sign"]
        if has_ref:
            commit_args = ["commit-tree", tree_sha, "-p", ref_commit, "-m", reason, "--no-gpg-sign"]
        ok_commit, new_sha, err = _run_git(
            commit_args, store, working_dir,
            index_file=index_file,
        )
        if not ok_commit or not new_sha:
            logger.debug("Checkpoint commit-tree 失败：%s", err)
            return False

        # 更新每项目 ref
        update_args = ["update-ref", ref, new_sha]
        if has_ref:
            update_args = ["update-ref", ref, new_sha, ref_commit]
        ok_update, _, err = _run_git(
            update_args, store, working_dir,
        )
        if not ok_update:
            logger.debug("Checkpoint update-ref 失败：%s", err)
            return False

        logger.debug("在 %s 中拍了 checkpoint：%s (%s)", working_dir, reason, new_sha[:8])

        # 真正的修剪 — 删除超过 max_snapshots 的旧 commit
        self._prune(store, working_dir, ref)

        # 强制全局大小上限
        self._enforce_size_cap(store)

        return True

    def _drop_oversize_from_index(
        self, store: Path, working_dir: str, index_file: Path,
    ) -> None:
        """从 index 中移除任何超过 max_file_size_mb 的暂存文件。

        让 agent 继续快照源代码，同时拒绝吞下生成的资产
        （数据集、模型权重、日志、视频）。
        """
        cap = self.max_file_size_mb * 1024 * 1024
        if cap <= 0:
            return
        ok, stdout, _ = _run_git(
            ["ls-files", "--cached", "-z"],
            store, working_dir, index_file=index_file,
        )
        if not ok or not stdout:
            return
        # ls-files -z 输出以 NUL 分隔
        paths = [p for p in stdout.split("\x00") if p]
        abs_workdir = _normalize_path(working_dir)
        oversize: List[str] = []
        for rel in paths:
            try:
                size = (abs_workdir / rel).stat().st_size
            except OSError:
                continue
            if size > cap:
                oversize.append(rel)
        if not oversize:
            return
        logger.debug(
            "Checkpoint：从 index 中删除 %d 个超大文件（>%d MB）",
            len(oversize), self.max_file_size_mb,
        )
        # 分批处理
        BATCH = 200
        for i in range(0, len(oversize), BATCH):
            chunk = oversize[i:i + BATCH]
            _run_git(
                ["rm", "--cached", "--quiet", "--"] + chunk,
                store, working_dir, index_file=index_file,
                allowed_returncodes={128},
            )

    def _prune(self, store: Path, working_dir: str, ref: str) -> None:
        """只保留每项目 ref 上最后 max_snapshots 个 commit。

        重写 ref 以删除超过 max_snapshots 的旧 commit，
        然后对存储运行 git gc 以回收不可达对象。
        """
        ok, stdout, _ = _run_git(
            ["rev-list", "--count", ref], store, working_dir,
            allowed_returncodes={128},
        )
        if not ok:
            return
        try:
            count = int(stdout)
        except ValueError:
            return
        if count <= self.max_snapshots:
            return

        # 收集 commit 从最旧到最新，取最后 N 个
        ok_list, list_out, _ = _run_git(
            ["rev-list", "--reverse", ref], store, working_dir,
        )
        if not ok_list or not list_out:
            return
        commits = list_out.splitlines()
        keep = commits[-self.max_snapshots:]

        # 从 keep[0] 的树重建线性链
        new_parent: Optional[str] = None
        for sha in keep:
            ok_tree, tree_sha, _ = _run_git(
                ["rev-parse", f"{sha}^{{tree}}"], store, working_dir,
            )
            if not ok_tree or not tree_sha:
                return
            ok_msg, msg, _ = _run_git(
                ["log", "--format=%s", "-1", sha], store, working_dir,
            )
            commit_msg = msg if ok_msg and msg else "checkpoint"
            args = ["commit-tree", tree_sha, "-m", commit_msg, "--no-gpg-sign"]
            if new_parent is not None:
                args = ["commit-tree", tree_sha, "-p", new_parent,
                        "-m", commit_msg, "--no-gpg-sign"]
            ok_commit, new_sha, _ = _run_git(args, store, working_dir)
            if not ok_commit or not new_sha:
                return
            new_parent = new_sha

        if new_parent is None:
            return
        _run_git(["update-ref", ref, new_parent], store, working_dir)

        # 回收被删除 commit 的对象
        _run_git(
            ["reflog", "expire", "--expire=now", "--all"],
            store, working_dir,
        )
        _run_git(
            ["gc", "--prune=now", "--quiet"],
            store, working_dir, timeout=_GIT_TIMEOUT * 3,
        )

    def _enforce_size_cap(self, store: Path) -> None:
        """如果存储总大小超过 max_total_size_mb，删除所有项目中最旧的 checkpoint。"""
        if self.max_total_size_mb <= 0:
            return
        cap_bytes = self.max_total_size_mb * 1024 * 1024
        size = _dir_size_bytes(store)
        if size <= cap_bytes:
            return
        logger.info(
            "Checkpoint 存储超过 %d MB（实际 %d MB）— 删除最旧的",
            self.max_total_size_mb, size // (1024 * 1024),
        )

        # 收集所有每项目 ref 的 (commit_time, ref, sha)
        ok, stdout, _ = _run_git(
            ["for-each-ref", "--format=%(refname)", _REFS_PREFIX],
            store, str(store.parent),
            allowed_returncodes={128},
        )
        if not ok or not stdout:
            return
        refs = [r for r in stdout.splitlines() if r.strip()]

        any_dropped = False
        # 轮流删除每个 ref 最旧的 commit 直到低于上限
        for _ in range(20):  # 硬上限避免病态循环
            size = _dir_size_bytes(store)
            if size <= cap_bytes:
                break
            for ref in refs:
                ok_count, count_out, _ = _run_git(
                    ["rev-list", "--count", ref], store, str(store.parent),
                    allowed_returncodes={128},
                )
                try:
                    count = int(count_out) if ok_count else 0
                except ValueError:
                    count = 0
                if count <= 1:
                    continue  # 每项目至少保留一个快照
                ok_list, list_out, _ = _run_git(
                    ["rev-list", "--reverse", ref], store, str(store.parent),
                )
                if not ok_list or not list_out:
                    continue
                commits = list_out.splitlines()
                keep = commits[1:]  # 删除最旧的
                new_parent: Optional[str] = None
                fail = False
                for sha in keep:
                    ok_tree, tree_sha, _ = _run_git(
                        ["rev-parse", f"{sha}^{{tree}}"], store, str(store.parent),
                    )
                    if not ok_tree or not tree_sha:
                        fail = True
                        break
                    ok_msg, msg, _ = _run_git(
                        ["log", "--format=%s", "-1", sha], store, str(store.parent),
                    )
                    commit_msg = msg if ok_msg and msg else "checkpoint"
                    args = ["commit-tree", tree_sha, "-m", commit_msg, "--no-gpg-sign"]
                    if new_parent is not None:
                        args = ["commit-tree", tree_sha, "-p", new_parent,
                                "-m", commit_msg, "--no-gpg-sign"]
                    ok_commit, new_sha, _ = _run_git(args, store, str(store.parent))
                    if not ok_commit or not new_sha:
                        fail = True
                        break
                    new_parent = new_sha
                if fail or new_parent is None:
                    continue
                _run_git(["update-ref", ref, new_parent], store, str(store.parent))
                any_dropped = True
            if not any_dropped:
                break

        _run_git(
            ["reflog", "expire", "--expire=now", "--all"],
            store, str(store.parent),
        )
        _run_git(
            ["gc", "--prune=now", "--quiet"],
            store, str(store.parent), timeout=_GIT_TIMEOUT * 3,
        )

    def clear_all(self) -> Dict[str, int]:
        """清除所有 checkpoint。

        Returns:
            清除统计
        """
        base = self._base
        out = {"bytes_freed": 0, "deleted": False}
        if not base.exists():
            return out
        size = _dir_size_bytes(base)
        try:
            shutil.rmtree(base)
            out["bytes_freed"] = size
            out["deleted"] = True
        except OSError as exc:
            logger.warning("无法清除 checkpoint 基础目录 %s：%s", base, exc)
        return out


# ---------------------------------------------------------------------------
# 自动维护
# ---------------------------------------------------------------------------

def prune_checkpoints(
    retention_days: int = 7,
    delete_orphans: bool = True,
    checkpoint_base: Optional[Path] = None,
    max_total_size_mb: int = 0,
) -> Dict[str, int]:
    """删除过期/孤立 checkpoint 并回收存储空间。

    项目条目在以下情况下被删除：
    * delete_orphans=True 且其 workdir 在磁盘上不再存在
      （原项目被删除/移动）；或
    * 其 last_touch 早于 retention_days 天。

    此外，如果 max_total_size_mb > 0 且存储在孤立/过期修剪后
    仍超过该值，则删除每个剩余项目最旧的 commit 直到低于上限。

    Args:
        retention_days: 保留天数
        delete_orphans: 是否删除孤立项目
        checkpoint_base: checkpoint 基础目录
        max_total_size_mb: 存储总大小上限（MB）

    Returns:
        包含 {"scanned", "deleted_orphan", "deleted_stale",
              "errors", "bytes_freed"} 的字典
    """
    base = checkpoint_base or _get_checkpoint_base()
    result = {
        "scanned": 0,
        "deleted_orphan": 0,
        "deleted_stale": 0,
        "errors": 0,
        "bytes_freed": 0,
    }
    if not base.exists():
        return result

    size_before = _dir_size_bytes(base)

    cutoff = 0.0
    if retention_days > 0:
        cutoff = time.time() - retention_days * 86400

    # 处理 legacy 存档目录
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if child.name == _STORE_DIRNAME:
            continue
        if child.name.startswith(_LEGACY_PREFIX):
            if retention_days <= 0:
                continue
            try:
                m = child.stat().st_mtime
            except OSError:
                continue
            if m >= cutoff:
                continue
            try:
                size = _dir_size_bytes(child)
                shutil.rmtree(child)
                result["bytes_freed"] += size
                result["deleted_stale"] += 1
            except OSError as exc:
                result["errors"] += 1
                logger.warning("无法删除 legacy 存档 %s：%s", child, exc)
            continue

    # v2 共享存储：通过元数据进行每项目 ref 修剪
    store = _store_path(base)
    if (store / "HEAD").exists():
        for meta in _list_projects(store):
            dir_hash = meta.get("_hash") or ""
            workdir = meta.get("workdir") or ""
            if not dir_hash:
                continue
            result["scanned"] += 1
            reason = None
            if delete_orphans and (not workdir or not Path(workdir).exists()):
                reason = "orphan"
            elif retention_days > 0:
                last_touch = float(meta.get("last_touch", 0) or 0)
                if last_touch > 0 and last_touch < cutoff:
                    reason = "stale"
            if reason is None:
                continue
            ref = _ref_name(dir_hash)
            ok, _, _ = _run_git(
                ["update-ref", "-d", ref], store, str(base),
                allowed_returncodes={128},
            )
            # 删除每项目 index 和元数据
            try:
                idx = _index_path(store, dir_hash)
                if idx.exists():
                    idx.unlink()
            except OSError:
                pass
            try:
                mp = _project_meta_path(store, dir_hash)
                if mp.exists():
                    mp.unlink()
            except OSError:
                pass
            if reason == "orphan":
                result["deleted_orphan"] += 1
            else:
                result["deleted_stale"] += 1

        # GC 存储以回收被删除 ref 的不可达对象
        _run_git(
            ["reflog", "expire", "--expire=now", "--all"],
            store, str(base),
        )
        _run_git(
            ["gc", "--prune=now", "--quiet"],
            store, str(base), timeout=_GIT_TIMEOUT * 3,
        )

        # 剩余项目的大小上限检查
        if max_total_size_mb > 0:
            cap_bytes = max_total_size_mb * 1024 * 1024
            for _i in range(20):
                size = _dir_size_bytes(store)
                if size <= cap_bytes:
                    break
                ok, stdout, _ = _run_git(
                    ["for-each-ref", "--format=%(refname)", _REFS_PREFIX],
                    store, str(base),
                    allowed_returncodes={128},
                )
                refs = [r for r in stdout.splitlines() if r.strip()] if ok else []
                if not refs:
                    break
                any_drop = False
                for ref in refs:
                    ok_c, count_out, _ = _run_git(
                        ["rev-list", "--count", ref], store, str(base),
                        allowed_returncodes={128},
                    )
                    try:
                        count = int(count_out) if ok_c else 0
                    except ValueError:
                        count = 0
                    if count <= 1:
                        continue
                    ok_l, lo, _ = _run_git(
                        ["rev-list", "--reverse", ref], store, str(base),
                    )
                    if not ok_l or not lo:
                        continue
                    commits = lo.splitlines()
                    keep = commits[1:]
                    new_parent: Optional[str] = None
                    fail = False
                    for sha in keep:
                        ok_t, tsha, _ = _run_git(
                            ["rev-parse", f"{sha}^{{tree}}"], store, str(base),
                        )
                        if not ok_t or not tsha:
                            fail = True
                            break
                        ok_m, m, _ = _run_git(
                            ["log", "--format=%s", "-1", sha], store, str(base),
                        )
                        msg = m if ok_m and m else "checkpoint"
                        args = ["commit-tree", tsha, "-m", msg, "--no-gpg-sign"]
                        if new_parent is not None:
                            args = ["commit-tree", tsha, "-p", new_parent,
                                    "-m", msg, "--no-gpg-sign"]
                        ok_cm, new_sha, _ = _run_git(args, store, str(base))
                        if not ok_cm or not new_sha:
                            fail = True
                            break
                        new_parent = new_sha
                    if fail or new_parent is None:
                        continue
                    _run_git(["update-ref", ref, new_parent], store, str(base))
                    any_drop = True
                if not any_drop:
                    break
            _run_git(
                ["reflog", "expire", "--expire=now", "--all"],
                store, str(base),
            )
            _run_git(
                ["gc", "--prune=now", "--quiet"],
                store, str(base), timeout=_GIT_TIMEOUT * 3,
            )

    size_after = _dir_size_bytes(base)
    delta = size_before - size_after
    result["bytes_freed"] = max(result["bytes_freed"], delta)

    return result


def maybe_auto_prune_checkpoints(
    retention_days: int = 7,
    min_interval_hours: int = 24,
    delete_orphans: bool = True,
    checkpoint_base: Optional[Path] = None,
    max_total_size_mb: int = 0,
) -> Dict[str, object]:
    """prune_checkpoints 的幂等包装器，用于启动钩子。

    完成时写入 CHECKPOINT_BASE/.last_prune，使后续在
    min_interval_hours 内的调用短路。

    Args:
        retention_days: 保留天数
        min_interval_hours: 最小间隔小时数
        delete_orphans: 是否删除孤立项目
        checkpoint_base: checkpoint 基础目录
        max_total_size_mb: 存储总大小上限（MB）

    Returns:
        {"skipped": bool, "result": prune_checkpoints-dict, "error": optional str}
    """
    base = checkpoint_base or _get_checkpoint_base()
    out: Dict[str, object] = {"skipped": False}

    try:
        if not base.exists():
            out["result"] = {
                "scanned": 0, "deleted_orphan": 0, "deleted_stale": 0,
                "errors": 0, "bytes_freed": 0,
            }
            return out

        marker = base / _PRUNE_MARKER_NAME
        now = time.time()
        if marker.exists():
            try:
                last_ts = float(marker.read_text(encoding="utf-8").strip())
                if now - last_ts < min_interval_hours * 3600:
                    out["skipped"] = True
                    return out
            except (OSError, ValueError):
                pass  # 损坏的标记 — 视为无先前运行

        result = prune_checkpoints(
            retention_days=retention_days,
            delete_orphans=delete_orphans,
            checkpoint_base=base,
            max_total_size_mb=max_total_size_mb,
        )
        out["result"] = result

        try:
            marker.write_text(str(now), encoding="utf-8")
        except OSError as exc:
            logger.debug("无法写入 checkpoint 修剪标记：%s", exc)

        total = result["deleted_orphan"] + result["deleted_stale"]
        if total > 0:
            logger.info(
                "checkpoint 自动维护：修剪了 %d 个条目"
                "（%d 孤立，%d 过期），回收 %.1f MB",
                total,
                result["deleted_orphan"],
                result["deleted_stale"],
                result["bytes_freed"] / (1024 * 1024),
            )
    except (OSError, IOError, ValueError) as exc:
        logger.warning("checkpoint 自动维护失败：%s", exc)
        out["error"] = str(exc)

    return out


# ---------------------------------------------------------------------------
# 公共辅助函数
# ---------------------------------------------------------------------------

def store_status(checkpoint_base: Optional[Path] = None) -> Dict:
    """返回 shadow 存储的摘要。

    Args:
        checkpoint_base: checkpoint 基础目录

    Returns:
        {"base": path, "store_size_bytes": N, "legacy_size_bytes": N,
         "total_size_bytes": N, "project_count": N, "projects": [...],
         "legacy_archives": [...]}
    """
    base = checkpoint_base or _get_checkpoint_base()
    out: Dict = {
        "base": str(base),
        "store_size_bytes": 0,
        "legacy_size_bytes": 0,
        "total_size_bytes": 0,
        "project_count": 0,
        "projects": [],
        "legacy_archives": [],
    }
    if not base.exists():
        return out

    store = _store_path(base)
    if store.exists():
        out["store_size_bytes"] = _dir_size_bytes(store)
        if (store / "HEAD").exists():
            for meta in _list_projects(store):
                dir_hash = meta.get("_hash") or ""
                workdir = meta.get("workdir") or ""
                ref = _ref_name(dir_hash)
                ok, count_out, _ = _run_git(
                    ["rev-list", "--count", ref], store, str(base),
                    allowed_returncodes={128},
                )
                try:
                    commits = int(count_out) if ok else 0
                except ValueError:
                    commits = 0
                out["projects"].append({
                    "hash": dir_hash,
                    "workdir": workdir,
                    "exists": bool(workdir) and Path(workdir).exists(),
                    "created_at": meta.get("created_at"),
                    "last_touch": meta.get("last_touch"),
                    "commits": commits,
                })
    out["project_count"] = len(out["projects"])

    for child in base.iterdir():
        if child.is_dir() and child.name.startswith(_LEGACY_PREFIX):
            try:
                size = _dir_size_bytes(child)
            except OSError:
                size = 0
            out["legacy_size_bytes"] += size
            try:
                mt = child.stat().st_mtime
            except OSError:
                mt = 0
            out["legacy_archives"].append({
                "name": child.name,
                "size_bytes": size,
                "mtime": mt,
            })

    out["total_size_bytes"] = _dir_size_bytes(base)
    return out


def format_checkpoint_list(checkpoints: List[Dict], directory: str) -> str:
    """格式化 checkpoint 列表以便显示给用户。

    Args:
        checkpoints: checkpoint 列表
        directory: 目录路径

    Returns:
        格式化的字符串
    """
    if not checkpoints:
        return f"未找到 {directory} 的 checkpoint"

    lines = [f"📸 {directory} 的 checkpoint：\n"]
    for i, cp in enumerate(checkpoints, 1):
        ts = cp["timestamp"]
        if "T" in ts:
            ts = ts.split("T")[1].split("+")[0].split("-")[0][:5]
            date = cp["timestamp"].split("T")[0]
            ts = f"{date} {ts}"

        files = cp.get("files_changed", 0)
        ins = cp.get("insertions", 0)
        dele = cp.get("deletions", 0)
        if files:
            stat = f"  ({files} 个文件, +{ins}/-{dele})"
        else:
            stat = ""

        lines.append(f"  {i}. {cp['short_hash']}  {ts}  {cp['reason']}{stat}")

    lines.append("\n  /rollback <N>             恢复到 checkpoint N")
    lines.append("  /rollback diff <N>        预览自 checkpoint N 以来的变更")
    lines.append("  /rollback <N> <file>      从 checkpoint N 恢复单个文件")
    return "\n".join(lines)


__all__ = [
    "CheckpointManager",
    "DEFAULT_EXCLUDES",
    "prune_checkpoints",
    "maybe_auto_prune_checkpoints",
    "store_status",
    "format_checkpoint_list",
]
