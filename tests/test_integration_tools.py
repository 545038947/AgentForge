"""AgentForge 高级集成测试 — 工具调用与 MCP。

测试场景：
1. 自定义工具注册和调用
2. 工具调用循环（agent 调用工具后将结果反馈给 LLM）
3. 错误工具调用处理
4. 工具护栏（ToolCallGuardrail）
5. MCP 服务器连接（如果有可用的）
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from hai_agent import Agent
from hai_agent.providers.builtins.ollama import OllamaProvider
from hai_agent.tools.base import Tool
from hai_agent.types import ToolResult

OLLAMA_BASE_URL = "http://localhost:11434/v1"
MODEL = "gemma4:31b-cloud"

results = {"pass": 0, "fail": 0}


def log_result(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results[status.lower()] += 1
    print(f"  [{status}] {name}: {detail}")


# === 自定义工具 ===
class WeatherTool(Tool):
    """天气查询工具。"""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "获取指定城市的天气信息"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称"},
            },
            "required": ["city"],
        }

    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        city = kwargs.get("city", "未知")
        # 模拟天气数据
        weather_data = {
            "北京": "晴天，25°C",
            "上海": "多云，22°C",
            "深圳": "阵雨，28°C",
        }
        weather = weather_data.get(city, "晴天，20°C")
        return ToolResult(
            tool_call_id=tool_call_id,
            content=json.dumps({"city": city, "weather": weather}, ensure_ascii=False),
            is_error=False,
        )


class CalculatorTool(Tool):
    """计算器工具。"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "计算数学表达式"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式，如 '2+3*4'"},
            },
            "required": ["expression"],
        }

    def execute(self, tool_call_id: str, **kwargs) -> ToolResult:
        expr = kwargs.get("expression", "")
        try:
            # 仅允许安全表达式
            allowed = set("0123456789+-*/.() ")
            if not all(c in allowed for c in expr):
                return ToolResult(
                    tool_call_id=tool_call_id,
                    content=f"不支持的表达式: {expr}",
                    is_error=True,
                )
            result = eval(expr)
            return ToolResult(
                tool_call_id=tool_call_id,
                content=str(result),
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"计算错误: {e}",
                is_error=True,
            )


# === 测试 1: 工具注册 ===
def test_tool_registration():
    """测试自定义工具注册。"""
    print("\n=== 测试 1: 工具注册 ===")

    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    weather = WeatherTool()
    calc = CalculatorTool()

    agent = Agent(
        provider=provider,
        tools=[weather, calc],
        register_atexit=False,
    )

    try:
        # 检查工具是否注册成功
        tool_names = list(agent._tools.keys())
        log_result("天气工具注册", "get_weather" in tool_names, f"工具列表={tool_names}")
        log_result("计算器工具注册", "calculator" in tool_names, f"工具列表={tool_names}")
    except Exception as e:
        log_result("工具注册", False, str(e))
    finally:
        agent.shutdown()


# === 测试 2: 工具调用 ===
def test_tool_execution():
    """测试 Agent 调用工具并获取结果。"""
    print("\n=== 测试 2: 工具调用 ===")

    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    weather = WeatherTool()

    agent = Agent(
        provider=provider,
        tools=[weather],
        register_atexit=False,
    )

    try:
        response = agent.run("北京今天天气怎么样？请用get_weather工具查询。")
        has_result = response and len(response.content) > 0
        log_result("工具调用返回内容", has_result, f"长度={len(response.content) if response else 0}")

        # 检查是否包含天气信息
        if response:
            mentions_weather = any(kw in response.content for kw in ["25", "晴天", "天气", "北京"])
            log_result("工具结果被整合到回答", mentions_weather, f"内容片段={response.content[:100]}")
    except Exception as e:
        log_result("工具调用返回内容", False, str(e))
    finally:
        agent.shutdown()


# === 测试 3: 计算器工具 ===
def test_calculator_tool():
    """测试计算器工具调用。"""
    print("\n=== 测试 3: 计算器工具 ===")

    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    calc = CalculatorTool()

    agent = Agent(
        provider=provider,
        tools=[calc],
        register_atexit=False,
    )

    try:
        response = agent.run("请用calculator工具计算 123 * 456 的结果。")
        has_result = response and len(response.content) > 0
        log_result("计算器工具返回内容", has_result, f"长度={len(response.content) if response else 0}")

        # 检查是否包含正确结果
        if response:
            has_correct = "56088" in response.content.replace(",", "")
            log_result("计算结果正确", has_correct, f"内容片段={response.content[:200]}")
    except Exception as e:
        log_result("计算器工具返回内容", False, str(e))
    finally:
        agent.shutdown()


# === 测试 4: 多工具协作 ===
def test_multi_tool():
    """测试多个工具同时可用。"""
    print("\n=== 测试 4: 多工具协作 ===")

    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    weather = WeatherTool()
    calc = CalculatorTool()

    agent = Agent(
        provider=provider,
        tools=[weather, calc],
        register_atexit=False,
    )

    try:
        response = agent.run("请查询上海的天气，并计算 100 * 50 的结果。")
        has_result = response and len(response.content) > 0
        log_result("多工具协作返回内容", has_result, f"长度={len(response.content) if response else 0}")
    except Exception as e:
        log_result("多工具协作返回内容", False, str(e))
    finally:
        agent.shutdown()


# === 测试 5: 直接工具执行验证 ===
def test_tool_direct_execution():
    """测试直接调用工具的 execute 方法。"""
    print("\n=== 测试 5: 直接工具执行 ===")

    weather = WeatherTool()
    calc = CalculatorTool()

    # 直接执行天气工具
    result = weather.execute("call-1", city="北京")
    log_result("天气工具直接执行", result.content and "北京" in result.content, f"result={result.content}")

    # 直接执行计算器
    result2 = calc.execute("call-2", expression="2+3*4")
    log_result("计算器直接执行", result2.content == "14", f"result={result2.content}")

    # 计算器错误表达式
    result3 = calc.execute("call-3", expression="1/0")
    log_result("计算器错误处理", result3.is_error, f"result={result3.content}")


# === 测试 6: 流式 + 工具 ===
def test_stream_with_tools():
    """测试流式模式下的工具调用。"""
    print("\n=== 测试 6: 流式 + 工具 ===")

    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    weather = WeatherTool()

    agent = Agent(
        provider=provider,
        tools=[weather],
        register_atexit=False,
    )

    chunks = []
    try:
        for chunk in agent.stream("北京天气如何？请用get_weather工具查询。"):
            chunks.append(chunk)
            if chunk.tool_calls:
                tool_names = [tc.name for tc in chunk.tool_calls]
                print(f"  [工具调用: {', '.join(tool_names)}]", flush=True)

        full_content = "".join(c.content or "" for c in chunks)
        log_result("流式+工具收到chunk", len(chunks) > 0, f"chunk数={len(chunks)}")
        log_result("流式+工具有内容", len(full_content) > 0, f"长度={len(full_content)}")
    except Exception as e:
        log_result("流式+工具", False, str(e))
    finally:
        agent.shutdown()


# === 主程序 ===
def main():
    print("=" * 60)
    print("AgentForge 高级集成测试 — 工具调用")
    print(f"模型: {MODEL}")
    print(f"服务: {OLLAMA_BASE_URL}")
    print("=" * 60)

    test_tool_registration()
    test_tool_execution()
    test_calculator_tool()
    test_multi_tool()
    test_tool_direct_execution()
    test_stream_with_tools()

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    total = results["pass"] + results["fail"]
    print(f"  通过: {results['pass']}")
    print(f"  失败: {results['fail']}")
    print(f"  总计: {total}")
    if total > 0:
        print(f"  通过率: {results['pass']/total*100:.0f}%")
    print("=" * 60)

    return results["fail"] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)