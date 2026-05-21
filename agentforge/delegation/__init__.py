"""委托系统模块。"""

from agentforge.delegation.config import (
    DelegationConfig,
    IsolationConfig,
)
from agentforge.delegation.result import (
    DelegationResult,
    DelegationStrategy,
)
from agentforge.delegation.manager import DelegationManager

__all__ = [
    "DelegationConfig",
    "IsolationConfig",
    "DelegationResult",
    "DelegationStrategy",
    "DelegationManager",
]