"""平台检测与兼容。

提供跨平台兼容性支持。
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_platform() -> str:
    """获取当前平台名称。

    Returns:
        平台名称：windows、linux、macos
    """
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "linux":
        return "linux"
    elif system == "darwin":
        return "macos"
    else:
        return system


def is_windows() -> bool:
    """检查是否是 Windows 系统。

    Returns:
        True 如果是 Windows
    """
    return get_platform() == "windows"


def is_linux() -> bool:
    """检查是否是 Linux 系统。

    Returns:
        True 如果是 Linux
    """
    return get_platform() == "linux"


def is_macos() -> bool:
    """检查是否是 macOS 系统。

    Returns:
        True 如果是 macOS
    """
    return get_platform() == "macos"


def get_home_dir() -> Path:
    """获取用户主目录。

    Returns:
        用户主目录路径
    """
    if is_windows():
        # Windows: 使用 USERPROFILE
        home = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
    else:
        # Linux/macOS: 使用 HOME
        home = os.environ.get("HOME", "")

    if not home:
        # 回退到 Path.home()
        home = str(Path.home())

    return Path(home)


def get_temp_dir() -> Path:
    """获取临时目录。

    Returns:
        临时目录路径
    """
    if is_windows():
        temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
    else:
        temp = "/tmp"

    if not temp:
        import tempfile
        temp = tempfile.gettempdir()

    return Path(temp)


def get_app_data_dir(app_name: str = "hai_agent") -> Path:
    """获取应用数据目录。

    Args:
        app_name: 应用名称

    Returns:
        应用数据目录路径
    """
    home = get_home_dir()

    if is_windows():
        # Windows: 使用 AppData/Local
        base = os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")
        return Path(base) / app_name
    elif is_macos():
        # macOS: 使用 ~/Library/Application Support
        return home / "Library" / "Application Support" / app_name
    else:
        # Linux: 使用 ~/.local/share
        return home / ".local" / "share" / app_name


def get_config_dir(app_name: str = "hai_agent") -> Path:
    """获取配置目录。

    Args:
        app_name: 应用名称

    Returns:
        配置目录路径
    """
    home = get_home_dir()

    if is_windows():
        # Windows: 使用 AppData/Roaming
        base = os.environ.get("APPDATA", home / "AppData" / "Roaming")
        return Path(base) / app_name
    elif is_macos():
        # macOS: 使用 ~/Library/Preferences
        return home / "Library" / "Preferences" / app_name
    else:
        # Linux: 使用 ~/.config
        return home / ".config" / app_name


def ensure_dir(path: Path) -> Path:
    """确保目录存在。

    Args:
        path: 目录路径

    Returns:
        目录路径
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_path(path: str) -> Path:
    """规范化路径。

    Args:
        path: 路径字符串

    Returns:
        规范化的 Path 对象
    """
    # 处理 Windows 路径分隔符
    if is_windows():
        path = path.replace("/", "\\")

    # 处理用户主目录
    if path.startswith("~"):
        path = str(get_home_dir()) + path[1:]

    return Path(path).resolve()