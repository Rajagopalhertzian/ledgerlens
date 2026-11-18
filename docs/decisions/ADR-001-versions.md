# ADR-001: Library Versions and Documentation References

**Date:** 2026-11-18
**Status:** Accepted

## Context

LedgerLens depends on several rapidly-evolving libraries (LangGraph, LangChain, MCP SDK, Qdrant, OCR/VLM libraries). The spec requires documenting exact versions and the documentation pages they were verified against to ensure reproducibility and ease future upgrades.

## Decision

Pin exact versions in `pyproject.toml` and record the documentation URLs checked for each library.

## Library Versions (as of 2026-11-18)

### Core Dependencies

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| Python | 3.12 | https://docs.python.org/3.12/ | Required by spec |
| uv | latest | https://docs.astral.sh/uv/ | Package manager |
| pydantic | 2.9.2 | https://docs.pydantic.dev/latest/ | V2 required |
| pydantic-settings | 2.5.2 | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ | Settings management |
| httpx | 0.27.2 | https://www.python-httpx.org/ | Async HTTP client |
| structlog | 24.1.0 | https://www.structlog.org/ | Structured logging |
| python-json-logger | 2.0.7 | https://github.com/nhairs/python-json-logger | JSON logging |
| anyio | 4.5.0 | https://anyio.readthedocs.io/ | Async primitives |
| tenacity | 8.3.0 | https://www.jdawson.com/tenacity/ | Retry logic |
| pyyaml | 6.0.1 | https://pyyaml.org/ | YAML config |
| orjson | 3.10.0 | https://github.com/ijl/orjson | Fast JSON |
| xxhash | 3.5.0 | https://github.com/ifduyue/xxhash | Fast hashing |
| tqdm | 4.66.5 | https://github.com/tqdm/tqdm | Progress bars |
| filelock | 3.15.0 | https://github.com/tox-dev/filelock | File locking |

### Database & Cache

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| sqlalchemy | 2.0.32 | https://docs.sqlalchemy.org/en/20/ | 2.0 required |
| alembic | 1.13.1 | https://alembic.sqlalchemy.org/ | Migrations |
| asyncpg | 0.29.0 | https://magicstack.github.io/asyncpg/ | Async Postgres |
| redis | 5.0.8 | https://redis-py.readthedocs.io/ | Redis client |

### FastAPI & Web

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| fastapi | 0.112.0 | https://fastapi.tiangolo.com/ | API framework |
| uvicorn | 0.30.6 | https://www.uvicorn.org/ | ASGI server |
| email-validator | 2.2.0 | https://github.com/JoshData/python-email-validator | Email validation |

### LangGraph & LangChain

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| langgraph | 0.2.34 | https://langchain-ai.github.io/langgraph/ | Workflow orchestration |
| langchain-core | 0.3.25 | https://python.langchain.com/docs/core/ | Core abstractions |
| langchain-openai | 0.2.1 | https://python.langchain.com/docs/integrations/chat/openai/ | OpenAI integration |
| **MCP Integration** | **LangChain 1.4+** | https://python.langchain.com/docs/integrations/mcp/ | Now in `langchain.mcp` beta module, replaces `langchain-mcp-adapters` |

### MCP SDK

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| mcp | 1.0.0 | https://modelcontextprotocol.io/specification/2025-06-18/ | Streamable HTTP, OAuth 2.1 auth |

### Vector Store

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| qdrant-client | 1.11.0 | https://qdrant.tech/documentation/ | Hybrid search (dense + BM25) |

### OCR / Document Processing

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| pytesseract | 0.3.10 | https://github.com/madmaze/pytesseract | Tesseract wrapper |
| pdf2image | 1.17.0 | https://github.com/Belval/pdf2image | PDF to images |
| pillow | 10.4.0 | https://pillow.readthedocs.io/ | Image processing |
| weasyprint | 62.0 | https://weasyprint.org/ | HTML to PDF rendering |
| paddleocr | 2.8.1 (optional) | https://github.com/PaddlePaddle/PaddleOCR | Optional GPU OCR |

### Evaluation & Testing

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| pytest | 8.3.0 | https://docs.pytest.org/ | Testing |
| pytest-asyncio | 0.23.7 | https://github.com/pytest-dev/pytest-asyncio | Async tests |
| pytest-cov | 5.0.0 | https://pytest-cov.readthedocs.io/ | Coverage |
| hypothesis | 6.100.0 | https://hypothesis.readthedocs.io/ | Property-based testing |
| rapidfuzz | 3.9.0 | https://github.com/maxbachmann/rapidfuzz | Fuzzy matching |

### Observability

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| opentelemetry-api | 1.25.0 | https://opentelemetry.io/docs/specs/otel/ | API |
| opentelemetry-sdk | 1.25.0 | https://opentelemetry.io/docs/specs/otel/ | SDK |
| opentelemetry-exporter-otlp | 1.25.0 | https://opentelemetry.io/docs/specs/otel/ | OTLP exporter |
| opentelemetry-instrumentation-fastapi | 0.46b0 | https://github.com/open-telemetry/opentelemetry-python-contrib | FastAPI instrumentation |
| opentelemetry-instrumentation-httpx | 0.46b0 | https://github.com/open-telemetry/opentelemetry-python-contrib | HTTPX instrumentation |
| opentelemetry-instrumentation-redis | 0.46b0 | https://github.com/open-telemetry/opentelemetry-python-contrib | Redis instrumentation |
| opentelemetry-instrumentation-sqlalchemy | 0.46b0 | https://github.com/open-telemetry/opentelemetry-python-contrib | SQLAlchemy instrumentation |

### Development Tools

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| ruff | 0.5.0 | https://docs.astral.sh/ruff/ | Linting & formatting |
| pyright | 1.1.384 | https://github.com/microsoft/pyright | Type checking |
| pre-commit | 3.8.0 | https://pre-commit.com/ | Git hooks |
| mypy | 1.11.0 | https://mypy.readthedocs.io/ | Static typing |

### UI & Load Testing (Optional)

| Library | Version | Docs URL | Notes |
|---------|---------|----------|-------|
| streamlit | 1.38.0 | https://streamlit.io/ | Reviewer console |
| plotly | 5.23.0 | https://plotly.com/python/ | Visualization |
| kaleido | 0.2.1 | https://github.com/plotly/kaleido | Static export |
| locust | 2.32.0 | https://locust.io/ | Load testing |

## Verification Process

Before upgrading any library:
1. Check the documentation URL for breaking changes
2. Run `make check` to ensure tests pass
3. Update this ADR with new version and date
4. Create a new ADR if the upgrade requires architectural changes

## Next Review

Review and update versions at the start of each milestone (M1-M9).