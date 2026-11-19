"""Provider-agnostic LLM Adapter for LedgerLens.

Supports OpenAI-compatible endpoints (OpenAI, Groq, NVIDIA NIM, Ollama, etc.)
and Anthropic API. Reads ONLY LLM_* environment variables, never ANTHROPIC_*
or OPENAI_* (those are for Claude Code itself).
"""

import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, SecretStr
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .cache import CacheKey, DiskCache
from .cost import CostTracker, TokenUsage
from .retry import CircuitBreaker, CircuitBreakerOpenError

logger = structlog.get_logger(__name__)


class ModelRole(StrEnum):
    """Model roles for different tasks."""

    CHEAP = "cheap"  # Classification, routing, cheap parsing
    STRONG = "strong"  # Extraction, complex reasoning
    JUDGE = "judge"  # Evaluation (must differ from model being graded)
    VLM = "vlm"  # Vision-language extraction


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    NVIDIA = "nvidia"
    OLLAMA = "ollama"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a specific model role."""

    model_id: str
    provider: LLMProvider
    base_url: str
    api_key: SecretStr
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout_seconds: float = 60.0
    max_retries: int = 3
    fallback_model_id: str | None = None


class LLMRequest(BaseModel):
    """LLM request with structured inputs."""

    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.0
    max_tokens: int = 4096
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def cache_key(self) -> CacheKey:
        """Generate deterministic cache key from request."""
        # Exclude metadata from cache key
        key_data = self.model_dump(exclude={"metadata"})
        key_str = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
        return CacheKey(hashlib.sha256(key_str.encode()).hexdigest()[:32])


class LLMResponse(BaseModel):
    """LLM response with usage and cost tracking."""

    content: str
    model: str
    usage: TokenUsage
    cost_usd: float
    latency_ms: float
    cached: bool = False
    request_id: str
    role: ModelRole
    raw_response: dict[str, Any] = Field(default_factory=dict, exclude=True)


class LLMError(Exception):
    """Base exception for LLM errors."""

    def __init__(self, message: str, provider: LLMProvider, model: str, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.retryable = retryable


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""

    def __init__(self, message: str, provider: LLMProvider, model: str, retry_after: float | None = None):
        super().__init__(message, provider, model, retryable=True)
        self.retry_after = retry_after


class LLMTimeoutError(LLMError):
    """Request timeout."""

    def __init__(self, message: str, provider: LLMProvider, model: str):
        super().__init__(message, provider, model, retryable=True)


class LLMAdapter:
    """Provider-agnostic LLM adapter with caching, cost tracking, retries, and circuit breaker.

    Usage:
        adapter = LLMAdapter.from_env()
        response = await adapter.chat(role=ModelRole.STRONG, messages=[...])
    """

    # Pricing per 1M tokens (input, output) in USD - update from provider docs
    DEFAULT_PRICING = {
        # OpenAI
        "gpt-4o": (5.00, 15.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        # Anthropic
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        "claude-3-5-haiku-20241022": (0.80, 4.00),
        "claude-3-opus-20240229": (15.00, 75.00),
        # Groq (free tier pricing shown)
        "llama-3.1-70b-versatile": (0.00, 0.00),
        "llama-3.1-8b-instant": (0.00, 0.00),
        "mixtral-8x7b-32768": (0.00, 0.00),
        # NVIDIA NIM
        "nemotron-3-ultra": (0.00, 0.00),  # Check current pricing
    }

    def __init__(
        self,
        configs: dict[ModelRole, ModelConfig],
        cache: DiskCache,
        cost_tracker: CostTracker,
        max_spend_usd: float = 10.0,
        default_timeout: float = 60.0,
    ):
        self.configs = configs
        self.cache = cache
        self.cost_tracker = cost_tracker
        self.max_spend_usd = max_spend_usd
        self.default_timeout = default_timeout
        self._clients: dict[LLMProvider, httpx.AsyncClient] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    @classmethod
    def from_env(cls, cache_dir: str = "data/llm_cache") -> "LLMAdapter":
        """Create adapter from environment variables."""
        provider = LLMProvider(os.getenv("LLM_PROVIDER", "openai").lower())
        base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        api_key = os.getenv("LLM_API_KEY", "")

        if not api_key:
            msg = "LLM_API_KEY environment variable is required"
            raise ValueError(msg)

        # Model role mappings
        role_models = {
            ModelRole.CHEAP: os.getenv("CHEAP_MODEL", "gpt-4o-mini"),
            ModelRole.STRONG: os.getenv("STRONG_MODEL", "gpt-4o"),
            ModelRole.JUDGE: os.getenv("JUDGE_MODEL", "gpt-4o"),
            ModelRole.VLM: os.getenv("VLM_MODEL", "gpt-4o"),
        }

        # Validate judge model differs from strong model (M2+ requirement)
        if role_models[ModelRole.JUDGE] == role_models[ModelRole.STRONG]:
            logger.warning(
                "JUDGE_MODEL equals STRONG_MODEL - they should differ for unbiased evaluation",
                judge=role_models[ModelRole.JUDGE],
                strong=role_models[ModelRole.STRONG],
            )

        configs = {}
        for role, model_id in role_models.items():
            configs[role] = ModelConfig(
                model_id=model_id, provider=provider, base_url=base_url, api_key=SecretStr(api_key)
            )

        cache = DiskCache(cache_dir)
        cost_tracker = CostTracker(max_spend_usd=float(os.getenv("MAX_SPEND_USD", "10.0")))

        return cls(
            configs=configs,
            cache=cache,
            cost_tracker=cost_tracker,
            max_spend_usd=float(os.getenv("MAX_SPEND_USD", "10.0")),
        )

    def _get_client(self, provider: LLMProvider) -> httpx.AsyncClient:
        """Get or create HTTP client for provider."""
        if provider not in self._clients:
            self._clients[provider] = httpx.AsyncClient(
                timeout=httpx.Timeout(self.default_timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._clients[provider]

    def _get_circuit_breaker(self, model_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for model."""
        if model_id not in self._circuit_breakers:
            self._circuit_breakers[model_id] = CircuitBreaker(
                failure_threshold=5, recovery_timeout=60.0, expected_exception=LLMError
            )
        return self._circuit_breakers[model_id]

    def _get_pricing(self, model_id: str) -> tuple[float, float]:
        """Get pricing for model (input, output per 1M tokens)."""
        return self.DEFAULT_PRICING.get(model_id, (0.0, 0.0))

    def _calculate_cost(self, model_id: str, usage: TokenUsage) -> float:
        """Calculate cost in USD for token usage."""
        input_price, output_price = self._get_pricing(model_id)
        input_cost = (usage.prompt_tokens / 1_000_000) * input_price
        output_cost = (usage.completion_tokens / 1_000_000) * output_price
        return input_cost + output_cost

    async def chat(
        self,
        role: ModelRole,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        use_cache: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send chat completion request with caching, retries, and cost tracking.

        Args:
            role: Model role (CHEAP, STRONG, JUDGE, VLM)
            messages: List of message dicts with role and content
            temperature: Override default temperature (0.0 for deterministic)
            max_tokens: Override default max tokens
            response_format: Structured output format (e.g., {"type": "json_object"})
            tools: Function calling tools
            tool_choice: Tool choice strategy
            use_cache: Whether to use disk cache
            metadata: Additional metadata for tracking

        Returns:
            LLMResponse with content, usage, cost, and latency

        """
        config = self.configs[role]
        request_id = hashlib.sha256(f"{role}{time.time()}".encode()).hexdigest()[:16]

        # Build request
        request = LLMRequest(
            model=config.model_id,
            messages=messages,
            temperature=temperature if temperature is not None else config.temperature,
            max_tokens=max_tokens or config.max_tokens,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            metadata=metadata or {},
        )

        # Check cache
        cache_key = request.cache_key()
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info("LLM cache hit", role=role.value, model=config.model_id, request_id=request_id)
                response = LLMResponse.model_validate(cached)
                response.cached = True
                return response

        # Check circuit breaker
        breaker = self._get_circuit_breaker(config.model_id)
        if not breaker.can_execute():
            msg = f"Circuit breaker open for {config.model_id}"
            raise CircuitBreakerOpenError(msg)

        # Check spend limit - estimate cost based on model pricing and max_tokens
        input_price, output_price = self._get_pricing(config.model_id)
        estimated_input_tokens = min(request.max_tokens, 4096)  # Rough estimate
        estimated_output_tokens = min(request.max_tokens, 4096)
        input_cost = (estimated_input_tokens / 1_000_000) * input_price
        output_cost = (estimated_output_tokens / 1_000_000) * output_price
        estimated_cost = input_cost + output_cost
        # Add small buffer
        estimated_cost = max(estimated_cost * 1.5, 0.0001)

        if not self.cost_tracker.can_spend(estimated_cost):
            msg = f"Max spend limit (${self.max_spend_usd}) reached"
            raise LLMError(msg, config.provider, config.model_id, retryable=False)

        # Execute with retries
        start_time = time.perf_counter()
        try:
            response = await self._execute_with_retry(config, request)
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            breaker.record_failure()

            # Try fallback model if available
            if config.fallback_model_id and not isinstance(e, CircuitBreakerOpenError):
                logger.warning(
                    "Primary model failed, trying fallback",
                    primary=config.model_id,
                    fallback=config.fallback_model_id,
                    error=str(e),
                )
                fallback_config = ModelConfig(
                    model_id=config.fallback_model_id,
                    provider=config.provider,
                    base_url=config.base_url,
                    api_key=config.api_key,
                )
                try:
                    response = await self._execute_with_retry(fallback_config, request)
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    cost_usd = self._calculate_cost(fallback_config.model_id, response.usage)
                    self.cost_tracker.record(cost_usd, response.usage)

                    return LLMResponse(
                        content=response.content,
                        model=fallback_config.model_id,
                        usage=response.usage,
                        cost_usd=cost_usd,
                        latency_ms=latency_ms,
                        cached=False,
                        request_id=request_id,
                        role=role,
                        raw_response=response.raw_response,
                    )
                except Exception as fallback_error:
                    logger.exception("Fallback model also failed", error=str(fallback_error))

            logger.exception(
                "LLM request failed",
                role=role.value,
                model=config.model_id,
                request_id=request_id,
                error=str(e),
                latency_ms=latency_ms,
            )
            raise
        else:
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Calculate cost
            cost_usd = self._calculate_cost(config.model_id, response.usage)

            # Create final response
            llm_response = LLMResponse(
                content=response.content,
                model=config.model_id,
                usage=response.usage,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                cached=False,
                request_id=request_id,
                role=role,
                raw_response=response.raw_response,
            )

            # Record cost
            self.cost_tracker.record(cost_usd, response.usage)

            # Cache response
            if use_cache:
                await self.cache.set(cache_key, llm_response.model_dump())

            # Record success for circuit breaker
            breaker.record_success()

            logger.info(
                "LLM request completed",
                role=role.value,
                model=config.model_id,
                request_id=request_id,
                tokens=response.usage.total_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )

            return llm_response

    async def _execute_with_retry(self, config: ModelConfig, request: LLMRequest) -> "LLMResponse":
        """Execute request with provider-specific logic and retries."""

        @retry(
            wait=wait_exponential_jitter(initial=1, max=10),
            stop=stop_after_attempt(config.max_retries),
            retry=retry_if_exception_type((LLMTimeoutError, LLMRateLimitError, httpx.TimeoutException)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        async def _do_request() -> LLMResponse:
            client = self._get_client(config.provider)

            openai_compatible = (
                LLMProvider.OPENAI,
                LLMProvider.GROQ,
                LLMProvider.NVIDIA,
                LLMProvider.OLLAMA,
                LLMProvider.CUSTOM,
            )
            if config.provider in openai_compatible:
                return await self._openai_compatible_request(client, config, request)
            if config.provider == LLMProvider.ANTHROPIC:
                return await self._anthropic_request(client, config, request)
            msg = f"Unsupported provider: {config.provider}"
            raise LLMError(msg, config.provider, config.model_id)

        return await _do_request()

    async def _openai_compatible_request(
        self, client: httpx.AsyncClient, config: ModelConfig, request: LLMRequest
    ) -> LLMResponse:
        """Make request to OpenAI-compatible endpoint."""
        headers = {"Authorization": f"Bearer {config.api_key.get_secret_value()}", "Content-Type": "application/json"}

        payload = request.model_dump(exclude_none=True, exclude={"metadata"})

        try:
            response = await client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=config.timeout_seconds,
            )
        except httpx.TimeoutException as e:
            msg = f"Request timeout: {e}"
            raise LLMTimeoutError(msg, config.provider, config.model_id) from e

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            msg = "Rate limit exceeded"
            raise LLMRateLimitError(
                msg, config.provider, config.model_id, retry_after=float(retry_after) if retry_after else None
            )

        if response.status_code >= 400:
            msg = f"API error {response.status_code}: {response.text}"
            raise LLMError(msg, config.provider, config.model_id, retryable=response.status_code >= 500)

        data = response.json()

        # Extract usage
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        # Extract content
        content = data["choices"][0]["message"]["content"] or ""

        return LLMResponse(
            content=content,
            model=config.model_id,
            usage=usage,
            cost_usd=0.0,  # Will be calculated by caller
            latency_ms=0.0,  # Will be calculated by caller
            cached=False,
            request_id="",
            role=ModelRole.CHEAP,  # Will be overridden
            raw_response=data,
        )

    async def _anthropic_request(
        self, client: httpx.AsyncClient, config: ModelConfig, request: LLMRequest
    ) -> LLMResponse:
        """Make request to Anthropic API."""
        headers = {
            "x-api-key": config.api_key.get_secret_value(),
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        # Convert OpenAI format to Anthropic format
        system_prompt = ""
        messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": config.model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": system_prompt,
            "messages": messages,
        }

        try:
            response = await client.post(
                f"{config.base_url.rstrip('/')}/v1/messages",
                headers=headers,
                json=payload,
                timeout=config.timeout_seconds,
            )
        except httpx.TimeoutException as e:
            msg = f"Request timeout: {e}"
            raise LLMTimeoutError(msg, config.provider, config.model_id) from e

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            msg = "Rate limit exceeded"
            raise LLMRateLimitError(
                msg, config.provider, config.model_id, retry_after=float(retry_after) if retry_after else None
            )

        if response.status_code >= 400:
            msg = f"API error {response.status_code}: {response.text}"
            raise LLMError(msg, config.provider, config.model_id, retryable=response.status_code >= 500)

        data = response.json()

        # Extract usage
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
        )

        # Extract content
        content = "".join(block["text"] for block in data.get("content", []) if block["type"] == "text")

        return LLMResponse(
            content=content,
            model=config.model_id,
            usage=usage,
            cost_usd=0.0,
            latency_ms=0.0,
            cached=False,
            request_id="",
            role=ModelRole.CHEAP,
            raw_response=data,
        )

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    @asynccontextmanager
    async def lifespan(self):
        """Context manager for adapter lifecycle."""
        try:
            yield self
        finally:
            await self.close()


# Global adapter instance (initialized on first use)
_adapter: LLMAdapter | None = None


def get_adapter() -> LLMAdapter:
    """Get or create global LLM adapter instance."""
    global _adapter
    if _adapter is None:
        _adapter = LLMAdapter.from_env()
    return _adapter


async def close_adapter() -> None:
    """Close global adapter."""
    global _adapter
    if _adapter is not None:
        await _adapter.close()
        _adapter = None
