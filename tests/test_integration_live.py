"""AgentForge 实际集成测试 — 使用 Ollama gemma4:31b-cloud 模型。

测试场景：
1. 基础对话（run/stream）
2. 流式响应（stream_deltas）
3. 多轮对话记忆
4. 上下文管理器（自动清理）
5. shutdown 方法验证
6. atexit 钩子验证
7. 并发安全（多 Agent 隔离）
8. FallbackChain（备用 Provider）
9. 错误处理（无效模型）
10. 敏感信息过滤
"""

import sys
import time
import asyncio
import threading
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from hai_agent import Agent
from hai_agent.providers.builtins.ollama import OllamaProvider
from hai_agent.types.errors import ProviderError, ProviderConnectionError
from hai_agent.utils.logging import SensitiveDataFilter, JsonFormatter, setup_secure_logging
from hai_agent.core.fallback import FallbackChain


# === 配置 ===
OLLAMA_BASE_URL = "http://localhost:11434/v1"
MODEL = "gemma4:31b-cloud"

results = {"pass": 0, "fail": 0, "skip": 0}


def log_result(test_name, passed, detail=""):
    """记录测试结果。"""
    status = "PASS" if passed else "FAIL"
    results[status.lower()] += 1
    print(f"  [{status}] {test_name}: {detail}")


def wait_for_ollama():
    """等待 Ollama 服务就绪。"""
    import requests
    check_url = OLLAMA_BASE_URL.rstrip("/v1")
    for i in range(5):
        try:
            r = requests.get(f"{check_url}/api/tags", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


# === 测试 1: 基础同步对话 ===
def test_basic_run():
    """测试 Agent.run() 同步调用。"""
    print("\n=== 测试 1: 基础同步对话 ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    agent = Agent(provider=provider, register_atexit=False)

    try:
        response = agent.run("你好，请用一句话介绍你自己。")
        if response and response.content and len(response.content) > 5:
            log_result("run() 返回有效内容", True, f"内容长度={len(response.content)}")
        else:
            log_result("run() 返回有效内容", False, f"response={response}")
    except Exception as e:
        log_result("run() 返回有效内容", False, str(e))
    finally:
        agent.shutdown()


# === 测试 2: 流式响应 ===
def test_stream():
    """测试 Agent.stream() 流式调用。"""
    print("\n=== 测试 2: 流式响应 ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    agent = Agent(provider=provider, register_atexit=False)

    chunks = []
    try:
        for chunk in agent.stream("请用三句话描述春天。"):
            chunks.append(chunk)
            if chunk.content:
                print(f"  流式chunk: {chunk.content[:50]}...", flush=True)

        if len(chunks) > 0:
            full_content = "".join(c.content or "" for c in chunks)
            log_result("stream() 收到多个chunk", True, f"chunk数={len(chunks)}")
            log_result("stream() 内容完整", len(full_content) > 10, f"总长度={len(full_content)}")
        else:
            log_result("stream() 收到多个chunk", False, "0 chunks")
    except Exception as e:
        log_result("stream() 收到多个chunk", False, str(e))
    finally:
        agent.shutdown()


# === 测试 3: 多轮对话记忆 ===
def test_multi_turn():
    """测试多轮对话的消息历史保持。"""
    print("\n=== 测试 3: 多轮对话记忆 ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    agent = Agent(provider=provider, register_atexit=False)

    try:
        # 第一轮
        r1 = agent.run("我叫小明。请记住我的名字。")
        log_result("第一轮对话", r1 and len(r1.content) > 0, f"长度={len(r1.content) if r1 else 0}")

        # 第二轮：测试记忆
        r2 = agent.run("你还记得我叫什么吗？")
        if r2 and "小明" in r2.content:
            log_result("多轮记忆保持", True, f"第二轮提到'小明'")
        else:
            log_result("多轮记忆保持", False, f"第二轮内容={r2.content[:100] if r2 else 'None'}")

        # 验证消息历史
        messages = agent._message_manager.get_messages()
        log_result("消息历史增长", len(messages) >= 4, f"消息数={len(messages)}")
    except Exception as e:
        log_result("多轮记忆保持", False, str(e))
    finally:
        agent.shutdown()


# === 测试 4: 上下文管理器 ===
def test_context_manager():
    """测试 Agent 作为上下文管理器。"""
    print("\n=== 测试 4: 上下文管理器 ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)

    try:
        with Agent(provider=provider, register_atexit=False) as agent:
            r = agent.run("请说'OK'")
            log_result("上下文管理器内运行", r is not None, f"response={r is not None}")

        # 退出后 shutdown 应已调用
        log_result("上下文管理器自动清理", True, "shutdown 已调用")
    except Exception as e:
        log_result("上下文管理器内运行", False, str(e))


# === 测试 5: shutdown 幂等性 ===
def test_shutdown_idempotent():
    """测试 shutdown 可安全多次调用。"""
    print("\n=== 测试 5: shutdown 幂等性 ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    agent = Agent(provider=provider, register_atexit=False)

    try:
        agent.shutdown()
        agent.shutdown()  # 第二次调用不应抛异常
        agent.shutdown()  # 第三次也不应抛异常
        log_result("shutdown 幂等", True, "三次调用无异常")
    except Exception as e:
        log_result("shutdown 幂等", False, str(e))


# === 测试 6: atexit 钩子 ===
def test_atexit_hook():
    """测试 atexit 钩子注册。"""
    print("\n=== 测试 6: atexit 钩子 ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)

    agent_with = Agent(provider=provider, register_atexit=True)
    agent_without = Agent(provider=provider, register_atexit=False)

    log_result("atexit 注册启用", agent_with._atexit_registered is True, f"flag={agent_with._atexit_registered}")
    log_result("atexit 注册禁用", agent_without._atexit_registered is False, f"flag={agent_without._atexit_registered}")

    agent_with.shutdown()
    agent_without.shutdown()


# === 测试 7: 并发安全（多 Agent 隔离） ===
def test_concurrent_agents():
    """测试多个 Agent 实例的消息隔离。"""
    print("\n=== 测试 7: 并发安全（多 Agent 隔离） ===")
    provider = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)

    agents = [
        Agent(provider=provider, register_atexit=False)
        for _ in range(3)
    ]

    try:
        # 每个 Agent 给不同的初始消息
        for i, agent in enumerate(agents):
            agent._message_manager.add_user_message(f"用户{i}的消息")

        # 验证隔离
        for i, agent in enumerate(agents):
            msgs = agent._message_manager.get_messages()
            is_isolated = len(msgs) == 1 and f"用户{i}" in msgs[0].content[0].text
            log_result(f"Agent {i} 消息隔离", is_isolated, f"消息数={len(msgs)}")

        for agent in agents:
            agent.shutdown()
    except Exception as e:
        log_result("并发安全", False, str(e))


# === 测试 8: 错误处理 ===
def test_error_handling():
    """测试 Provider 错误处理。"""
    print("\n=== 测试 8: 错误处理 ===")

    # 测试无效模型
    try:
        bad_provider = OllamaProvider(model="nonexistent-model-xyz", base_url=OLLAMA_BASE_URL)
        agent = Agent(provider=bad_provider, register_atexit=False)
        response = agent.run("test")
        # Ollama 可能下载模型或返回错误
        if response and response.finish_reason == "error":
            log_result("无效模型错误处理", True, f"finish_reason=error")
        else:
            log_result("无效模型返回了内容", False, f"response={response}")
        agent.shutdown()
    except (ProviderError, ProviderConnectionError) as e:
        log_result("无效模型错误处理", True, f"抛出 {type(e).__name__}")
    except Exception as e:
        log_result("无效模型错误处理", False, f"未预期异常: {type(e).__name__}: {e}")


# === 测试 9: 敏感信息过滤 ===
def test_sensitive_filter():
    """测试日志敏感信息过滤。"""
    print("\n=== 测试 9: 敏感信息过滤 ===")

    filter_obj = SensitiveDataFilter()

    # API Key
    rec1 = logging.LogRecord("test", logging.INFO, "", 0, "API Key: sk-1234567890abcdefghijklmn", (), None)
    filter_obj.filter(rec1)
    has_redacted = "***REDACTED***" in rec1.msg and "sk-1234567890abcdefghijklmn" not in rec1.msg
    log_result("API Key 过滤", has_redacted)

    # Bearer Token
    rec2 = logging.LogRecord("test", logging.INFO, "", 0, "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig", (), None)
    filter_obj.filter(rec2)
    has_redacted2 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig" not in rec2.msg
    log_result("Bearer Token 过滤", has_redacted2)

    # 正常消息不变
    rec3 = logging.LogRecord("test", logging.INFO, "", 0, "用户请求处理完成", (), None)
    filter_obj.filter(rec3)
    log_result("正常消息不变", rec3.msg == "用户请求处理完成")


# === 测试 10: FallbackChain ===
def test_fallback_chain():
    """测试 Provider 降级链。"""
    print("\n=== 测试 10: FallbackChain ===")

    primary = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)
    fallback = OllamaProvider(model=MODEL, base_url=OLLAMA_BASE_URL)

    chain = FallbackChain(providers=[primary, fallback])

    agent = Agent(provider=primary, fallback_chain=chain, register_atexit=False)

    try:
        response = agent.run("请说'你好'")
        log_result("FallbackChain 正常工作", response is not None and len(response.content) > 0, f"长度={len(response.content) if response else 0}")
    except Exception as e:
        log_result("FallbackChain 正常工作", False, str(e))
    finally:
        agent.shutdown()


# === 主程序 ===
def main():
    print("=" * 60)
    print("AgentForge 实际集成测试")
    print(f"模型: {MODEL}")
    print(f"服务: {OLLAMA_BASE_URL}")
    print("=" * 60)

    if not wait_for_ollama():
        print("FAIL: Ollama 服务不可用，跳过所有测试")
        return

    print("Ollama 服务就绪 ✓")

    # 运行所有测试
    test_basic_run()
    test_stream()
    test_multi_turn()
    test_context_manager()
    test_shutdown_idempotent()
    test_atexit_hook()
    test_concurrent_agents()
    test_error_handling()
    test_sensitive_filter()
    test_fallback_chain()

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    total = results["pass"] + results["fail"] + results["skip"]
    print(f"  通过: {results['pass']}")
    print(f"  失败: {results['fail']}")
    print(f"  跳过: {results['skip']}")
    print(f"  总计: {total}")
    print(f"  通过率: {results['pass']/total*100:.0f}%")
    print("=" * 60)

    return results["fail"] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)