"""Demo 公共工具函数。

提供通用的检查和创建函数，避免代码重复。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

# Windows 终端编码设置
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 添加项目根目录到路径（用于场景脚本）
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agentforge import Agent
from agentforge.providers.builtins.ollama import OllamaProvider
from demo.config import DemoConfig, get_config


def check_ollama(base_url: str) -> bool:
    """检查 Ollama 服务是否可用。

    Args:
        base_url: Ollama 服务地址

    Returns:
        是否可用
    """
    import requests

    # 提取基础 URL（去掉 /v1）
    check_url = base_url.rstrip("/v1")
    try:
        response = requests.get(f"{check_url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def list_available_models(base_url: str) -> list:
    """列出可用模型。

    Args:
        base_url: Ollama 服务地址

    Returns:
        模型名称列表
    """
    import requests

    check_url = base_url.rstrip("/v1")
    try:
        response = requests.get(f"{check_url}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return []


def create_agent(
    config: Optional[DemoConfig] = None,
    tools: Optional[list] = None,
) -> Tuple[Agent, DemoConfig]:
    """创建 Agent 实例。

    Args:
        config: 配置实例（可选，默认从配置文件加载）
        tools: 工具列表（可选）

    Returns:
        (Agent, DemoConfig) 元组
    """
    if config is None:
        config = get_config()

    provider = OllamaProvider(
        model=config.ollama.model,
        base_url=config.ollama.base_url,
        timeout=config.ollama.timeout,
    )

    agent = Agent(
        provider=provider,
        tools=tools or [],
    )

    return agent, config


def setup_demo(
    config_path: Optional[str] = None,
) -> Tuple[Agent, DemoConfig]:
    """设置 Demo 环境。

    包含：
    - 加载配置
    - 检查 Ollama 服务
    - 创建 Agent

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        (Agent, DemoConfig) 元组

    Raises:
        SystemExit: 如果 Ollama 服务不可用
    """
    from demo.config import reload_config

    # 加载配置
    config = reload_config(config_path)

    # 检查 Ollama
    if not check_ollama(config.ollama.base_url):
        print("\n❌ 错误: Ollama 服务未运行")
        print(f"   检查地址: {config.ollama.base_url.rstrip('/v1')}")
        print("\n请先启动 Ollama:")
        print("  ollama serve")
        sys.exit(1)

    print("✅ Ollama 服务已连接")

    # 创建 Agent
    agent, config = create_agent(config)

    return agent, config


def print_section(title: str):
    """打印分节标题。

    Args:
        title: 标题文本
    """
    print("\n" + "=" * 50)
    print(f"=== {title} ===")
    print("=" * 50)
