"""P7-P8 阶段单元测试：内置实现与工具函数。"""

import pytest
import tempfile
import logging
from pathlib import Path

from agentforge.providers.builtins import (
    OpenAIProvider,
    AnthropicProvider,
    MoonshotProvider,
    QwenProvider,
    DeepSeekProvider,
)
from agentforge.tools.builtins import (
    DelegateTool,
    ShellTool,
    FileReadTool,
    FileWriteTool,
    WebFetchTool,
)
from agentforge.utils import (
    get_platform,
    is_windows,
    is_linux,
    is_macos,
    get_home_dir,
    get_temp_dir,
    setup_logging,
    get_logger,
)
from agentforge.types import NormalizedResponse


# ── Provider 测试 ──────────────────────────────────────────────

class TestOpenAIProvider:
    """OpenAIProvider 测试。"""

    def test_create_provider(self):
        """测试创建 Provider。"""
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4",
        )

        assert provider.name == "openai"
        assert provider._model == "gpt-4"

    def test_capabilities(self):
        """测试能力。"""
        provider = OpenAIProvider(api_key="test-key")

        caps = provider.capabilities
        assert caps.supports_tools is True
        assert caps.supports_streaming is True
        assert caps.supports_vision is True

    def test_supports(self):
        """测试支持检查。"""
        provider = OpenAIProvider(api_key="test-key")

        assert provider.supports("tools")
        assert provider.supports("streaming")
        assert not provider.supports("reasoning")

    def test_mock_stream(self):
        """测试模拟流式响应。"""
        provider = OpenAIProvider(api_key="test-key")

        # 使用 stream 方法获取响应
        for response in provider.stream([{"role": "user", "content": "test"}]):
            assert response.content is not None
            break

    def test_to_dict(self):
        """测试转换为字典。"""
        provider = OpenAIProvider(api_key="test-key", model="gpt-4")

        d = provider.to_dict()
        assert d["name"] == "openai"
        assert d["model"] == "gpt-4"


class TestAnthropicProvider:
    """AnthropicProvider 测试。"""

    def test_create_provider(self):
        """测试创建 Provider。"""
        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-3-opus",
        )

        assert provider.name == "anthropic"
        assert provider._model == "claude-3-opus"

    def test_capabilities(self):
        """测试能力。"""
        provider = AnthropicProvider(api_key="test-key")

        caps = provider.capabilities
        assert caps.supports_tools is True
        assert caps.supports_caching is True

    def test_convert_messages(self):
        """测试消息转换。"""
        provider = AnthropicProvider(api_key="test-key")

        messages = [{"role": "user", "content": "Hello"}]
        converted = provider._convert_messages(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "user"


class TestMoonshotProvider:
    """MoonshotProvider 测试。"""

    def test_create_provider(self):
        """测试创建 Provider。"""
        provider = MoonshotProvider(
            api_key="test-key",
            model="moonshot-v1-8k",
        )

        assert provider.name == "moonshot"
        assert provider._model == "moonshot-v1-8k"

    def test_capabilities(self):
        """测试能力。"""
        provider = MoonshotProvider(api_key="test-key")

        caps = provider.capabilities
        assert caps.supports_tools is True
        assert caps.supports_streaming is True


class TestQwenProvider:
    """QwenProvider 测试。"""

    def test_create_provider(self):
        """测试创建 Provider。"""
        provider = QwenProvider(
            api_key="test-key",
            model="qwen-turbo",
        )

        assert provider.name == "qwen"
        assert provider._model == "qwen-turbo"

    def test_capabilities(self):
        """测试能力。"""
        provider = QwenProvider(api_key="test-key")

        caps = provider.capabilities
        assert caps.supports_vision is True


class TestDeepSeekProvider:
    """DeepSeekProvider 测试。"""

    def test_create_provider(self):
        """测试创建 Provider。"""
        provider = DeepSeekProvider(
            api_key="test-key",
            model="deepseek-chat",
        )

        assert provider.name == "deepseek"
        assert provider._model == "deepseek-chat"

    def test_reasoner_capability(self):
        """测试推理能力。"""
        provider = DeepSeekProvider(
            api_key="test-key",
            model="deepseek-reasoner",
        )

        caps = provider.capabilities
        assert caps.supports_reasoning is True


# ── 内置工具测试 ──────────────────────────────────────────────

class TestDelegateTool:
    """DelegateTool 测试。"""

    def test_create_tool(self):
        """测试创建工具。"""
        tool = DelegateTool()

        assert tool.name == "delegate_task"
        assert tool.timeout == 600.0

    def test_parameters(self):
        """测试参数定义。"""
        tool = DelegateTool()

        params = tool.parameters
        assert "goal" in params["properties"]
        assert "goal" in params["required"]

    def test_execute_without_manager(self):
        """测试无管理器执行。"""
        tool = DelegateTool()

        result = tool.execute("call-1", goal="测试任务")

        assert result.is_error
        assert "委托管理器未配置" in result.content


class TestShellTool:
    """ShellTool 测试。"""

    def test_create_tool(self):
        """测试创建工具。"""
        tool = ShellTool()

        assert tool.name == "shell"
        assert tool.dangerous is True
        assert tool.requires_approval is True

    def test_should_approve_dangerous(self):
        """测试危险命令审批。"""
        tool = ShellTool()

        assert tool.should_approve({"command": "rm -rf /"})
        assert tool.should_approve({"command": "dd if=/dev/zero"})

    def test_should_approve_safe(self):
        """测试安全命令。"""
        tool = ShellTool()

        # 安全命令仍需审批（因为 requires_approval=True）
        assert tool.should_approve({"command": "ls -la"})


class TestFileReadTool:
    """FileReadTool 测试。"""

    def test_create_tool(self):
        """测试创建工具。"""
        tool = FileReadTool()

        assert tool.name == "file_read"
        assert not tool.dangerous

    def test_read_file(self):
        """测试读取文件。"""
        tool = FileReadTool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("测试内容")
            f.flush()

            result = tool.execute("call-1", path=f.name)

            assert not result.is_error
            assert "测试内容" in result.content

    def test_read_nonexistent_file(self):
        """测试读取不存在的文件。"""
        tool = FileReadTool()

        result = tool.execute("call-1", path="/nonexistent/file.txt")

        assert result.is_error
        assert "文件不存在" in result.content


class TestFileWriteTool:
    """FileWriteTool 测试。"""

    def test_create_tool(self):
        """测试创建工具。"""
        tool = FileWriteTool()

        assert tool.name == "file_write"
        assert tool.dangerous is True

    def test_write_file(self):
        """测试写入文件。"""
        tool = FileWriteTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"

            result = tool.execute("call-1", path=str(file_path), content="测试内容")

            assert not result.is_error
            assert file_path.exists()
            assert file_path.read_text(encoding="utf-8") == "测试内容"


class TestWebFetchTool:
    """WebFetchTool 测试。"""

    def test_create_tool(self):
        """测试创建工具。"""
        tool = WebFetchTool()

        assert tool.name == "web_fetch"
        assert not tool.dangerous

    def test_parameters(self):
        """测试参数定义。"""
        tool = WebFetchTool()

        params = tool.parameters
        assert "url" in params["properties"]
        assert "url" in params["required"]


# ── 工具函数测试 ──────────────────────────────────────────────

class TestPlatform:
    """平台检测测试。"""

    def test_get_platform(self):
        """测试获取平台。"""
        platform = get_platform()

        assert platform in ["windows", "linux", "macos"]

    def test_is_windows(self):
        """测试 Windows 检测。"""
        result = is_windows()
        # 根据实际环境判断
        assert isinstance(result, bool)

    def test_is_linux(self):
        """测试 Linux 检测。"""
        result = is_linux()
        assert isinstance(result, bool)

    def test_is_macos(self):
        """测试 macOS 检测。"""
        result = is_macos()
        assert isinstance(result, bool)

    def test_get_home_dir(self):
        """测试获取主目录。"""
        home = get_home_dir()

        assert home.exists()
        assert home.is_dir()

    def test_get_temp_dir(self):
        """测试获取临时目录。"""
        temp = get_temp_dir()

        assert temp.exists()
        assert temp.is_dir()


class TestLogging:
    """日志配置测试。"""

    def test_setup_logging(self):
        """测试配置日志。"""
        setup_logging(level="INFO")

        logger = get_logger("test")
        assert logger is not None

    def test_get_logger(self):
        """测试获取日志器。"""
        logger = get_logger("agentforge.test")

        assert logger.name == "agentforge.test"

    def test_set_log_level(self):
        """测试设置日志级别。"""
        from agentforge.utils.logging import set_log_level

        set_log_level("DEBUG")

        logger = logging.getLogger()
        assert logger.level == logging.DEBUG


# ── 集成测试 ──────────────────────────────────────────────

class TestP7P8Integration:
    """P7-P8 阶段集成测试。"""

    def test_provider_and_tools_integration(self):
        """测试 Provider 与工具集成。"""
        # 创建 Provider
        provider = OpenAIProvider(api_key="test-key", model="gpt-4")

        # 创建工具
        shell_tool = ShellTool()

        # 验证能力
        assert provider.supports("tools")
        assert shell_tool.dangerous

    def test_utils_with_file_tools(self):
        """测试工具函数与文件工具集成。"""
        tool = FileWriteTool()

        temp_dir = get_temp_dir()
        test_file = temp_dir / "test_integration.txt"

        result = tool.execute("call-1", path=str(test_file), content="集成测试")

        assert not result.is_error