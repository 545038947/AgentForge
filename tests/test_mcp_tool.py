"""MCPTool 包装器单元测试。"""

import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from hai_agent.mcp.tool import MCPTool
from hai_agent.mcp.types import MCPToolSchema
from hai_agent.types import ToolResult


@pytest.fixture(autouse=True)
def _reset_mcp_pool():
    """确保每个测试前连接池为 None，避免类变量污染。"""
    MCPTool.set_pool(None)
    yield
    MCPTool.set_pool(None)


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_schema(
    name: str = "test_tool",
    description: str = "测试工具",
    inputSchema: dict | None = None,
) -> MCPToolSchema:
    """创建一个 MCPToolSchema 实例。"""
    if inputSchema is None:
        inputSchema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询关键词"},
                "limit": {"type": "integer", "description": "结果数量"},
            },
            "required": ["query"],
        }
    return MCPToolSchema(name=name, description=description, inputSchema=inputSchema)


def _make_client(name: str = "test-server") -> MagicMock:
    """创建一个模拟 MCPClient 的 Mock 对象。"""
    client = MagicMock()
    client.name = name
    return client


def _make_mcp_tool(
    schema: MCPToolSchema | None = None,
    client: MagicMock | None = None,
) -> MCPTool:
    """创建一个 MCPTool 实例。"""
    if schema is None:
        schema = _make_schema()
    if client is None:
        client = _make_client()
    return MCPTool(client=client, schema=schema)


# ---------------------------------------------------------------------------
# 属性测试
# ---------------------------------------------------------------------------

class TestMCPToolProperties:
    """测试 MCPTool 的属性代理。"""

    def test_name_from_schema(self):
        """name 属性应来自 schema。"""
        schema = _make_schema(name="search")
        tool = _make_mcp_tool(schema=schema)
        assert tool.name == "search"

    def test_description_from_schema(self):
        """description 属性应来自 schema。"""
        schema = _make_schema(description="搜索工具")
        tool = _make_mcp_tool(schema=schema)
        assert tool.description == "搜索工具"

    def test_parameters_from_schema(self):
        """parameters 属性应来自 schema 的 inputSchema。"""
        input_schema = {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        }
        schema = _make_schema(inputSchema=input_schema)
        tool = _make_mcp_tool(schema=schema)
        assert tool.parameters is input_schema
        assert tool.parameters["required"] == ["key"]

    def test_parameters_empty_schema(self):
        """inputSchema 为空字典时 parameters 也应为空字典。"""
        schema = _make_schema(inputSchema={})
        tool = _make_mcp_tool(schema=schema)
        assert tool.parameters == {}


# ---------------------------------------------------------------------------
# get_schema 测试
# ---------------------------------------------------------------------------

class TestMCPToolGetSchema:
    """测试 MCPTool.get_schema()。"""

    def test_get_schema_returns_dict(self):
        """get_schema 应返回包含 name/description/input_schema 的字典。"""
        input_schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        }
        schema = _make_schema(name="find", description="查找", inputSchema=input_schema)
        tool = _make_mcp_tool(schema=schema)

        result = tool.get_schema()
        assert isinstance(result, dict)
        assert result["name"] == "find"
        assert result["description"] == "查找"
        assert result["input_schema"] is input_schema

    def test_get_schema_keys(self):
        """get_schema 返回的字典应恰好包含 name、description、input_schema 三个键。"""
        tool = _make_mcp_tool()
        result = tool.get_schema()
        assert set(result.keys()) == {"name", "description", "input_schema"}


# ---------------------------------------------------------------------------
# validate_parameters 测试
# ---------------------------------------------------------------------------

class TestMCPToolValidateParameters:
    """测试 MCPTool.validate_parameters()。"""

    def test_valid_params_with_all_required(self):
        """提供所有必填参数时应返回 True。"""
        tool = _make_mcp_tool()  # required: ["query"]
        assert tool.validate_parameters({"query": "hello"}) is True

    def test_valid_params_with_optional(self):
        """提供必填 + 可选参数时应返回 True。"""
        tool = _make_mcp_tool()  # required: ["query"], optional: ["limit"]
        assert tool.validate_parameters({"query": "hello", "limit": 10}) is True

    def test_missing_required_param(self):
        """缺少必填参数时应返回 False。"""
        tool = _make_mcp_tool()  # required: ["query"]
        assert tool.validate_parameters({"limit": 10}) is False

    def test_extra_params_allowed(self):
        """多余参数不应导致验证失败。"""
        tool = _make_mcp_tool()  # required: ["query"]
        assert tool.validate_parameters({"query": "hello", "extra": "value"}) is True

    def test_no_required_params(self):
        """没有必填参数时，空参数应通过验证。"""
        schema = _make_schema(
            inputSchema={"type": "object", "properties": {"opt": {"type": "string"}}}
        )
        tool = _make_mcp_tool(schema=schema)
        assert tool.validate_parameters({}) is True

    def test_empty_required_list(self):
        """required 为空列表时，空参数应通过验证。"""
        schema = _make_schema(
            inputSchema={
                "type": "object",
                "properties": {"opt": {"type": "string"}},
                "required": [],
            }
        )
        tool = _make_mcp_tool(schema=schema)
        assert tool.validate_parameters({}) is True

    def test_multiple_required_all_present(self):
        """多个必填参数全部提供时应返回 True。"""
        schema = _make_schema(
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            }
        )
        tool = _make_mcp_tool(schema=schema)
        assert tool.validate_parameters({"a": "x", "b": 1}) is True

    def test_multiple_required_partial_missing(self):
        """多个必填参数部分缺失时应返回 False。"""
        schema = _make_schema(
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            }
        )
        tool = _make_mcp_tool(schema=schema)
        assert tool.validate_parameters({"a": "x"}) is False


# ---------------------------------------------------------------------------
# execute 测试
# ---------------------------------------------------------------------------

class TestMCPToolExecute:
    """测试 MCPTool.execute()。"""

    def test_execute_success(self):
        """成功执行应返回 is_error=False 的 ToolResult。"""
        tool = _make_mcp_tool()

        async def mock_execute(**kwargs):
            return "执行结果"

        with patch.object(tool, "_execute_with_new_connection", side_effect=mock_execute):
            result = tool.execute(tool_call_id="call_1", query="test")

        assert isinstance(result, ToolResult)
        assert result.tool_call_id == "call_1"
        assert result.content == "执行结果"
        assert result.is_error is False

    def test_execute_error(self):
        """_execute_with_new_connection 抛异常时应返回 is_error=True 的 ToolResult。"""
        tool = _make_mcp_tool()

        async def mock_execute(**kwargs):
            raise RuntimeError("连接失败")

        with patch.object(tool, "_execute_with_new_connection", side_effect=mock_execute):
            result = tool.execute(tool_call_id="call_2", query="test")

        assert isinstance(result, ToolResult)
        assert result.tool_call_id == "call_2"
        assert "连接失败" in result.content
        assert result.is_error is True

    def test_execute_timeout(self):
        """执行超时时应返回 is_error=True 且包含超时信息的 ToolResult。"""
        tool = _make_mcp_tool()
        tool.timeout = 0.1  # 设置极短超时

        async def mock_execute(**kwargs):
            # 模拟长时间执行
            import asyncio
            await asyncio.sleep(5)

        with patch.object(tool, "_execute_with_new_connection", side_effect=mock_execute):
            result = tool.execute(tool_call_id="call_3", query="test")

        assert isinstance(result, ToolResult)
        assert result.tool_call_id == "call_3"
        assert "超时" in result.content
        assert result.is_error is True

    def test_execute_passes_kwargs(self):
        """execute 应将 kwargs 传递给 _execute_with_new_connection。"""
        tool = _make_mcp_tool()
        received_kwargs = {}

        async def mock_execute(**kwargs):
            received_kwargs.update(kwargs)
            return "ok"

        with patch.object(tool, "_execute_with_new_connection", side_effect=mock_execute):
            tool.execute(tool_call_id="call_4", query="hello", limit=5)

        assert received_kwargs == {"query": "hello", "limit": 5}

    def test_execute_outer_exception(self):
        """execute 外层异常（如线程创建失败）应返回 is_error=True。"""
        tool = _make_mcp_tool()

        with patch("hai_agent.mcp.tool.threading.Thread", side_effect=OSError("无法创建线程")):
            result = tool.execute(tool_call_id="call_5", query="test")

        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert "无法创建线程" in result.content


# ---------------------------------------------------------------------------
# __repr__ 测试
# ---------------------------------------------------------------------------

class TestMCPToolRepr:
    """测试 MCPTool.__repr__()。"""

    def test_repr_format(self):
        """__repr__ 应返回 MCPTool(name=..., client=...) 格式。"""
        schema = _make_schema(name="search")
        client = _make_client(name="my-server")
        tool = _make_mcp_tool(schema=schema, client=client)

        result = repr(tool)
        assert result == "MCPTool(name=search, client=my-server)"

    def test_repr_different_names(self):
        """不同名称的 MCPTool 应有不同的 __repr__。"""
        schema1 = _make_schema(name="tool_a")
        schema2 = _make_schema(name="tool_b")
        client = _make_client(name="server")

        tool1 = _make_mcp_tool(schema=schema1, client=client)
        tool2 = _make_mcp_tool(schema=schema2, client=client)

        assert "tool_a" in repr(tool1)
        assert "tool_b" in repr(tool2)
        assert repr(tool1) != repr(tool2)
