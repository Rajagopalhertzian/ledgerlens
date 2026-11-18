"""Pytest configuration and fixtures for LedgerLens."""

import asyncio

import pytest

# Ensure asyncio mode is auto
pytest_asyncio_mode = "auto"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return {
        "content": "test response",
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "cost_usd": 0.001,
        "latency_ms": 100.0,
    }


@pytest.fixture
def sample_invoice_data():
    """Sample invoice data for testing."""
    return {
        "invoice_number": "INV-2024-001",
        "supplier_gstin": "29ABCDE1234F1Z5",
        "invoice_date": "2024-01-15",
        "line_items": [
            {"description": "Product A", "quantity": 10, "unit_price": 100.0, "tax_rate": 18}
        ],
        "total_amount": 1180.0,
    }


# Async test support
pytest_plugins = ["pytest_asyncio"]
