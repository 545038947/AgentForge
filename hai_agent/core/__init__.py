"""AgentForge 核心模块。

提供迭代预算、重试工具、回退链、执行引擎、凭证池等核心功能。
"""

from hai_agent.core.iteration_budget import IterationBudget
from hai_agent.core.retry_utils import (
    jittered_backoff,
    RetryPolicy,
    RetryContext,
    sleep_with_interrupt,
)
from hai_agent.core.fallback import FallbackProvider, FallbackChain
from hai_agent.core.execution import (
    ExecutionConfig,
    ExecutionState,
    ExecutionResult,
    ExecutionEngine,
)
from hai_agent.core.credential_pool import (
    PooledCredential,
    CredentialPool,
    STATUS_OK,
    STATUS_EXHAUSTED,
    STRATEGY_FILL_FIRST,
    STRATEGY_ROUND_ROBIN,
    STRATEGY_RANDOM,
    STRATEGY_LEAST_USED,
)
from hai_agent.core.model_metadata import (
    ModelCapabilities,
    ModelMetadataProvider,
    DefaultModelMetadataProvider,
)
from hai_agent.core.stream_accumulator import (
    ToolCallAccumulator,
    StreamAccumulator,
)
from hai_agent.core.async_utils import (
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
