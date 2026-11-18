"""Token usage and cost tracking for LLM calls.

Tracks cumulative spend, enforces MAX_SPEND_USD limit.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenUsage:
    """Token usage for a single request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass
class CostSnapshot:
    """Snapshot of cost tracking state."""

    total_cost_usd: float
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    request_count: int
    started_at: float
    last_request_at: float | None = None


class CostTracker:
    """Tracks LLM token usage and costs with spend limit enforcement.

    Thread-safe for concurrent access.
    """

    def __init__(self, max_spend_usd: float = 10.0):
        self.max_spend_usd = max_spend_usd
        self._lock = threading.RLock()
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._request_count = 0
        self._started_at = time.time()
        self._last_request_at: float | None = None
        self._by_model: dict[str, dict[str, float]] = {}
        self._by_role: dict[str, dict[str, float]] = {}

    def record(self, cost_usd: float, usage: TokenUsage, model: str = "", role: str = "") -> None:
        """Record a request's cost and token usage."""
        with self._lock:
            self._total_cost_usd += cost_usd
            self._total_tokens += usage.total_tokens
            self._total_prompt_tokens += usage.prompt_tokens
            self._total_completion_tokens += usage.completion_tokens
            self._request_count += 1
            self._last_request_at = time.time()

            # Track by model
            if model:
                if model not in self._by_model:
                    self._by_model[model] = {"cost": 0.0, "tokens": 0, "requests": 0}
                self._by_model[model]["cost"] += cost_usd
                self._by_model[model]["tokens"] += usage.total_tokens
                self._by_model[model]["requests"] += 1

            # Track by role
            if role:
                if role not in self._by_role:
                    self._by_role[role] = {"cost": 0.0, "tokens": 0, "requests": 0}
                self._by_role[role]["cost"] += cost_usd
                self._by_role[role]["tokens"] += usage.total_tokens
                self._by_role[role]["requests"] += 1

            logger.debug(
                "Cost recorded",
                cost_usd=cost_usd,
                total_cost_usd=self._total_cost_usd,
                tokens=usage.total_tokens,
                model=model,
                role=role,
            )

    def can_spend(self, estimated_cost_usd: float) -> bool:
        """Check if estimated cost would exceed limit."""
        with self._lock:
            return (self._total_cost_usd + estimated_cost_usd) <= self.max_spend_usd

    def remaining_budget(self) -> float:
        """Get remaining budget in USD."""
        with self._lock:
            return max(0.0, self.max_spend_usd - self._total_cost_usd)

    def get_snapshot(self) -> CostSnapshot:
        """Get current cost tracking snapshot."""
        with self._lock:
            return CostSnapshot(
                total_cost_usd=self._total_cost_usd,
                total_tokens=self._total_tokens,
                total_prompt_tokens=self._total_prompt_tokens,
                total_completion_tokens=self._total_completion_tokens,
                request_count=self._request_count,
                started_at=self._started_at,
                last_request_at=self._last_request_at,
            )

    def get_breakdown(self) -> dict[str, Any]:
        """Get detailed cost breakdown by model and role."""
        with self._lock:
            return {
                "total": {
                    "cost_usd": self._total_cost_usd,
                    "tokens": self._total_tokens,
                    "prompt_tokens": self._total_prompt_tokens,
                    "completion_tokens": self._total_completion_tokens,
                    "requests": self._request_count,
                },
                "by_model": dict(self._by_model),
                "by_role": dict(self._by_role),
                "budget": {
                    "max_spend_usd": self.max_spend_usd,
                    "spent_usd": self._total_cost_usd,
                    "remaining_usd": self.remaining_budget(),
                    "utilization_pct": (self._total_cost_usd / self.max_spend_usd * 100)
                    if self.max_spend_usd > 0
                    else 0,
                },
            }

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        with self._lock:
            self._total_cost_usd = 0.0
            self._total_tokens = 0
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._request_count = 0
            self._started_at = time.time()
            self._last_request_at = None
            self._by_model.clear()
            self._by_role.clear()


# Global cost tracker instance
_global_tracker: CostTracker | None = None
_tracker_lock = threading.Lock()


def get_cost_tracker(max_spend_usd: float = 10.0) -> CostTracker:
    """Get or create global cost tracker."""
    global _global_tracker
    with _tracker_lock:
        if _global_tracker is None:
            _global_tracker = CostTracker(max_spend_usd)
        return _global_tracker


def reset_cost_tracker() -> None:
    """Reset global cost tracker (for testing)."""
    global _global_tracker
    with _tracker_lock:
        _global_tracker = None
