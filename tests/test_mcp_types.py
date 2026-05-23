"""MCP 类型和错误层次结构单元测试。"""

import pytest

from hai_agent.mcp.types import MCPToolSchema, MCPResourceSchema, MCPToolResult, MCPResourceContent
from hai_agent.mcp.errors import MCPError, MCPConnectionError, MCPToolCallError, MCPResourceError, MCPConfigError
from hai_agent.types.errors import AgentForgeError


# ── MCPToolSchema 测试 ──────────────────────────────────────


class TestMCPToolSchema:
    """MCPToolSchema.from_dict 测试。"""

    def test_from_dict_正常数据(self):
        """完整数据应正确映射。"""
        data = {
            "name": "search",
            "description": "搜索文档",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
        schema = MCPToolSchema.from_dict(data)
        assert schema.name == "search"
        assert schema.description == "搜索文档"
        assert schema.inputSchema == {"type": "object", "properties": {"q": {"type": "string"}}}

    def test_from_dict_缺失description默认空字符串(self):
        """缺少 description 时应默认为空字符串。"""
        data = {"name": "search", "inputSchema": {"type": "object"}}
        schema = MCPToolSchema.from_dict(data)
        assert schema.description == ""

    def test_from_dict_缺失inputSchema默认object(self):
        """缺少 inputSchema 时应默认为 {"type": "object"}。"""
        data = {"name": "search", "description": "搜索"}
        schema = MCPToolSchema.from_dict(data)
        assert schema.inputSchema == {"type": "object"}

    def test_from_dict_缺失name抛出KeyError(self):
        """缺少 name 字段应抛出 KeyError。"""
        with pytest.raises(KeyError):
            MCPToolSchema.from_dict({"description": "无名称"})

    def test_from_dict_description为None时保留None(self):
        """description 显式为 None 时 data.get 返回 None 而非默认值。"""
        data = {"name": "tool", "description": None, "inputSchema": {"type": "object"}}
        schema = MCPToolSchema.from_dict(data)
        # data.get("description", "") 在 key 存在时返回 None
        assert schema.description is None


# ── MCPResourceSchema 测试 ──────────────────────────────────


class TestMCPResourceSchema:
    """MCPResourceSchema.from_dict 测试。"""

    def test_from_dict_正常数据(self):
        """完整数据应正确映射。"""
        data = {
            "uri": "file:///tmp/readme.md",
            "name": "README",
            "description": "项目说明",
            "mimeType": "text/markdown",
        }
        schema = MCPResourceSchema.from_dict(data)
        assert schema.uri == "file:///tmp/readme.md"
        assert schema.name == "README"
        assert schema.description == "项目说明"
        assert schema.mimeType == "text/markdown"

    def test_from_dict_缺失name回退到uri(self):
        """缺少 name 时应回退到 uri 值。"""
        data = {"uri": "file:///tmp/readme.md"}
        schema = MCPResourceSchema.from_dict(data)
        assert schema.name == "file:///tmp/readme.md"

    def test_from_dict_缺失description为None(self):
        """缺少 description 时应为 None。"""
        data = {"uri": "file:///tmp/a.txt", "name": "a"}
        schema = MCPResourceSchema.from_dict(data)
        assert schema.description is None

    def test_from_dict_缺失mimeType为None(self):
        """缺少 mimeType 时应为 None。"""
        data = {"uri": "file:///tmp/a.txt", "name": "a"}
        schema = MCPResourceSchema.from_dict(data)
        assert schema.mimeType is None

    def test_from_dict_缺失uri抛出KeyError(self):
        """缺少 uri 字段应抛出 KeyError。"""
        with pytest.raises(KeyError):
            MCPResourceSchema.from_dict({"name": "无URI"})

    def test_from_dict_仅uri(self):
        """仅提供 uri 的最小输入。"""
        data = {"uri": "file:///tmp/x.json"}
        schema = MCPResourceSchema.from_dict(data)
        assert schema.uri == "file:///tmp/x.json"
        assert schema.name == "file:///tmp/x.json"
        assert schema.description is None
        assert schema.mimeType is None


# ── MCPToolResult 测试 ──────────────────────────────────────


class TestMCPToolResult:
    """MCPToolResult.from_dict 测试。"""

    def test_from_dict_字符串content(self):
        """content 为字符串时应直接使用。"""
        data = {"content": "执行成功", "isError": False}
        result = MCPToolResult.from_dict(data)
        assert result.content == "执行成功"
        assert result.isError is False

    def test_from_dict_列表content解析文本(self):
        """content 为列表时应提取 type=text 的项并拼接。"""
        data = {
            "content": [
                {"type": "text", "text": "第一行"},
                {"type": "text", "text": "第二行"},
            ],
        }
        result = MCPToolResult.from_dict(data)
        assert result.content == "第一行\n第二行"

    def test_from_dict_列表content过滤非text类型(self):
        """列表中非 text 类型的项应被忽略。"""
        data = {
            "content": [
                {"type": "image", "data": "base64..."},
                {"type": "text", "text": "有效文本"},
                {"type": "resource", "uri": "file:///x"},
            ],
        }
        result = MCPToolResult.from_dict(data)
        assert result.content == "有效文本"

    def test_from_dict_列表content全为非text类型(self):
        """列表中无 text 类型项时应返回空字符串。"""
        data = {
            "content": [
                {"type": "image", "data": "base64..."},
                {"type": "resource", "uri": "file:///x"},
            ],
        }
        result = MCPToolResult.from_dict(data)
        assert result.content == ""

    def test_from_dict_缺失content默认空字符串(self):
        """缺少 content 时应默认为空字符串。"""
        data = {"isError": True}
        result = MCPToolResult.from_dict(data)
        assert result.content == ""
        assert result.isError is True

    def test_from_dict_缺失isError默认False(self):
        """缺少 isError 时应默认为 False。"""
        data = {"content": "结果"}
        result = MCPToolResult.from_dict(data)
        assert result.isError is False

    def test_from_dict_空字典(self):
        """空字典输入应使用所有默认值。"""
        result = MCPToolResult.from_dict({})
        assert result.content == ""
        assert result.isError is False

    def test_from_dict_列表content中text缺失text键(self):
        """列表项 type=text 但缺少 text 键时应使用空字符串。"""
        data = {
            "content": [
                {"type": "text"},
            ],
        }
        result = MCPToolResult.from_dict(data)
        assert result.content == ""

    def test_from_dict_列表content中项非dict(self):
        """列表项不是字典时应被忽略（不会匹配 type=text）。"""
        data = {
            "content": ["纯字符串", 42, None],
        }
        result = MCPToolResult.from_dict(data)
        assert result.content == ""


# ── MCPResourceContent 测试 ─────────────────────────────────


class TestMCPResourceContent:
    """MCPResourceContent.from_dict 测试。"""

    def test_from_dict_正常数据(self):
        """完整数据应正确映射。"""
        data = {
            "contents": [
                {
                    "uri": "file:///tmp/readme.md",
                    "text": "# Hello",
                    "mimeType": "text/markdown",
                }
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.uri == "file:///tmp/readme.md"
        assert content.text == "# Hello"
        assert content.mimeType == "text/markdown"

    def test_from_dict_bytes解码(self):
        """text 为 bytes 时应解码为 utf-8 字符串。"""
        data = {
            "contents": [
                {
                    "uri": "file:///tmp/data.txt",
                    "text": b"binary content",
                }
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.text == "binary content"
        assert isinstance(content.text, str)

    def test_from_dict_bytes中文解码(self):
        """bytes 包含中文时应正确解码。"""
        data = {
            "contents": [
                {
                    "uri": "file:///tmp/cn.txt",
                    "text": "中文内容".encode("utf-8"),
                }
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.text == "中文内容"

    def test_from_dict_空contents(self):
        """contents 为空列表时应返回空 uri 和空 text。"""
        data = {"contents": []}
        content = MCPResourceContent.from_dict(data)
        assert content.uri == ""
        assert content.text == ""
        assert content.mimeType is None

    def test_from_dict_缺失contents(self):
        """缺少 contents 键时应返回空 uri 和空 text。"""
        data = {}
        content = MCPResourceContent.from_dict(data)
        assert content.uri == ""
        assert content.text == ""

    def test_from_dict_缺失mimeType为None(self):
        """contents 项缺少 mimeType 时应为 None。"""
        data = {
            "contents": [
                {
                    "uri": "file:///tmp/a.txt",
                    "text": "hello",
                }
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.mimeType is None

    def test_from_dict_缺失uri默认空字符串(self):
        """contents 项缺少 uri 时应默认为空字符串。"""
        data = {
            "contents": [
                {"text": "无 URI 的内容"},
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.uri == ""
        assert content.text == "无 URI 的内容"

    def test_from_dict_缺失text默认空字符串(self):
        """contents 项缺少 text 时应默认为空字符串。"""
        data = {
            "contents": [
                {"uri": "file:///tmp/a.txt"},
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.text == ""

    def test_from_dict_仅取第一个contents项(self):
        """多个 contents 项时仅取第一个。"""
        data = {
            "contents": [
                {"uri": "file:///tmp/first.txt", "text": "第一"},
                {"uri": "file:///tmp/second.txt", "text": "第二"},
            ]
        }
        content = MCPResourceContent.from_dict(data)
        assert content.uri == "file:///tmp/first.txt"
        assert content.text == "第一"


# ── MCP 错误层次结构测试 ────────────────────────────────────


class TestMCPErrorHierarchy:
    """MCP 错误类型层次结构测试。"""

    def test_MCPError是AgentForgeError子类(self):
        """MCPError 应继承自 AgentForgeError。"""
        assert issubclass(MCPError, AgentForgeError)

    def test_MCPConnectionError是MCPError子类(self):
        """MCPConnectionError 应继承自 MCPError。"""
        assert issubclass(MCPConnectionError, MCPError)

    def test_MCPToolCallError是MCPError子类(self):
        """MCPToolCallError 应继承自 MCPError。"""
        assert issubclass(MCPToolCallError, MCPError)

    def test_MCPResourceError是MCPError子类(self):
        """MCPResourceError 应继承自 MCPError。"""
        assert issubclass(MCPResourceError, MCPError)

    def test_MCPConfigError是MCPError子类(self):
        """MCPConfigError 应继承自 MCPError。"""
        assert issubclass(MCPConfigError, MCPError)

    def test_所有MCP错误都是AgentForgeError子类(self):
        """所有 MCP 错误都应可被 AgentForgeError 捕获。"""
        mcp_errors = [MCPError, MCPConnectionError, MCPToolCallError, MCPResourceError, MCPConfigError]
        for err_cls in mcp_errors:
            assert issubclass(err_cls, AgentForgeError), f"{err_cls.__name__} 不是 AgentForgeError 的子类"

    def test_MCPError可被捕获为Exception(self):
        """MCPError 应可被作为 Exception 捕获。"""
        with pytest.raises(Exception):
            raise MCPError("测试错误")

    def test_MCPConnectionError可被MCPError捕获(self):
        """MCPConnectionError 应可被 MCPError 捕获。"""
        with pytest.raises(MCPError):
            raise MCPConnectionError("连接失败")

    def test_MCPToolCallError可被MCPError捕获(self):
        """MCPToolCallError 应可被 MCPError 捕获。"""
        with pytest.raises(MCPError):
            raise MCPToolCallError("工具调用失败")

    def test_MCPResourceError可被MCPError捕获(self):
        """MCPResourceError 应可被 MCPError 捕获。"""
        with pytest.raises(MCPError):
            raise MCPResourceError("资源访问失败")

    def test_MCPConfigError可被MCPError捕获(self):
        """MCPConfigError 应可被 MCPError 捕获。"""
        with pytest.raises(MCPError):
            raise MCPConfigError("配置错误")

    def test_MCPError继承AgentForgeError属性(self):
        """MCPError 应继承 AgentForgeError 的 message 和 reason 属性。"""
        err = MCPError("测试消息")
        assert err.message == "测试消息"
        assert hasattr(err, "reason")
        assert hasattr(err, "details")

    def test_子类错误消息正确传递(self):
        """子类错误的消息应正确传递。"""
        err = MCPConnectionError("服务器不可达")
        assert str(err) == "服务器不可达"
        assert err.message == "服务器不可达"
