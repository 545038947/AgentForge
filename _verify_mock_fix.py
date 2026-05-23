"""验证 Mock 降级修复。"""
from hai_agent.providers.builtins.anthropic import AnthropicProvider
from hai_agent.types.errors import ProviderError

p = AnthropicProvider(model="test", api_key="fake-key")
try:
    list(p.stream([]))
    print("FAIL: 未抛出异常")
except ProviderError as e:
    print(f"OK: 抛出 ProviderError - {e}")
except Exception as e:
    print(f"FAIL: 抛出 {type(e).__name__} - {e}")
