"""TODO 项实现测试。"""

import pytest
from unittest.mock import MagicMock, patch
import base64
import io

from agentforge.types import Message, ImageContent, TextContent
from agentforge.core.execution import ExecutionEngine, ExecutionConfig
from agentforge.delegation.manager import DelegationManager
from agentforge.delegation.config import DelegationConfig, TaskSpec
from agentforge.tools.toolsets import register_toolset, ToolsetDefinition, _global_registry


class TestImageShrink:
    """测试图片缩小功能。"""

    def test_shrink_images_with_pil(self):
        """测试使用 PIL 缩小图片。"""
        try:
            from PIL import Image as PILImage
        except ImportError:
            pytest.skip("Pillow 未安装")

        # 创建一个小测试图片
        pil_img = PILImage.new("RGB", (2000, 2000), color="red")
        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # 创建消息
        image_content = ImageContent(base64=image_base64, media_type="image/png")
        message = Message(role="user", content=[image_content])

        # 创建执行引擎
        mock_provider = MagicMock()
        engine = ExecutionEngine(provider=mock_provider)

        # 调用缩小方法
        shrunk_messages = engine._shrink_images([message], max_dimension=1024)

        # 验证结果
        assert len(shrunk_messages) == 1
        assert isinstance(shrunk_messages[0].content, list)
        # 图片应该被缩小
        shrunk_image = shrunk_messages[0].content[0]
        assert isinstance(shrunk_image, ImageContent)
        assert shrunk_image.base64 is not None

    def test_shrink_images_url_image(self):
        """测试 URL 图片处理（应被移除）。"""
        # 创建带 URL 图片的消息
        image_content = ImageContent(url="https://example.com/image.png")
        message = Message(role="user", content=[image_content])

        mock_provider = MagicMock()
        engine = ExecutionEngine(provider=mock_provider)

        # 调用缩小方法
        shrunk_messages = engine._shrink_images([message])

        # URL 图片应被替换为文本
        assert len(shrunk_messages) == 1
        assert isinstance(shrunk_messages[0].content, list)
        assert isinstance(shrunk_messages[0].content[0], TextContent)
        assert "移除" in shrunk_messages[0].content[0].text

    def test_shrink_images_text_only(self):
        """测试纯文本消息（无需处理）。"""
        message = Message(role="user", content="这是纯文本")

        mock_provider = MagicMock()
        engine = ExecutionEngine(provider=mock_provider)

        shrunk_messages = engine._shrink_images([message])

        assert len(shrunk_messages) == 1
        assert shrunk_messages[0].content == "这是纯文本"

    def test_shrink_without_pil(self):
        """测试无 PIL 时的处理。"""
        message = Message(
            role="user",
            content=[ImageContent(base64="aGVsbG8=", media_type="image/png")]
        )

        mock_provider = MagicMock()
        engine = ExecutionEngine(provider=mock_provider)

        with patch.dict("sys.modules", {"PIL": None}):
            shrunk_messages = engine._shrink_images([message])

        # 无 PIL 时图片应被替换
        assert isinstance(shrunk_messages[0].content[0], TextContent)


class TestToolsetFilter:
    """测试工具集过滤功能。"""

    def test_filter_by_toolset(self):
        """测试按工具集过滤工具。"""
        # 注册测试工具集
        register_toolset("test_tools", ToolsetDefinition(
            description="测试工具集",
            tools=["tool_a", "tool_b"],
        ))

        # 创建模拟父 Agent
        mock_parent = MagicMock()
        mock_tool_a = MagicMock()
        mock_tool_a.name = "tool_a"
        mock_tool_b = MagicMock()
        mock_tool_b.name = "tool_b"
        mock_tool_c = MagicMock()
        mock_tool_c.name = "tool_c"

        mock_parent._tools = {
            "tool_a": mock_tool_a,
            "tool_b": mock_tool_b,
            "tool_c": mock_tool_c,
        }

        # 创建委托管理器
        config = DelegationConfig()
        manager = DelegationManager(config=config, parent_agent=mock_parent)

        # 创建任务规格，指定工具集
        task = TaskSpec(
            goal="测试任务",
            toolsets=["test_tools"],
        )

        # 构建子工具
        child_tools = manager._build_child_tools(task)

        # 验证只有 tool_a 和 tool_b
        tool_names = {t.name for t in child_tools}
        assert tool_names == {"tool_a", "tool_b"}

    def test_filter_with_blocked_tools(self):
        """测试工具集过滤与阻止工具组合。"""
        # 注册测试工具集
        register_toolset("all_tools", ToolsetDefinition(
            description="所有工具",
            tools=["tool_a", "tool_b", "tool_c"],
        ))

        # 创建模拟父 Agent
        mock_parent = MagicMock()
        mock_tool_a = MagicMock()
        mock_tool_a.name = "tool_a"
        mock_tool_b = MagicMock()
        mock_tool_b.name = "tool_b"
        mock_tool_c = MagicMock()
        mock_tool_c.name = "tool_c"

        mock_parent._tools = {
            "tool_a": mock_tool_a,
            "tool_b": mock_tool_b,
            "tool_c": mock_tool_c,
        }

        # 创建配置，阻止 tool_b
        config = DelegationConfig()
        config.isolation.blocked_tools = frozenset(["tool_b"])

        manager = DelegationManager(config=config, parent_agent=mock_parent)

        task = TaskSpec(goal="测试任务", toolsets=["all_tools"])
        child_tools = manager._build_child_tools(task)

        # 验证只有 tool_a 和 tool_c（tool_b 被阻止）
        tool_names = {t.name for t in child_tools}
        assert tool_names == {"tool_a", "tool_c"}

    def test_no_toolset_specified(self):
        """测试未指定工具集时继承所有工具。"""
        mock_parent = MagicMock()
        mock_tool_a = MagicMock()
        mock_tool_a.name = "tool_a"
        mock_tool_b = MagicMock()
        mock_tool_b.name = "tool_b"

        mock_parent._tools = {
            "tool_a": mock_tool_a,
            "tool_b": mock_tool_b,
        }

        config = DelegationConfig()
        manager = DelegationManager(config=config, parent_agent=mock_parent)

        task = TaskSpec(goal="测试任务")  # 无 toolsets
        child_tools = manager._build_child_tools(task)

        # 应继承所有工具
        assert len(child_tools) == 2

    def test_multiple_toolsets(self):
        """测试多个工具集组合。"""
        register_toolset("set_a", ToolsetDefinition(
            description="工具集 A",
            tools=["tool_a"],
        ))
        register_toolset("set_b", ToolsetDefinition(
            description="工具集 B",
            tools=["tool_b"],
        ))

        mock_parent = MagicMock()
        mock_tool_a = MagicMock()
        mock_tool_a.name = "tool_a"
        mock_tool_b = MagicMock()
        mock_tool_b.name = "tool_b"
        mock_tool_c = MagicMock()
        mock_tool_c.name = "tool_c"

        mock_parent._tools = {
            "tool_a": mock_tool_a,
            "tool_b": mock_tool_b,
            "tool_c": mock_tool_c,
        }

        config = DelegationConfig()
        manager = DelegationManager(config=config, parent_agent=mock_parent)

        task = TaskSpec(goal="测试任务", toolsets=["set_a", "set_b"])
        child_tools = manager._build_child_tools(task)

        # 应包含两个工具集的工具
        tool_names = {t.name for t in child_tools}
        assert tool_names == {"tool_a", "tool_b"}
