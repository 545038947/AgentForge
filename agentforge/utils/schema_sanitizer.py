"""Schema Sanitizer - JSON Schema 标准化。

清理 JSON Schema 以兼容不同 Provider 的验证器。
特别是 Anthropic 的 validator 对某些 JSON Schema 特性支持有限。

参考 hermes-agent/tools/schema_sanitizer.py 和 hermes-agent/agent/moonshot_schema.py。
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Moonshot 特定 Schema 键 ───────────────────────────────────────

# 值为 name → schema 映射的键
_MOONSHOT_SCHEMA_MAP_KEYS = frozenset({"properties", "patternProperties", "$defs", "definitions"})

# 值为 schema 列表的键
_MOONSHOT_SCHEMA_LIST_KEYS = frozenset({"anyOf", "oneOf", "allOf", "prefixItems"})

# 值为单个嵌套 schema 的键
_MOONSHOT_SCHEMA_NODE_KEYS = frozenset({"items", "contains", "not", "additionalProperties", "propertyNames"})


def strip_nullable_unions(schema: Dict[str, Any]) -> Dict[str, Any]:
    """清理 nullable union 类型。

    Anthropic 不支持 {"anyOf": [{"type": "string"}, {"type": "null"}]} 格式。
    将其转换为 {"type": "string", "nullable": True}。

    Args:
        schema: JSON Schema

    Returns:
        清理后的 Schema
    """
    if not isinstance(schema, dict):
        return schema

    result = {}

    for key, value in schema.items():
        if key == "anyOf" and isinstance(value, list):
            # 检查是否是 nullable union
            non_null_types = []
            has_null = False

            for item in value:
                if isinstance(item, dict):
                    if item.get("type") == "null":
                        has_null = True
                    else:
                        non_null_types.append(item)

            # 如果只有一个非 null 类型，转换为 nullable
            if has_null and len(non_null_types) == 1:
                result.update(non_null_types[0])
                result["nullable"] = True
            else:
                result[key] = [strip_nullable_unions(item) for item in value]

        elif key == "type":
            if isinstance(value, list):
                # 类型数组转为基础类型 + nullable
                non_null_types = [t for t in value if t != "null"]
                if "null" in value and len(non_null_types) == 1:
                    result["type"] = non_null_types[0]
                    result["nullable"] = True
                else:
                    result["type"] = value
            else:
                result[key] = value

        elif key == "properties" and isinstance(value, dict):
            result[key] = {
                k: strip_nullable_unions(v) for k, v in value.items()
            }

        elif key == "items":
            result[key] = strip_nullable_unions(value)

        elif key == "additionalProperties":
            if isinstance(value, dict):
                result[key] = strip_nullable_unions(value)
            else:
                result[key] = value

        elif key in ("allOf", "oneOf"):
            result[key] = [strip_nullable_unions(item) for item in value]

        else:
            result[key] = value

    return result


def strip_format_patterns(schema: Dict[str, Any]) -> Dict[str, Any]:
    """移除 format 和 pattern 字段。

    某些 Provider（如 llama.cpp）不支持正则表达式 pattern 和某些 format。

    Args:
        schema: JSON Schema

    Returns:
        清理后的 Schema
    """
    if not isinstance(schema, dict):
        return schema

    result = {}

    for key, value in schema.items():
        # 跳过 pattern 和 format
        if key in ("pattern", "format"):
            continue

        if key == "properties" and isinstance(value, dict):
            result[key] = {
                k: strip_format_patterns(v) for k, v in value.items()
            }
        elif key == "items":
            result[key] = strip_format_patterns(value)
        elif key == "additionalProperties" and isinstance(value, dict):
            result[key] = strip_format_patterns(value)
        elif key in ("allOf", "anyOf", "oneOf") and isinstance(value, list):
            result[key] = [strip_format_patterns(item) for item in value]
        else:
            result[key] = value

    return result


def sanitize_schema(
    schema: Dict[str, Any],
    *,
    strip_patterns: bool = False,
    strip_formats: bool = False,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """清理 JSON Schema 以兼容目标 Provider。

    Args:
        schema: JSON Schema
        strip_patterns: 是否移除 pattern 字段
        strip_formats: 是否移除 format 字段
        provider: 目标 Provider（自动选择清理策略）

    Returns:
        清理后的 Schema
    """
    if not isinstance(schema, dict):
        return schema

    # 始终清理 nullable unions
    result = strip_nullable_unions(schema)

    # 根据 Provider 选择清理策略
    if provider:
        provider_lower = provider.lower()

        # llama.cpp 不支持 pattern 和 format
        if provider_lower in ("llama", "llama.cpp", "ollama"):
            strip_patterns = True
            strip_formats = True

    if strip_patterns or strip_formats:
        result = strip_format_patterns(result)

    return result


def sanitize_tool_schema(
    tool_schema: Dict[str, Any],
    *,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """清理工具的 JSON Schema。

    Args:
        tool_schema: 工具 Schema（OpenAI 格式）
        provider: 目标 Provider

    Returns:
        清理后的工具 Schema
    """
    if not isinstance(tool_schema, dict):
        return tool_schema

    result = dict(tool_schema)

    # 清理 function.parameters
    if "function" in result:
        func = result["function"]
        if isinstance(func, dict) and "parameters" in func:
            result["function"] = dict(func)
            result["function"]["parameters"] = sanitize_schema(
                func["parameters"],
                provider=provider,
            )

    return result


def sanitize_tools(
    tools: List[Dict[str, Any]],
    *,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """清理工具列表。

    Args:
        tools: 工具列表
        provider: 目标 Provider

    Returns:
        清理后的工具列表
    """
    return [sanitize_tool_schema(tool, provider=provider) for tool in tools]


def validate_schema(schema: Dict[str, Any]) -> List[str]:
    """验证 JSON Schema 结构。

    Args:
        schema: JSON Schema

    Returns:
        错误消息列表（空列表表示有效）
    """
    errors = []

    if not isinstance(schema, dict):
        return ["Schema must be a dictionary"]

    # 检查必需字段
    if "type" not in schema and "anyOf" not in schema and "allOf" not in schema and "oneOf" not in schema:
        # 允许空 schema
        if schema:
            errors.append("Schema should have 'type', 'anyOf', 'allOf', or 'oneOf'")

    # 检查 properties
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            errors.append("'properties' must be a dictionary")
        else:
            for prop_name, prop_schema in schema["properties"].items():
                if not isinstance(prop_schema, dict):
                    errors.append(f"Property '{prop_name}' must be a dictionary")

    # 检查 required
    if "required" in schema:
        if not isinstance(schema["required"], list):
            errors.append("'required' must be a list")
        elif "properties" in schema:
            for prop in schema["required"]:
                if prop not in schema["properties"]:
                    errors.append(f"Required property '{prop}' not in 'properties'")

    return errors


# ── Moonshot 特定 Schema 清理 ───────────────────────────────────────

def _repair_moonshot_schema(node: Any, is_schema: bool = True) -> Any:
    """递归应用 Moonshot schema 修复。

    Moonshot 接受比标准 OpenAI 更严格的 JSON Schema 子集：
    1. 每个属性 schema 必须有 type
    2. anyOf 使用时，type 必须在子节点上
    3. enum 数组不能包含 null 或空字符串
    4. $ref 节点不能有兄弟关键字
    5. items 不能是元组样式数组

    Args:
        node: Schema 节点
        is_schema: 是否为 schema 节点（而非容器映射）

    Returns:
        修复后的节点
    """
    if isinstance(node, list):
        return [_repair_moonshot_schema(item, is_schema=True) for item in node]
    if not isinstance(node, dict):
        return node

    # 遍历字典，根据键决定递归方式
    repaired: Dict[str, Any] = {}
    for key, value in node.items():
        if key in _MOONSHOT_SCHEMA_MAP_KEYS and isinstance(value, dict):
            # name → schema 映射
            repaired[key] = {
                sub_key: _repair_moonshot_schema(sub_val, is_schema=True)
                for sub_key, sub_val in value.items()
            }
        elif key in _MOONSHOT_SCHEMA_LIST_KEYS and isinstance(value, list):
            repaired[key] = [_repair_moonshot_schema(v, is_schema=True) for v in value]
        elif key == "items" and isinstance(value, list):
            # 规则 5: 元组样式 items 数组，折叠为第一个元素
            first = value[0] if value else {}
            if isinstance(first, dict):
                repaired[key] = _repair_moonshot_schema(first, is_schema=True)
            else:
                repaired[key] = first
        elif key in _MOONSHOT_SCHEMA_NODE_KEYS:
            if isinstance(value, dict):
                repaired[key] = _repair_moonshot_schema(value, is_schema=True)
            else:
                repaired[key] = value
        else:
            repaired[key] = value

    if not is_schema:
        return repaired

    # 规则 2: anyOf 存在时，type 只能在子节点上
    if "anyOf" in repaired and isinstance(repaired["anyOf"], list):
        repaired.pop("type", None)
        non_null = [
            b for b in repaired["anyOf"]
            if isinstance(b, dict) and b.get("type") != "null"
        ]
        if non_null and len(non_null) < len(repaired["anyOf"]):
            if len(non_null) == 1:
                merge = {k: v for k, v in repaired.items() if k != "anyOf"}
                merge.update(non_null[0])
                repaired = merge
            else:
                repaired["anyOf"] = non_null
                return repaired
        else:
            return repaired

    # 移除 nullable（Moonshot 不接受）
    repaired.pop("nullable", None)

    # 规则 1: 没有 type 的属性 schema 需要填充
    if "$ref" not in repaired:
        repaired = _fill_moonshot_missing_type(repaired)

    # 规则 3: 清理 enum 中的 null 和空字符串
    if "enum" in repaired and isinstance(repaired["enum"], list):
        node_type = repaired.get("type")
        if node_type in {"string", "integer", "number", "boolean"}:
            cleaned = [v for v in repaired["enum"] if v is not None and v != ""]
            if cleaned:
                repaired["enum"] = cleaned
            else:
                repaired.pop("enum")

    # 规则 4: $ref 节点不能有兄弟关键字
    if "$ref" in repaired:
        return {"$ref": repaired["$ref"]}

    return repaired


def _fill_moonshot_missing_type(node: Dict[str, Any]) -> Dict[str, Any]:
    """为缺少 type 的 schema 节点推断合理的 type。"""
    if "type" in node and node["type"] not in {None, ""}:
        return node

    if "properties" in node or "required" in node or "additionalProperties" in node:
        inferred = "object"
    elif "items" in node or "prefixItems" in node:
        inferred = "array"
    elif "enum" in node and isinstance(node["enum"], list) and node["enum"]:
        sample = node["enum"][0]
        if isinstance(sample, bool):
            inferred = "boolean"
        elif isinstance(sample, int):
            inferred = "integer"
        elif isinstance(sample, float):
            inferred = "number"
        else:
            inferred = "string"
    else:
        inferred = "string"

    return {**node, "type": inferred}


def sanitize_moonshot_tool_parameters(parameters: Any) -> Dict[str, Any]:
    """标准化工具参数为 Moonshot 兼容格式。

    Args:
        parameters: 工具参数 schema

    Returns:
        Moonshot 兼容的参数 schema
    """
    if not isinstance(parameters, dict):
        return {"type": "object", "properties": {}}

    repaired = _repair_moonshot_schema(copy.deepcopy(parameters), is_schema=True)
    if not isinstance(repaired, dict):
        return {"type": "object", "properties": {}}

    # 顶层必须是 object schema
    if repaired.get("type") != "object":
        repaired["type"] = "object"
    if "properties" not in repaired:
        repaired["properties"] = {}

    return repaired


def sanitize_moonshot_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """应用 Moonshot schema 清理到所有工具。

    Args:
        tools: 工具列表

    Returns:
        清理后的工具列表
    """
    if not tools:
        return tools

    sanitized: List[Dict[str, Any]] = []
    any_change = False

    for tool in tools:
        if not isinstance(tool, dict):
            sanitized.append(tool)
            continue
        fn = tool.get("function")
        if not isinstance(fn, dict):
            sanitized.append(tool)
            continue
        params = fn.get("parameters")
        repaired = sanitize_moonshot_tool_parameters(params)
        if repaired is not params:
            any_change = True
            new_fn = {**fn, "parameters": repaired}
            sanitized.append({**tool, "function": new_fn})
        else:
            sanitized.append(tool)

    return sanitized if any_change else tools


def is_moonshot_model(model: str | None) -> bool:
    """检查是否为 Moonshot/Kimi 模型。

    匹配裸名称（kimi-k2.6, moonshotai/Kimi-K2.6）和聚合器前缀的 slug。

    Args:
        model: 模型名称

    Returns:
        是否为 Moonshot 模型
    """
    if not model:
        return False
    bare = model.strip().lower()
    # 取最后一个路径段
    tail = bare.rsplit("/", 1)[-1]
    if tail.startswith("kimi-") or tail == "kimi":
        return True
    if "moonshot" in bare or "/kimi" in bare or bare.startswith("kimi"):
        return True
    return False