"""Provider 客户端工厂。

创建和管理各 Provider 的 SDK 客户端实例。
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _build_keepalive_http_client(base_url: str = "") -> Optional[Any]:
    """构建带 TCP keepalive 的 HTTP 客户端。

    注入 TCP keepalives 以检测死连接，防止 socket 进入 CLOSE-WAIT 状态。
    空闲 30 秒后发送探测，每 10 秒重试，3 次后放弃 → 约 60 秒内检测到死连接。

    Args:
        base_url: API 基础 URL

    Returns:
        httpx.Client 实例，如果 httpx 未安装则返回 None
    """
    try:
        import httpx

        sock_opts = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]

        # Linux/Unix TCP keepalive 参数
        if hasattr(socket, "TCP_KEEPIDLE"):
            sock_opts.append((socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30))
            sock_opts.append((socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10))
            sock_opts.append((socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3))
        elif hasattr(socket, "TCP_KEEPALIVE"):
            # macOS 使用 TCP_KEEPALIVE
            sock_opts.append((socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 30))

        # 获取代理设置
        proxy = _get_proxy_for_base_url(base_url)

        return httpx.Client(
            transport=httpx.HTTPTransport(socket_options=sock_opts),
            proxy=proxy,
        )
    except ImportError:
        logger.debug("httpx 未安装，跳过 keepalive 配置")
        return None
    except (OSError, RuntimeError) as e:
        logger.debug(f"构建 keepalive HTTP 客户端失败: {e}")
        return None


def _get_proxy_for_base_url(base_url: str) -> Optional[str]:
    """获取指定 URL 的代理设置。

    从环境变量读取代理设置，同时尊重 NO_PROXY。

    Args:
        base_url: API 基础 URL

    Returns:
        代理 URL，如果没有代理则返回 None
    """
    if not base_url:
        base_url = ""

    # 检查是否是本地地址（不使用代理）
    try:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        hostname = parsed.hostname or ""

        # 本地地址不使用代理
        local_hosts = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        if hostname in local_hosts or hostname.startswith("192.168.") or hostname.startswith("10."):
            return None
    except ValueError:
        logger.debug("解析代理 URL 失败，跳过本地地址检查")

    # 从环境变量读取代理
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    all_proxy = os.getenv("ALL_PROXY") or os.getenv("all_proxy")

    # 检查 NO_PROXY
    no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    no_proxy_hosts = [h.strip().lower() for h in no_proxy.split(",") if h.strip()]

    try:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        hostname = (parsed.hostname or "").lower()

        for no_host in no_proxy_hosts:
            if hostname == no_host or hostname.endswith("." + no_host):
                return None
    except ValueError:
        logger.debug("解析 NO_PROXY 主机名失败，跳过 NO_PROXY 检查")

    return https_proxy or all_proxy or None


def create_openai_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    enable_keepalive: bool = True,
    **kwargs,
) -> Optional[Any]:
    """创建 OpenAI SDK 客户端。

    Args:
        api_key: API 密钥（可选，从环境变量获取）
        base_url: API 基础 URL（可选）
        timeout: 超时时间（秒）
        enable_keepalive: 是否启用 TCP keepalive
        **kwargs: 其他参数

    Returns:
        OpenAI 客户端实例，如果 SDK 未安装则返回 None
    """
    # 获取 API 密钥
    effective_key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not effective_key:
        logger.warning("OpenAI API 密钥未配置")
        return None

    try:
        from openai import OpenAI

        # 复制 kwargs 以防止修改原始字典
        client_kwargs = dict(kwargs)
        client_kwargs.update({
            "api_key": effective_key,
            "timeout": timeout,
        })

        if base_url:
            client_kwargs["base_url"] = base_url

        # 注入 TCP keepalive
        if enable_keepalive and "http_client" not in client_kwargs:
            keepalive_http = _build_keepalive_http_client(base_url)
            if keepalive_http is not None:
                client_kwargs["http_client"] = keepalive_http

        return OpenAI(**client_kwargs)

    except ImportError:
        logger.warning("openai 库未安装，请运行: pip install openai")
        return None
    except (ImportError, AttributeError, OSError, RuntimeError) as e:
        logger.error(f"创建 OpenAI 客户端失败: {e}")
        return None


def create_anthropic_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    enable_keepalive: bool = True,
    **kwargs,
) -> Optional[Any]:
    """创建 Anthropic SDK 客户端。

    Args:
        api_key: API 密钥（可选，从环境变量获取）
        base_url: API 基础 URL（可选）
        timeout: 超时时间（秒）
        enable_keepalive: 是否启用 TCP keepalive
        **kwargs: 其他参数

    Returns:
        Anthropic 客户端实例，如果 SDK 未安装则返回 None
    """
    # 获取 API 密钥
    effective_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not effective_key:
        logger.warning("Anthropic API 密钥未配置")
        return None

    try:
        from anthropic import Anthropic

        # 复制 kwargs 以防止修改原始字典
        client_kwargs = dict(kwargs)
        client_kwargs.update({
            "api_key": effective_key,
            "timeout": timeout,
        })

        if base_url:
            client_kwargs["base_url"] = base_url

        # Anthropic SDK 使用 httpx，可以注入 keepalive
        if enable_keepalive and "http_client" not in client_kwargs:
            keepalive_http = _build_keepalive_http_client(base_url)
            if keepalive_http is not None:
                client_kwargs["http_client"] = keepalive_http

        return Anthropic(**client_kwargs)

    except ImportError:
        logger.warning("anthropic 库未安装，请运行: pip install anthropic")
        return None
    except (ImportError, AttributeError, OSError, RuntimeError) as e:
        logger.error(f"创建 Anthropic 客户端失败: {e}")
        return None


def create_moonshot_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    enable_keepalive: bool = True,
    **kwargs,
) -> Optional[Any]:
    """创建 Moonshot (Kimi) SDK 客户端。

    Moonshot API 兼容 OpenAI 格式。

    Args:
        api_key: API 密钥（可选，从环境变量获取）
        base_url: API 基础 URL（可选）
        timeout: 超时时间（秒）
        enable_keepalive: 是否启用 TCP keepalive
        **kwargs: 其他参数

    Returns:
        OpenAI 客户端实例（指向 Moonshot API）
    """
    # 获取 API 密钥
    effective_key = api_key or os.getenv("MOONSHOT_API_KEY", "")
    if not effective_key:
        logger.warning("Moonshot API 密钥未配置")
        return None

    # Moonshot 默认端点
    effective_base_url = base_url or "https://api.moonshot.cn/v1"

    return create_openai_client(
        api_key=effective_key,
        base_url=effective_base_url,
        timeout=timeout,
        enable_keepalive=enable_keepalive,
        **kwargs,
    )


def create_qwen_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    enable_keepalive: bool = True,
    **kwargs,
) -> Optional[Any]:
    """创建通义千问 SDK 客户端。

    通义千问 API 兼容 OpenAI 格式。

    Args:
        api_key: API 密钥（可选，从环境变量获取）
        base_url: API 基础 URL（可选）
        timeout: 超时时间（秒）
        enable_keepalive: 是否启用 TCP keepalive
        **kwargs: 其他参数

    Returns:
        OpenAI 客户端实例（指向通义千问 API）
    """
    # 获取 API 密钥
    effective_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
    if not effective_key:
        logger.warning("通义千问 API 密钥未配置（DASHSCOPE_API_KEY）")
        return None

    # 通义千问默认端点
    effective_base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    return create_openai_client(
        api_key=effective_key,
        base_url=effective_base_url,
        timeout=timeout,
        enable_keepalive=enable_keepalive,
        **kwargs,
    )


def create_deepseek_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    enable_keepalive: bool = True,
    **kwargs,
) -> Optional[Any]:
    """创建 DeepSeek SDK 客户端。

    DeepSeek API 兼容 OpenAI 格式。

    Args:
        api_key: API 密钥（可选，从环境变量获取）
        base_url: API 基础 URL（可选）
        timeout: 超时时间（秒）
        enable_keepalive: 是否启用 TCP keepalive
        **kwargs: 其他参数

    Returns:
        OpenAI 客户端实例（指向 DeepSeek API）
    """
    # 获取 API 密钥
    effective_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not effective_key:
        logger.warning("DeepSeek API 密钥未配置")
        return None

    # DeepSeek 默认端点
    effective_base_url = base_url or "https://api.deepseek.com/v1"

    return create_openai_client(
        api_key=effective_key,
        base_url=effective_base_url,
        timeout=timeout,
        enable_keepalive=enable_keepalive,
        **kwargs,
    )


# Provider 到客户端工厂的映射
_CLIENT_FACTORY_MAP = {
    "openai": create_openai_client,
    "anthropic": create_anthropic_client,
    "moonshot": create_moonshot_client,
    "qwen": create_qwen_client,
    "deepseek": create_deepseek_client,
}


def create_client(
    provider: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    enable_keepalive: bool = True,
    **kwargs,
) -> Optional[Any]:
    """创建指定 Provider 的客户端。

    Args:
        provider: Provider 名称
        api_key: API 密钥
        base_url: API 基础 URL
        timeout: 超时时间
        enable_keepalive: 是否启用 TCP keepalive
        **kwargs: 其他参数

    Returns:
        SDK 客户端实例
    """
    factory = _CLIENT_FACTORY_MAP.get(provider.lower())
    if factory is None:
        logger.warning(f"未知的 Provider: {provider}")
        return None

    return factory(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        enable_keepalive=enable_keepalive,
        **kwargs,
    )


__all__ = [
    "create_openai_client",
    "create_anthropic_client",
    "create_moonshot_client",
    "create_qwen_client",
    "create_deepseek_client",
    "create_client",
    "_build_keepalive_http_client",
]