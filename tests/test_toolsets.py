"""工具集系统测试。"""

import os
from unittest.mock import patch

import pytest

from agentforge.tools.toolsets import (
    ToolsetDefinition,
    ToolsetRegistry,
    register_toolset,
    get_toolset,
    resolve_toolset,
)


class TestToolsetDefinition:
    """ToolsetDefinition 测试。"""

    def test_create_definition(self):
        """测试创建工具集定义。"""
        toolset = ToolsetDefinition(
            description="网络搜索工具",
            tools=["web_search", "web_extract"],
        )

        assert toolset.description == "网络搜索工具"
        assert "web_search" in toolset.tools
        assert toolset.is_available() is True

    def test_check_fn(self):
        """测试条件检查函数。"""
        toolset = ToolsetDefinition(
            description="需要网关的工具",
            tools=["send_message"],
            check_fn=lambda: False,
        )

        assert toolset.is_available() is False

    def test_requires_env(self):
        """测试环境变量要求。"""
        toolset = ToolsetDefinition(
            description="需要 API Key",
            tools=["api_call"],
            requires_env=["MY_API_KEY"],
        )

        # 没有设置环境变量
        assert toolset.is_available() is False

        # 设置环境变量后
        with patch.dict(os.environ, {"MY_API_KEY": "test"}):
            assert toolset.is_available() is True

    def test_includes(self):
        """测试包含其他工具集。"""
        toolset = ToolsetDefinition(
            description="完整工具集",
            tools=["extra_tool"],
            includes=["web"],
        )

        assert "web" in toolset.includes


class TestToolsetRegistry:
    """ToolsetRegistry 测试。"""

    def test_register_and_get(self):
        """测试注册和获取。"""
        registry = ToolsetRegistry()

        toolset = ToolsetDefinition(
            description="测试工具集",
            tools=["tool1", "tool2"],
        )

        registry.register("test", toolset)

        assert registry.get("test") == toolset

    def test_resolve_tools(self):
        """测试解析工具列表。"""
        registry = ToolsetRegistry()

        registry.register("base", ToolsetDefinition(
            description="基础工具",
            tools=["tool1"],
        ))

        registry.register("extended", ToolsetDefinition(
            description="扩展工具",
            tools=["tool2"],
            includes=["base"],
        ))

        tools = registry.resolve("extended")

        assert "tool1" in tools
        assert "tool2" in tools

    def test_resolve_circular(self):
        """测试循环引用检测。"""
        registry = ToolsetRegistry()

        registry.register("a", ToolsetDefinition(
            description="A",
            tools=["tool_a"],
            includes=["b"],
        ))

        registry.register("b", ToolsetDefinition(
            description="B",
            tools=["tool_b"],
            includes=["a"],
        ))

        # 不应该无限循环
        tools = registry.resolve("a")
        assert "tool_a" in tools

    def test_check_requirements(self):
        """测试要求检查。"""
        registry = ToolsetRegistry()

        registry.register("needs_key", ToolsetDefinition(
            description="需要 API Key",
            tools=["api_tool"],
            requires_env=["REQUIRED_API_KEY"],
        ))

        # 没有环境变量
        error = registry.check_requirements("needs_key")
        assert error is not None
        assert "REQUIRED_API_KEY" in error

    def test_list_available(self):
        """测试列出可用工具集。"""
        registry = ToolsetRegistry()

        registry.register("available", ToolsetDefinition(
            description="可用",
            tools=["tool1"],
        ))

        registry.register("unavailable", ToolsetDefinition(
            description="不可用",
            tools=["tool2"],
            check_fn=lambda: False,
        ))

        available = registry.list_available()

        assert "available" in available
        assert "unavailable" not in available


class TestGlobalRegistry:
    """全局注册表测试。"""

    def test_builtin_toolsets(self):
        """测试内置工具集已注册。"""
        # web 工具集应该存在
        web_toolset = get_toolset("web")
        assert web_toolset is not None
        assert web_toolset.description == "网络搜索和内容提取工具"

    def test_register_and_resolve(self):
        """测试注册和解析。"""
        # 注册自定义工具集
        register_toolset("custom_test", ToolsetDefinition(
            description="自定义测试工具集",
            tools=["custom_tool_1", "custom_tool_2"],
        ))

        # 解析
        tools = resolve_toolset("custom_test")
        assert "custom_tool_1" in tools
        assert "custom_tool_2" in tools
