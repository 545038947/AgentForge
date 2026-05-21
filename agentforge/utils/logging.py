"""日志配置。

提供统一的日志配置。
"""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path
from typing import Optional


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