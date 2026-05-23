"""演示用自定义工具。

包含 4 个工具展示不同特性：
- calculator: 基础工具调用，单参数
- get_weather: 多参数，可选参数
- read_file: 文件操作，路径验证
- search_web: 模拟外部服务，整数参数
"""

from __future__ import annotations

import os
from typing import List

from hai_agent import tool


@tool
def calculator(expression: str) -> str:
    """计算数学表达式。

    支持基本运算：加(+)、减(-)、乘(*)、除(/)。

    Args:
        expression: 数学表达式，如 "123 * 456" 或 "100 / 5"

    Returns:
        计算结果
    """
    try:
        # 安全计算：只允许数字和基本运算符
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含不允许的字符"

        result = eval(expression)
        return f"计算结果: {expression} = {result}"
    except ZeroDivisionError:
        return "错误：除数不能为零"
    except Exception as e:
        return f"计算错误: {e}"


@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """获取指定城市的天气信息（模拟）。

    这是一个模拟工具，返回预设的天气数据。

    Args:
        city: 城市名称，如 "北京"、"上海"
        unit: 温度单位，"celsius" 或 "fahrenheit"

    Returns:
        天气信息字符串
    """
    # 模拟天气数据
    weather_data = {
        "北京": {"temp": 25, "condition": "晴朗", "humidity": 45},
        "上海": {"temp": 28, "condition": "多云", "humidity": 65},
        "广州": {"temp": 32, "condition": "雷阵雨", "humidity": 80},
        "深圳": {"temp": 30, "condition": "晴朗", "humidity": 70},
        "成都": {"temp": 22, "condition": "阴天", "humidity": 55},
    }

    # 获取城市数据，默认返回通用数据
    data = weather_data.get(city, {"temp": 26, "condition": "晴朗", "humidity": 50})

    # 温度单位转换
    temp = data["temp"]
    if unit == "fahrenheit":
        temp = temp * 9 / 5 + 32
        unit_str = "°F"
    else:
        unit_str = "°C"

    return (
        f"📍 {city} 天气预报\n"
        f"  温度: {temp:.1f}{unit_str}\n"
        f"  天气: {data['condition']}\n"
        f"  湿度: {data['humidity']}%"
    )


@tool
def read_file(filepath: str) -> str:
    """读取本地文件内容。

    读取指定路径的文本文件内容。

    Args:
        filepath: 文件路径，可以是相对路径或绝对路径

    Returns:
        文件内容或错误信息
    """
    try:
        # 路径验证
        if not filepath:
            return "错误：文件路径不能为空"

        # 展开路径（支持 ~）
        expanded_path = os.path.expanduser(filepath)

        # 检查文件是否存在
        if not os.path.exists(expanded_path):
            return f"错误：文件不存在: {filepath}"

        # 检查是否是文件
        if not os.path.isfile(expanded_path):
            return f"错误：路径不是文件: {filepath}"

        # 读取文件
        with open(expanded_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 限制返回长度
        max_length = 2000
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n... (已截断，共 {len(content)} 字符)"

        return f"📄 文件: {filepath}\n\n{content}"

    except PermissionError:
        return f"错误：无权限读取文件: {filepath}"
    except UnicodeDecodeError:
        return f"错误：文件编码不支持（非文本文件）: {filepath}"
    except Exception as e:
        return f"读取错误: {e}"


@tool
def search_web(query: str, limit: int = 3) -> str:
    """模拟网络搜索。

    这是一个模拟工具，返回预设的搜索结果。

    Args:
        query: 搜索关键词
        limit: 返回结果数量，默认 3

    Returns:
        模拟的搜索结果
    """
    # 模拟搜索结果
    mock_results = [
        {
            "title": f"关于 {query} 的详细介绍",
            "url": f"https://example.com/article/{query}",
            "snippet": f"这是关于 {query} 的详细文章，包含相关知识和信息...",
        },
        {
            "title": f"{query} - 官方文档",
            "url": f"https://docs.example.com/{query}",
            "snippet": f"官方文档提供了 {query} 的完整使用指南...",
        },
        {
            "title": f"如何学习 {query}",
            "url": f"https://tutorial.example.com/{query}",
            "snippet": f"本教程将帮助你快速掌握 {query} 的核心概念...",
        },
        {
            "title": f"{query} 最佳实践",
            "url": f"https://bestpractices.example.com/{query}",
            "snippet": f"本文总结了 {query} 的最佳实践和常见问题...",
        },
        {
            "title": f"{query} 社区讨论",
            "url": f"https://forum.example.com/{query}",
            "snippet": f"社区成员分享了关于 {query} 的经验和见解...",
        },
    ]

    # 限制结果数量
    results = mock_results[:limit]

    # 格式化输出
    output = f"🔍 搜索: {query}\n"
    output += f"找到 {len(results)} 个结果:\n\n"

    for i, result in enumerate(results, 1):
        output += f"{i}. {result['title']}\n"
        output += f"   URL: {result['url']}\n"
        output += f"   {result['snippet']}\n\n"

    return output


def get_all_demo_tools() -> List:
    """获取所有演示工具。

    Returns:
        工具列表
    """
    return [calculator, get_weather, read_file, search_web]
