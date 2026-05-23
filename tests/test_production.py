"""生产环境相关测试。"""

import io
import json
import logging

import pytest

from agentforge.utils.logging import (
    SensitiveDataFilter,
    JsonFormatter,
    setup_secure_logging,
)


class TestSensitiveDataFilter:
    """敏感信息过滤器测试。"""

    def test_filter_api_key(self):
        """测试 OpenAI API Key 被脱敏。"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="API Key: sk-1234567890abcdefghijklmn",
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        result = filter_obj.filter(record)

        assert result is True
        assert "sk-1234567890abcdefghijklmn" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_filter_bearer_token(self):
        """测试 Bearer Token 被脱敏。"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        filter_obj.filter(record)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_filter_password(self):
        """测试密码被脱敏。"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='Config: {"password": "my_secret_password"}',
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        filter_obj.filter(record)

        assert "my_secret_password" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_filter_url_credentials(self):
        """测试 URL 中的凭证被脱敏。"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting to postgres://admin:secretpass@db.example.com:5432/mydb",
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        filter_obj.filter(record)

        assert "secretpass" not in record.msg
        assert "admin" in record.msg  # 用户名保留
        assert "***@" in record.msg

    def test_normal_message_unchanged(self):
        """测试普通消息不被修改。"""
        original = "用户请求处理完成"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=original,
            args=(),
            exc_info=None,
        )

        filter_obj = SensitiveDataFilter()
        filter_obj.filter(record)

        assert record.msg == original


class TestJsonFormatter:
    """JSON 格式日志测试。"""

    def test_json_format(self):
        """测试 JSON 格式日志输出。"""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger("test_json_fmt")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("测试消息")

        output = stream.getvalue().strip()
        log_obj = json.loads(output)

        assert log_obj["level"] == "INFO"
        assert log_obj["message"] == "测试消息"
        assert log_obj["logger"] == "test_json_fmt"
        assert "timestamp" in log_obj

    def test_json_format_with_exception(self):
        """测试 JSON 格式包含异常信息。"""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger("test_json_exc")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        try:
            raise ValueError("测试异常")
        except ValueError:
            logger.exception("发生错误")

        output = stream.getvalue().strip()
        log_obj = json.loads(output)

        assert "exception" in log_obj
        assert "ValueError" in log_obj["exception"]


class TestSetupSecureLogging:
    """安全日志配置测试。"""

    def test_setup_with_sensitive_filter(self):
        """测试启用敏感信息过滤的日志配置。"""
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]

        try:
            setup_secure_logging(
                level="DEBUG",
                enable_sensitive_filter=True,
                enable_json_format=False,
            )

            # 验证处理器上有 SensitiveDataFilter
            has_filter = any(
                isinstance(f, SensitiveDataFilter)
                for h in root_logger.handlers
                for f in h.filters
            )
            assert has_filter is True
        finally:
            root_logger.handlers = original_handlers

    def test_setup_with_json_format(self):
        """测试启用 JSON 格式的日志配置。"""
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]

        try:
            setup_secure_logging(
                level="DEBUG",
                enable_sensitive_filter=False,
                enable_json_format=True,
            )

            # 验证处理器使用 JsonFormatter
            has_json = any(
                isinstance(h.formatter, JsonFormatter)
                for h in root_logger.handlers
            )
            assert has_json is True
        finally:
            root_logger.handlers = original_handlers