"""LedgerLens LLM Adapter Package.

Provider-agnostic LLM interface with:
- Role-based model selection (CHEAP, STRONG, JUDGE, VLM)
- Disk cache keyed by request hash
- Token and cost accounting
- Timeouts, retries with jitter, circuit breaker
- Fallback model support
"""

from .adapter import LLMAdapter, LLMRequest, LLMResponse, ModelRole, get_adapter
from .cache import CacheKey, DiskCache
from .cost import CostTracker, TokenUsage
from .retry import CircuitBreaker, RetryPolicy

__all__ = [
    "LLMAdapter",
    "LLMResponse",
    "LLMRequest",
    "ModelRole",
    "get_adapter",
    "DiskCache",
    "CacheKey",
    "CostTracker",
    "TokenUsage",
    "RetryPolicy",
    "CircuitBreaker",
]
