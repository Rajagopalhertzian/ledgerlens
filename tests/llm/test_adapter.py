"""Tests for LLM adapter.

Tests the provider-agnostic LLM adapter with fake provider.
"""


import pytest
from pydantic import SecretStr

from src.ledgerlens.llm.adapter import (
    LLMAdapter,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ModelRole,
    TokenUsage,
)
from src.ledgerlens.llm.cache import CacheKey, DiskCache
from src.ledgerlens.llm.cost import CostTracker
from src.ledgerlens.llm.retry import CircuitBreaker, CircuitState


class TestModelConfig:
    """Tests for ModelConfig."""

    def test_model_config_creation(self):
        config = ModelConfig(
            model_id="gpt-4o",
            provider=LLMProvider.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key=SecretStr("test-key"),
        )
        assert config.model_id == "gpt-4o"
        assert config.provider == LLMProvider.OPENAI
        assert config.temperature == 0.0
        assert config.max_tokens == 4096


class TestLLMRequest:
    """Tests for LLMRequest."""

    def test_request_creation(self):
        request = LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0,
        )
        assert request.model == "gpt-4o"
        assert len(request.messages) == 1

    def test_cache_key_deterministic(self):
        request1 = LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0,
        )
        request2 = LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0,
        )
        # Same request should produce same cache key
        assert request1.cache_key().value == request2.cache_key().value

    def test_cache_key_excludes_metadata(self):
        request1 = LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            metadata={"request_id": "1"},
        )
        request2 = LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            metadata={"request_id": "2"},
        )
        # Metadata should not affect cache key
        assert request1.cache_key().value == request2.cache_key().value


class TestTokenUsage:
    """Tests for TokenUsage."""

    def test_token_usage_addition(self):
        usage1 = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        usage2 = TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300)
        combined = usage1 + usage2
        assert combined.prompt_tokens == 300
        assert combined.completion_tokens == 150
        assert combined.total_tokens == 450


class TestDiskCache:
    """Tests for DiskCache."""

    @pytest.fixture
    def cache_dir(self, tmp_path):
        return str(tmp_path / "cache")

    @pytest.fixture
    def cache(self, cache_dir):
        return DiskCache(cache_dir, max_size_mb=10)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        key = CacheKey("test-key-123")
        data = {"content": "test response", "model": "gpt-4o"}

        await cache.set(key, data)
        result = await cache.get(key)

        assert result is not None
        assert result["content"] == "test response"

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        key = CacheKey("non-existent-key")
        result = await cache.get(key)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_delete(self, cache):
        key = CacheKey("test-delete")
        data = {"content": "test"}

        await cache.set(key, data)
        assert await cache.get(key) is not None

        deleted = await cache.delete(key)
        assert deleted is True
        assert await cache.get(key) is None

    @pytest.mark.asyncio
    async def test_cache_clear(self, cache):
        for i in range(5):
            await cache.set(CacheKey(f"key-{i}"), {"data": i})

        count = await cache.clear()
        assert count == 5

        for i in range(5):
            assert await cache.get(CacheKey(f"key-{i}")) is None

    @pytest.mark.asyncio
    async def test_cache_stats(self, cache):
        await cache.set(CacheKey("key1"), {"data": "x" * 1000})
        await cache.set(CacheKey("key2"), {"data": "y" * 2000})

        stats = cache.stats()
        assert stats["entries"] == 2
        assert stats["total_size_mb"] > 0


class TestCostTracker:
    """Tests for CostTracker."""

    @pytest.fixture
    def tracker(self):
        return CostTracker(max_spend_usd=10.0)

    def test_record_cost(self, tracker):
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.record(0.01, usage, model="gpt-4o", role="strong")

        snapshot = tracker.get_snapshot()
        assert snapshot.total_cost_usd == 0.01
        assert snapshot.total_tokens == 1500
        assert snapshot.request_count == 1

    def test_can_spend_within_limit(self, tracker):
        assert tracker.can_spend(0.01) is True

    def test_can_spend_exceeds_limit(self, tracker):
        usage = TokenUsage(prompt_tokens=1000000, completion_tokens=500000, total_tokens=1500000)
        tracker.record(15.0, usage)  # Exceeds 10.0 limit
        assert tracker.can_spend(0.01) is False

    def test_remaining_budget(self, tracker):
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.record(0.01, usage)
        assert tracker.remaining_budget() == 9.99

    def test_get_breakdown(self, tracker):
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.record(0.01, usage, model="gpt-4o", role="strong")
        tracker.record(0.005, usage, model="gpt-4o-mini", role="cheap")

        breakdown = tracker.get_breakdown()
        assert breakdown["total"]["requests"] == 2
        assert "gpt-4o" in breakdown["by_model"]
        assert "strong" in breakdown["by_role"]
        assert breakdown["budget"]["max_spend_usd"] == 10.0

    def test_reset(self, tracker):
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.record(0.01, usage)
        tracker.reset()

        snapshot = tracker.get_snapshot()
        assert snapshot.total_cost_usd == 0.0
        assert snapshot.request_count == 0


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_closed(self):
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True

    def test_opens_after_threshold(self):
        breaker = CircuitBreaker(failure_threshold=3)

        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure()  # Third failure - should open
        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    def test_half_open_after_timeout(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)

        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        import time
        time.sleep(0.02)

        # State should transition to HALF_OPEN on next check
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.can_execute() is True

    def test_closes_after_successes_in_half_open(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, success_threshold=2)

        breaker.record_failure()
        breaker.record_failure()
        import time
        time.sleep(0.02)

        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()  # Second success - should close
        assert breaker.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)

        breaker.record_failure()
        breaker.record_failure()
        import time
        time.sleep(0.02)

        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_failure()  # Failure in half-open
        assert breaker.state == CircuitState.OPEN

    def test_reset(self):
        breaker = CircuitBreaker(failure_threshold=2)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True


class FakeLLMAdapter(LLMAdapter):
    """Fake adapter for testing without real API calls."""

    def __init__(
        self,
        responses: dict[str, str],
        cache_dir: str = "data/test_cache",
        *args,
        **kwargs,
    ):
        # Create minimal configs
        configs = {
            ModelRole.CHEAP: ModelConfig(
                model_id="fake-cheap",
                provider=LLMProvider.CUSTOM,
                base_url="http://fake",
                api_key=SecretStr("fake"),
            ),
            ModelRole.STRONG: ModelConfig(
                model_id="fake-strong",
                provider=LLMProvider.CUSTOM,
                base_url="http://fake",
                api_key=SecretStr("fake"),
            ),
            ModelRole.JUDGE: ModelConfig(
                model_id="fake-judge",
                provider=LLMProvider.CUSTOM,
                base_url="http://fake",
                api_key=SecretStr("fake"),
            ),
            ModelRole.VLM: ModelConfig(
                model_id="fake-vlm",
                provider=LLMProvider.CUSTOM,
                base_url="http://fake",
                api_key=SecretStr("fake"),
            ),
        }
        cache = DiskCache(cache_dir, max_size_mb=1)
        cost_tracker = CostTracker(max_spend_usd=100.0)
        super().__init__(configs, cache, cost_tracker)
        # Add pricing for fake models
        self.DEFAULT_PRICING["fake-cheap"] = (0.001, 0.002)
        self.DEFAULT_PRICING["fake-strong"] = (0.01, 0.02)
        self.DEFAULT_PRICING["fake-judge"] = (0.01, 0.02)
        self.DEFAULT_PRICING["fake-vlm"] = (0.01, 0.02)
        self._responses = responses
        self._call_count = 0

    async def _execute_with_retry(self, config, request):
        self._call_count += 1
        content = self._responses.get(config.model_id, "default response")
        return LLMResponse(
            content=content,
            model=config.model_id,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            cost_usd=0.001,
            latency_ms=100.0,
            cached=False,
            request_id="test",
            role=ModelRole.CHEAP,
            raw_response={},
        )


class TestLLMAdapter:
    """Tests for LLMAdapter with fake provider."""

    @pytest.fixture
    def adapter(self, tmp_path):
        """Create adapter with unique cache directory per test."""
        cache_dir = tmp_path / "llm_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return FakeLLMAdapter(
            responses={
                "fake-cheap": "cheap response",
                "fake-strong": "strong response",
                "fake-judge": "judge response",
                "fake-vlm": "vlm response",
            },
            cache_dir=str(cache_dir),
        )

    @pytest.mark.asyncio
    async def test_chat_cheap_role(self, adapter):
        response = await adapter.chat(
            role=ModelRole.CHEAP,
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert response.content == "cheap response"
        assert response.role == ModelRole.CHEAP
        assert response.model == "fake-cheap"

    @pytest.mark.asyncio
    async def test_chat_strong_role(self, adapter):
        response = await adapter.chat(
            role=ModelRole.STRONG,
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert response.content == "strong response"
        assert response.role == ModelRole.STRONG

    @pytest.mark.asyncio
    async def test_chat_caching(self, adapter):
        # First call
        response1 = await adapter.chat(
            role=ModelRole.CHEAP,
            messages=[{"role": "user", "content": "Hello"}],
            use_cache=True,
        )
        assert response1.cached is False

        # Second call with same request should hit cache
        response2 = await adapter.chat(
            role=ModelRole.CHEAP,
            messages=[{"role": "user", "content": "Hello"}],
            use_cache=True,
        )
        assert response2.cached is True
        assert response2.content == "cheap response"

    @pytest.mark.asyncio
    async def test_chat_no_cache(self, adapter):
        response1 = await adapter.chat(
            role=ModelRole.CHEAP,
            messages=[{"role": "user", "content": "Hello"}],
            use_cache=False,
        )
        response2 = await adapter.chat(
            role=ModelRole.CHEAP,
            messages=[{"role": "user", "content": "Hello"}],
            use_cache=False,
        )
        # Both should not be cached
        assert response1.cached is False
        assert response2.cached is False

    @pytest.mark.asyncio
    async def test_cost_tracking(self, adapter):
        initial_cost = adapter.cost_tracker.get_snapshot().total_cost_usd

        await adapter.chat(
            role=ModelRole.CHEAP,
            messages=[{"role": "user", "content": "Hello"}],
        )

        final_cost = adapter.cost_tracker.get_snapshot().total_cost_usd
        assert final_cost > initial_cost

    @pytest.mark.asyncio
    async def test_spend_limit_enforced(self, adapter):
        # Test cost tracker spend limit directly (bypassing adapter's estimate)
        tracker = adapter.cost_tracker
        tracker.max_spend_usd = 0.01

        # Record some costs
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.record(0.003, usage)
        assert tracker.can_spend(0.005) is True   # 0.003 + 0.005 = 0.008 <= 0.01
        assert tracker.can_spend(0.008) is False  # 0.003 + 0.008 = 0.011 > 0.01

        tracker.record(0.005, usage)  # Total now 0.008
        assert tracker.can_spend(0.001) is True   # 0.008 + 0.001 = 0.009 <= 0.01
        assert tracker.can_spend(0.002) is True   # 0.008 + 0.002 = 0.010 <= 0.01 (boundary)
        assert tracker.can_spend(0.003) is False  # 0.008 + 0.003 = 0.011 > 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
