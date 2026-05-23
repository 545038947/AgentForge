"""委托系统模块。"""

from hai_agent.delegation.config import (
    DelegationConfig,
    IsolationConfig,
)
from hai_agent.delegation.result import (
    DelegationResult,
    DelegationStrategy,
)
from hai_agent.delegation.manager import DelegationManager

__all__ = [
    "DelegationConfig",
    "IsolationConfig",
    "DelegationResult",
    "DelegationStrategy",
    "DelegationManager",
]