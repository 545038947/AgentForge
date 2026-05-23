"""P3 阶段单元测试：工具系统。"""

import pytest
import threading
import time

from hai_agent.tools import (
    Tool,
    FunctionTool,
    tool,
    ToolRegistry,
    register_tool,
    get_tool,
    list_tools,
    ToolExecutor,
    ToolExecution,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalCallback,
    ApprovalManager,
)
from hai_agent.types import ToolResult


# ── 测试工具实现 ──────────────────────────────────────────────

class MockTool(Tool):
    """测试工具。"""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query string"}
            },
            "required": ["query"]
        }

    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        return ToolResult(tool_call_id=tool_call_id, content=f"Result: {kwargs.get('query')}")


class DangerousTool(Tool):
    """危险工具。"""

    @property
    def name(self) -> str:
        return "dangerous_tool"

    @property
    def description(self) -> str:
        return "A dangerous tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    dangerous = True
    requires_approval = True

    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        return ToolResult(tool_call_id=tool_call_id, content="Dangerous operation done")


class TestTool:
    """Tool 抽象基类测试。"""

    def test_abstract_properties(self):
        """测试抽象属性必须实现。"""
        # 不能直接实例化抽象类
        with pytest.raises(TypeError):
            Tool()

    def test_mock_tool(self):
        """测试 MockTool 实现。"""
        tool = MockTool()

        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"
        assert "query" in tool.parameters["properties"]
        assert tool.timeout == 300.0
        assert not tool.requires_approval

    def test_execute(self):
        """测试工具执行。"""
        tool = MockTool()
        result = tool.execute("call-1", query="test")

        assert result.tool_call_id == "call-1"
        assert result.content == "Result: test"
        assert not result.is_error

    def test_to_spec(self):
        """测试转换为 ToolSpec。"""
        tool = MockTool()
        spec = tool.to_spec()

        assert spec.name == "mock_tool"
        assert spec.description == "A mock tool for testing"
        assert spec.timeout == 300.0


class TestFunctionTool:
    """FunctionTool 测试。"""

    def test_from_function(self):
        """测试从函数创建工具。"""
        def search(query: str) -> str:
            """Search for something."""
            return f"Found: {query}"

        ft = FunctionTool(search)

        assert ft.name == "search"
        assert ft.description == "Search for something."
        assert "query" in ft.parameters["properties"]
        assert "query" in ft.parameters["required"]

    def test_execute_string_result(self):
        """测试执行返回字符串。"""
        def greet(name: str) -> str:
            return f"Hello, {name}"

        ft = FunctionTool(greet)
        result = ft.execute("call-1", name="World")

        assert result.content == "Hello, World"
        assert not result.is_error

    def test_execute_dict_result(self):
        """测试执行返回字典。"""
        def get_info(key: str) -> dict:
            return {"key": key, "value": "test"}

        ft = FunctionTool(get_info)
        result = ft.execute("call-1", key="abc")

        assert "key" in result.content
        assert "abc" in result.content

    def test_execute_tool_result(self):
        """测试执行返回 ToolResult。"""
        def custom_tool(x: int) -> ToolResult:
            return ToolResult(tool_call_id="custom", content=f"Value: {x}")

        ft = FunctionTool(custom_tool)
        result = ft.execute("call-1", x=42)

        assert result.content == "Value: 42"

    def test_custom_name_description(self):
        """测试自定义名称和描述。"""
        def func(x: int) -> str:
            return str(x)

        ft = FunctionTool(func, name="custom_name", description="Custom description")

        assert ft.name == "custom_name"
        assert ft.description == "Custom description"

    def test_infer_parameters(self):
        """测试参数推断。"""
        def complex_func(a: int, b: str, c: bool, d: list, e: dict, f: float) -> str:
            return "result"

        ft = FunctionTool(complex_func)
        params = ft.parameters

        assert params["properties"]["a"]["type"] == "number"
        assert params["properties"]["b"]["type"] == "string"
        assert params["properties"]["c"]["type"] == "boolean"
        assert params["properties"]["d"]["type"] == "array"
        assert params["properties"]["e"]["type"] == "object"
        assert params["properties"]["f"]["type"] == "number"

    def test_error_handling(self):
        """测试错误处理。"""
        def failing_tool(x: int) -> str:
            raise ValueError("Test error")

        ft = FunctionTool(failing_tool)
        result = ft.execute("call-1", x=1)

        assert result.is_error
        assert "Test error" in result.content


class TestToolDecorator:
    """@tool 装饰器测试。"""

    def test_simple_decorator(self):
        """测试简单装饰器。"""
        @tool
        def search(query: str) -> str:
            """Search for something."""
            return f"Found: {query}"

        assert isinstance(search, FunctionTool)
        assert search.name == "search"

        result = search.execute("call-1", query="test")
        assert result.content == "Found: test"

    def test_decorator_with_options(self):
        """测试带参数的装饰器。"""
        @tool(name="custom_search", requires_approval=True)
        def my_search(q: str) -> str:
            return f"Result: {q}"

        assert my_search.name == "custom_search"
        assert my_search.requires_approval


class TestToolRegistry:
    """ToolRegistry 测试。"""

    def test_register(self):
        """测试注册工具。"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)
        assert "mock_tool" in registry.list()

    def test_unregister(self):
        """测试取消注册。"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)
        result = registry.unregister("mock_tool")
        assert result is True
        assert "mock_tool" not in registry.list()

    def test_unregister_not_found(self):
        """测试取消注册不存在的工具。"""
        registry = ToolRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_get(self):
        """测试获取工具。"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)
        found = registry.get("mock_tool")
        assert found is tool

    def test_get_not_found(self):
        """测试获取不存在的工具。"""
        registry = ToolRegistry()
        found = registry.get("nonexistent")
        assert found is None

    def test_list(self):
        """测试列出工具。"""
        registry = ToolRegistry()
        tool1 = MockTool()
        tool2 = DangerousTool()

        registry.register(tool1)
        registry.register(tool2)

        names = registry.list()
        assert "mock_tool" in names
        assert "dangerous_tool" in names

    def test_get_all(self):
        """测试获取所有工具。"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)
        all_tools = registry.get_all()
        assert "mock_tool" in all_tools

    def test_to_specs(self):
        """测试转换为 ToolSpec 列表。"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)
        specs = registry.to_specs()
        assert len(specs) == 1
        assert specs[0].name == "mock_tool"

    def test_clear(self):
        """测试清空注册表。"""
        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)
        registry.clear()
        assert len(registry.list()) == 0

    def test_thread_safety(self):
        """测试线程安全。"""
        registry = ToolRegistry()
        results = []

        def register_loop():
            for i in range(100):
                t = MockTool()
                t._name = f"tool_{threading.current_thread().name}_{i}"
                registry.register(t)
                results.append(t.name)

        threads = [threading.Thread(target=register_loop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 500


class TestGlobalRegistry:
    """全局注册表测试。"""

    def test_register_tool(self):
        """测试全局注册。"""
        tool = MockTool()
        register_tool(tool)

        assert "mock_tool" in list_tools()

        # 清理
        get_tool("mock_tool")  # 确认存在


class TestToolExecutor:
    """ToolExecutor 测试。"""

    def test_execute_single(self):
        """测试执行单个工具。"""
        executor = ToolExecutor()
        tool = MockTool()

        result = executor.execute(tool, "call-1", query="test")

        assert result.content == "Result: test"
        assert not result.is_error

    def test_execute_batch(self):
        """测试并发执行多个工具。"""
        executor = ToolExecutor(max_workers=2)
        tool = MockTool()

        calls = [
            (tool, "call-1", {"query": "a"}),
            (tool, "call-2", {"query": "b"}),
            (tool, "call-3", {"query": "c"}),
        ]

        results = executor.execute_batch(calls)

        assert len(results) == 3
        assert all(not r.is_error for r in results)

    def test_execution_record(self):
        """测试执行记录。"""
        executor = ToolExecutor()
        tool = MockTool()

        executor.execute(tool, "call-1", query="test")

        execution = executor.get_execution("call-1")
        assert execution is not None
        assert execution.tool_name == "mock_tool"
        assert execution.success
        assert execution.duration >= 0  # 执行时间可能非常短

    def test_context_manager(self):
        """测试上下文管理器。"""
        tool = MockTool()

        with ToolExecutor() as executor:
            result = executor.execute(tool, "call-1", query="test")
            assert result.content == "Result: test"

    def test_shutdown(self):
        """测试关闭执行器。"""
        executor = ToolExecutor()
        executor.start()

        executor.shutdown(wait=True)
        assert executor._executor is None


class TestToolExecution:
    """ToolExecution 测试。"""

    def test_duration(self):
        """测试执行耗时计算。"""
        execution = ToolExecution(
            tool_call_id="call-1",
            tool_name="test",
            args={},
            start_time=time.time(),
            end_time=time.time() + 1.5,
        )

        assert execution.duration == 1.5

    def test_success(self):
        """测试成功状态判断。"""
        execution = ToolExecution(
            tool_call_id="call-1",
            tool_name="test",
            args={},
            result=ToolResult(tool_call_id="call-1", content="ok"),
        )

        assert execution.success

    def test_failure(self):
        """测试失败状态判断。"""
        execution = ToolExecution(
            tool_call_id="call-1",
            tool_name="test",
            args={},
            result=ToolResult(tool_call_id="call-1", content="error", is_error=True),
        )

        assert not execution.success


class TestApprovalDecision:
    """ApprovalDecision 测试。"""

    def test_decision_values(self):
        """测试决定值。"""
        assert ApprovalDecision.APPROVE.value == "approve"
        assert ApprovalDecision.DENY.value == "deny"
        assert ApprovalDecision.APPROVE_ONCE.value == "approve_once"
        assert ApprovalDecision.APPROVE_ALL.value == "approve_all"


class TestApprovalRequest:
    """ApprovalRequest 测试。"""

    def test_create_request(self):
        """测试创建审批请求。"""
        request = ApprovalRequest(
            tool_name="dangerous_tool",
            args={"path": "/tmp"},
            reason="需要删除文件",
            risk_level="high",
        )

        assert request.tool_name == "dangerous_tool"
        assert request.risk_level == "high"

    def test_to_dict(self):
        """测试转换为字典。"""
        request = ApprovalRequest(
            tool_name="test",
            args={"x": 1},
            reason="test",
        )

        d = request.to_dict()
        assert d["tool_name"] == "test"
        assert d["args"] == {"x": 1}


class TestApprovalResponse:
    """ApprovalResponse 测试。"""

    def test_approve_response(self):
        """测试批准响应。"""
        response = ApprovalResponse(
            decision=ApprovalDecision.APPROVE,
            reason="安全操作",
        )

        assert response.decision == ApprovalDecision.APPROVE

    def test_deny_response(self):
        """测试拒绝响应。"""
        response = ApprovalResponse(
            decision=ApprovalDecision.DENY,
            reason="危险操作",
        )

        assert response.decision == ApprovalDecision.DENY


class TestApprovalCallback:
    """ApprovalCallback 测试。"""

    def test_not_implemented(self):
        """测试未实现方法抛出异常。"""
        callback = ApprovalCallback()
        with pytest.raises(NotImplementedError):
            callback.request_approval(ApprovalRequest(tool_name="test", args={}))

    def test_custom_callback(self):
        """测试自定义回调。"""
        class SimpleCallback(ApprovalCallback):
            def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
                return ApprovalResponse(decision=ApprovalDecision.APPROVE)

        callback = SimpleCallback()
        response = callback.request_approval(ApprovalRequest(tool_name="test", args={}))

        assert response.decision == ApprovalDecision.APPROVE


class TestApprovalManager:
    """ApprovalManager 测试。"""

    def test_needs_approval(self):
        """测试判断是否需要审批。"""
        manager = ApprovalManager()
        safe_tool = MockTool()
        dangerous_tool = DangerousTool()

        assert not manager.needs_approval(safe_tool, {})
        assert manager.needs_approval(dangerous_tool, {})

    def test_request_approval_with_callback(self):
        """测试带回调的审批请求。"""
        class SimpleCallback(ApprovalCallback):
            def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
                return ApprovalResponse(decision=ApprovalDecision.APPROVE)

        manager = ApprovalManager()
        manager.set_callback(SimpleCallback())

        response = manager.request_approval(DangerousTool(), {})

        assert response.decision == ApprovalDecision.APPROVE

    def test_request_approval_without_callback(self):
        """测试无回调时的审批请求。"""
        manager = ApprovalManager()

        response = manager.request_approval(DangerousTool(), {})

        assert response.decision == ApprovalDecision.DENY

    def test_cache_approve_all(self):
        """测试 APPROVE_ALL 缓存。"""
        class ApproveAllCallback(ApprovalCallback):
            def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
                return ApprovalResponse(
                    decision=ApprovalDecision.APPROVE_ALL,
                    cache_key="test_key",
                )

        manager = ApprovalManager()
        manager.set_callback(ApproveAllCallback())

        # 第一次请求
        response1 = manager.request_approval(DangerousTool(), {"x": 1})
        assert response1.decision == ApprovalDecision.APPROVE_ALL

        # 第二次应该使用缓存
        response2 = manager.request_approval(DangerousTool(), {"x": 1})
        assert response2.decision == ApprovalDecision.APPROVE
        assert "缓存" in response2.reason

    def test_clear_cache(self):
        """测试清空缓存。"""
        class ApproveAllCallback(ApprovalCallback):
            def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
                return ApprovalResponse(decision=ApprovalDecision.APPROVE_ALL)

        manager = ApprovalManager()
        manager.set_callback(ApproveAllCallback())

        manager.request_approval(DangerousTool(), {"x": 1})
        manager.clear_cache()

        assert len(manager._cache) == 0

    def test_auto_approve_safe(self):
        """测试自动批准安全操作。"""
        manager = ApprovalManager()
        safe_tool = MockTool()

        assert manager.auto_approve(safe_tool, {})

    def test_auto_approve_dangerous(self):
        """测试不自动批准危险操作。"""
        manager = ApprovalManager()
        dangerous_tool = DangerousTool()

        assert not manager.auto_approve(dangerous_tool, {})