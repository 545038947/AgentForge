"""AgentForge 核心模块。

提供迭代预算、重试工具、回退链、执行引擎、凭证池等核心功能。
"""

from agentforge.core.iteration_budget import IterationBudget
from agentforge.core.retry_utils import (
    jittered_backoff,
    RetryPolicy,
    RetryContext,
    sleep_with_interrupt,
)
from agentforge.core.fallback import FallbackProvider, FallbackChain
from agentforge.core.execution import (
    ExecutionConfig,
    ExecutionState,
    ExecutionResult,
    ExecutionEngine,
)
from agentforge.core.credential_pool import (
    PooledCredential,
    CredentialPool,
    STATUS_OK,
    STATUS_EXHAUSTED,
    STRATEGY_FILL_FIRST,
    STRATEGY_ROUND_ROBIN,
    STRATEGY_RANDOM,
    STRATEGY_LEAST_USED,
)
from agentforge.core.model_metadata import (
    ModelCapabilities,
    ModelMetadataProvider,
    DefaultModelMetadataProvider,
)
from agentforge.core.stream_accumulator import (
    ToolCallAccumulator,
    StreamAccumulator,
)
from agentforge.core.async_utils import (
    safe_schedule_threadsafe,
    to_thread,
    gather_with_concurrency,
    run_with_timeout,
    is_async_context,
    get_event_loop,
    AsyncIteratorWrapper,
    async_wrap,
)

__all__ = [
    # 迭代预算
    "IterationBudget",
    # 重试工具
    "jittered_backoff",
    "RetryPolicy",
    "RetryContext",
    "sleep_with_interrupt",
    # 回退链
    "FallbackProvider",
    "FallbackChain",
    # 执行引擎
    "ExecutionConfig",
    "ExecutionState",
    "ExecutionResult",
    "ExecutionEngine",
    # 凭证池
    "PooledCredential",
    "CredentialPool",
    "STATUS_OK",
    "STATUS_EXHAUSTED",
    "STRATEGY_FILL_FIRST",
    "STRATEGY_ROUND_ROBIN",
    "STRATEGY_RANDOM",
    "STRATEGY_LEAST_USED",
    # 模型能力
    "ModelCapabilities",
    "ModelMetadataProvider",
    "DefaultModelMetadataProvider",
    # 流式累积器
    "ToolCallAccumulator",
    "StreamAccumulator",
    # 异步工具
    "safe_schedule_threadsafe",
    "to_thread",
    "gather_with_concurrency",
    "run_with_timeout",
    "is_async_context",
    "get_event_loop",
    "AsyncIteratorWrapper",
    "async_wrap",
]
