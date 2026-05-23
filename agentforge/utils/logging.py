"""日志配置。

提供统一的日志配置，支持敏感信息过滤和结构化日志。
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    date_format: str = "%Y-%m-%d %H:%M:%S",
) -> None:
    """配置日志系统。

    Args:
        level: 日志级别（DEBUG、INFO、WARNING、ERROR、CRITICAL）
        log_file: 日志文件路径（可选）
        format: 日志格式
        date_format: 时间格式
    """
    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除现有处理器
    root_logger.handlers.clear()

    # 创建格式器
    formatter = logging.Formatter(format, datefmt=date_format)

    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 添加文件处理器（如果指定）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def setup_secure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    enable_sensitive_filter: bool = True,
    enable_json_format: bool = False,
) -> None:
    """配置安全的日志系统。

    Args:
        level: 日志级别
        log_file: 日志文件路径
        enable_sensitive_filter: 是否启用敏感信息过滤
        enable_json_format: 是否使用 JSON 格式
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    if enable_json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    if enable_sensitive_filter:
        console_handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        if enable_sensitive_filter:
            file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取日志器。

    Args:
        name: 日志器名称

    Returns:
        Logger 实例
    """
    return logging.getLogger(name)


def set_log_level(level: str) -> None:
    """设置日志级别。

    Args:
        level: 日志级别
    """
    logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))


class SensitiveDataFilter:
    """日志敏感信息过滤器。

    自动脱敏日志中的 API Key、Token、密码等敏感信息。
    """

    PATTERNS: List[tuple] = [
        # API Keys (OpenAI, Anthropic 等)
        (r'sk-[a-zA-Z0-9]{20,}', 'sk-***REDACTED***'),
        (r'api[_-]?key["\s:=]+["\']?([a-zA-Z0-9_-]{20,})', 'api_key=***REDACTED***'),
        # Bearer Tokens
        (r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}', 'Bearer ***REDACTED***'),
        # JWT
        (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', '***JWT_REDACTED***'),
        # 密码
        (r'password["\s:=]+["\']?([^\s"\',}]+)', 'password=***REDACTED***'),
        (r'passwd["\s:=]+["\']?([^\s"\',}]+)', 'passwd=***REDACTED***'),
        # 连接字符串中的凭证
        (r'://([^:]+):([^@]+)@', r'://\1:***@'),
    ]

    def __init__(self):
        """初始化过滤器，编译正则表达式。"""
        self._compiled: List[tuple] = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.PATTERNS
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录中的敏感信息。

        修改 record.msg 为脱敏后的内容，始终返回 True 允许日志通过。

        Args:
            record: 日志记录

        Returns:
            始终返回 True
        """
        msg = record.getMessage()

        for pattern, replacement in self._compiled:
            msg = pattern.sub(replacement, msg)

        record.msg = msg
        record.args = ()

        return True


class JsonFormatter(logging.Formatter):
    """JSON 格式日志格式器。"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化为 JSON 字符串。"""
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


class LoggerAdapter(logging.LoggerAdapter):
    """日志适配器，添加额外上下文。"""

    def process(self, msg, kwargs):
        """处理日志消息。"""
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def create_context_logger(
    logger: logging.Logger,
    context: dict,
) -> LoggerAdapter:
    """创建带上下文的日志器。

    Args:
        logger: 基础日志器
        context: 上下文信息

    Returns:
        LoggerAdapter 实例
    """
    return LoggerAdapter(logger, context)