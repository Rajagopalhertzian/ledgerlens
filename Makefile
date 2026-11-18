# LedgerLens Makefile
# All commands from CLAUDE.md

.PHONY: help up down check test datagen eval-oracle eval-extraction eval-matching eval-agent eval-rag eval-security eval-gate replay lint typecheck format clean

# Default target
help:
	@echo "LedgerLens - Multimodal Agentic AP Platform for Indian GST Invoices"
	@echo ""
	@echo "Core commands:"
	@echo "  make up           - Start docker compose (core profile)"
	@echo "  make up-full      - Start docker compose (full profile)"
	@echo "  make down         - Stop docker compose"
	@echo "  make check        - Run ruff + pyright + pytest (must pass before done)"
	@echo ""
	@echo "Data & Evaluation:"
	@echo "  make datagen SEED=42    - Generate synthetic documents + ground truth + manifest"
	@echo "  make eval-oracle        - Run oracle baseline evaluation"
	@echo "  make eval-extraction    - Run extraction ablation (E0-E4)"
	@echo "  make eval-matching      - Run matching evaluation (oracle + extracted)"
	@echo "  make eval-agent         - Run agent workflow evaluation (B0-B3)"
	@echo "  make eval-rag           - Run RAG evaluation"
	@echo "  make eval-security      - Run security evaluation"
	@echo "  make gate               - Compare latest results with evals/baseline.json"
	@echo "  make replay INVOICE=<id> - Re-run invoice from cached responses"
	@echo ""
	@echo "Development:"
	@echo "  make lint         - Run ruff check"
	@echo "  make format       - Run ruff format"
	@echo "  make typecheck    - Run pyright"
	@echo "  make test         - Run pytest"
	@echo "  make clean        - Clean build artifacts"

# Docker compose
up:
	docker compose --profile core up -d

up-full:
	docker compose --profile full up -d

down:
	docker compose down -v

# Core quality checks
check: lint typecheck test

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

typecheck:
	uv run pyright src/ tests/

test:
	uv run pytest -v --tb=short

# Data generation (M1)
datagen:
	@echo "Generating synthetic data with SEED=$(SEED)..."
	uv run python -m datagen.generate --seed $(SEED)

# Evaluation targets (stubs for M0, implemented in later milestones)
eval-oracle:
	@echo "Running oracle baseline evaluation..."
	uv run python -m evals.run_oracle

eval-extraction:
	@echo "Running extraction evaluation (E0-E4)..."
	uv run python -m evals.run_extraction

eval-matching:
	@echo "Running matching evaluation..."
	uv run python -m evals.run_matching

eval-agent:
	@echo "Running agent evaluation (B0-B3)..."
	uv run python -m evals.run_agent

eval-rag:
	@echo "Running RAG evaluation..."
	uv run python -m evals.run_rag

eval-security:
	@echo "Running security evaluation..."
	uv run python -m evals.run_security

gate:
	@echo "Comparing with baseline..."
	uv run python -m evals.gate

replay:
	@echo "Replaying invoice $(INVOICE)..."
	uv run python -m evals.replay --invoice $(INVOICE)

# Resilience tests (M7)
resilience:
	@echo "Running resilience tests R1-R6..."
	uv run python -m evals.run_resilience

# Development utilities
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

install:
	uv sync --all-extras

install-dev:
	uv sync --extra dev

install-full:
	uv sync --extra full

# Pre-commit
pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files