"""敏感信息管理。

提供敏感信息的安全存储和脱敏功能。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional

from pydantic import SecretStr


# 敏感字段名称（用于日志脱敏）
SENSITIVE_FIELD_NAMES: FrozenSet[str] = frozenset([
    "api_key",
    "token",
    "password",
    "secret",
    "authorization",
    "credential",
    "api_key_id",
    "access_key",
    "secret_key",
    "private_key",
    "session_token",
])


@dataclass
class SecretManager:
    """敏感信息管理器。

    功能：
    - 安全存储敏感信息（API 密钥、令牌等）
    - 日志脱敏：从文本中移除敏感信息
    - 环境变量管理

    使用示例：
        manager = SecretManager()
        manager.set("openai_api_key", "sk-xxx")
        manager.get("openai_api_key")  # 返回 "sk-xxx"
        manager.redact("使用 sk-xxx 调用 API")  # 返回 "使用 [openai_api_key_REDACTED] 调用 API"
    """
    _secrets: Dict[str, SecretStr] = field(default_factory=dict)

    def set(self, key: str, value: str) -> None:
        """存储敏感信息。"""
        self._secrets[key] = SecretStr(value)

    def get(self, key: str) -> Optional[str]:
        """获取敏感信息。"""
        secret = self._secrets.get(key)
        return secret.get_secret_value() if secret else None

    def delete(self, key: str) -> None:
        """删除敏感信息。"""
        self._secrets.pop(key, None)

    def exists(self, key: str) -> bool:
        """检查敏感信息是否存在。"""
        return key in self._secrets

    def redact(self, text: str) -> str:
        """从文本中移除敏感信息。

        将所有已存储的敏感值替换为 [key_REDACTED] 格式。

        参数：
            text: 原始文本

        返回：
            脱敏后的文本
        """
        for key, secret in self._secrets.items():
            value = secret.get_secret_value()
            if value and value in text:
                text = text.replace(value, f"[{key}_REDACTED]")
        return text

    def redact_dict(self, data: Dict) -> Dict:
        """脱敏字典中的敏感字段。

        将敏感字段名称对应的值替换为 ***REDACTED***。

        参数：
            data: 原始字典

        返回：
            脱敏后的字典
        """
        result = {}
        for key, value in data.items():
            if key.lower() in SENSITIVE_FIELD_NAMES:
                result[key] = "***REDACTED***"
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value)
            elif isinstance(value, str):
                result[key] = self.redact(value)
            else:
                result[key] = value
        return result

    def load_from_env(self, prefix: str = "") -> None:
        """从环境变量加载敏感信息。

        扫描环境变量中匹配敏感字段名称的变量，存储到管理器。

        参数：
            prefix: 环境变量前缀（如 "OPENAI_"）
        """
        import os

        for key, value in os.environ.items():
            # 检查是否为敏感字段
            key_lower = key.lower()
            for sensitive in SENSITIVE_FIELD_NAMES:
                if sensitive in key_lower:
                    # 存储到管理器（移除前缀）
                    storage_key = key[len(prefix):] if prefix and key.startswith(prefix) else key
                    self.set(storage_key.lower(), value)
                    break

    def clear(self) -> None:
        """清空所有敏感信息。"""
        self._secrets.clear()


def redact_sensitive(text: str, patterns: Optional[FrozenSet[str]] = None) -> str:
    """脱敏文本中的敏感信息。

    使用正则表达式匹配常见敏感模式进行脱敏。

    参数：
        text: 原始文本
        patterns: 自定义敏感模式（可选）

    返回：
        脱敏后的文本
    """
    if patterns is None:
        patterns = frozenset([
            # API 密钥模式
            r"sk-[a-zA-Z0-9]{20,}",
            r"sk_live_[a-zA-Z0-9]{20,}",
            r"sk_test_[a-zA-Z0-9]{20,}",
            # Bearer Token
            r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*",
            # AWS 密钥
            r"AKIA[A-Z0-9]{16}",
            # JWT Token
            r"eyJ[a-zA-Z0-9\-._~+/]+=*\.eyJ[a-zA-Z0-9\-._~+/]+=*\.[a-zA-Z0-9\-._~+/]+=*",
        ])

    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)

    return text
