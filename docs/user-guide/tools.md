# 工具系统指南

## 定义工具

### 函数式工具

```python
from agentforge import tool

@tool
def search(query: str) -> str:
    """搜索网络信息。
    
    Args:
        query: 搜索关键词
    
    Returns:
        搜索结果
    """
    return f"搜索结果: {query}"
```

### 类式工具

```python
from agentforge import FunctionTool

class Calculator(FunctionTool):
    name = "calculator"
    description = "执行数学计算"
    
    def execute(self, expression: str) -> float:
        return eval(expression)
```

## 使用工具

```python
from agentforge import Agent

agent = Agent(model="gpt-4", tools=[search, Calculator()])
response = agent.run("搜索 Python 教程")
```

## 工具护栏

```python
from agentforge.tools import ToolCallGuardrailController

guardrail = ToolCallGuardrailController(
    allowed_tools=["search", "read"],
    max_calls_per_turn=5,
)

agent = Agent(model="gpt-4", tools=[...], guardrails=[guardrail])
```
