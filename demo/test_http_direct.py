"""直接测试 MCP HTTP/SSE 连接 - 详细错误。"""

import asyncio
import traceback
import httpx


async def test_mcp_http():
    """测试 MCP HTTP 连接。"""
    url = "https://mcp.hai168.xyz/sse"

    print(f"测试连接: {url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 测试 GET SSE
        print("\n1. 测试 GET SSE 连接...")
        try:
            response = await client.get(
                url,
                headers={"Accept": "text/event-stream"},
            )
            print(f"状态码: {response.status_code}")
            print(f"响应头: {dict(response.headers)}")
            print(f"响应内容前 500 字符: {response.text[:500]}")
        except Exception as e:
            print(f"GET 失败:")
            traceback.print_exc()

        # 测试 POST
        print("\n2. 测试 POST JSON-RPC...")
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
            response = await client.post(
                url,
                json=request,
                headers={"Content-Type": "application/json"},
            )
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:1000]}")
        except Exception as e:
            print(f"POST 失败:")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_mcp_http())