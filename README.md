# LedgerLens

**Multimodal Agentic Accounts-Payable Platform for Indian GST Invoices**

LedgerLens reads invoices (PDFs, scans, phone photos), validates them against GST rules and ERP data, matches them to purchase orders and goods receipts (3-way match), and routes them for straight-through processing, agentic investigation, or human approval. Every action is audited.

## Architecture

```
upload → API → worker (LangGraph) → extraction + 3 MCP servers → Postgres checkpoints → approvals → ERP post → audit log
```

| Component | Technology |
|-----------|------------|
| API | FastAPI (async), Pydantic v2 |
| Worker | Async + Redis queue, LangGraph |
| Extraction | OCR (Tesseract/PaddleOCR) + VLM + validators + calibration + cascade |
| ERP MCP | PostgreSQL, guarded writes with HMAC approval tokens |
| Policy MCP | Hybrid RAG (Qdrant: dense + BM25 + rerank) |
| Comms MCP | Draft vendor emails to outbox |
| Vector Store | Qdrant |
| Observability | OpenTelemetry + Arize Phoenix |
| UI | Streamlit |

## Quickstart

```bash
# Clone and setup
git clone <repo>
cd ledgerlens

# Install dependencies
uv sync --all-extras

# Copy environment template and configure
cp .env.example .env
# Edit .env with your LLM_API_KEY and other settings

# Start core services (PostgreSQL, Redis, API, Worker, 3 MCP servers)
make up

# Run checks
make check

# Generate synthetic data (deterministic with SEED=42)
make datagen SEED=42

# Run evaluations (after M1+)
make eval-oracle
make eval-extraction
make eval-matching
make eval-agent
make eval-rag
make eval-security
```

## Documentation

- [Architecture](docs/architecture.md)
- [Threat Model](docs/threat-model.md)
- [Extraction Failures](docs/extraction-failures.md)
- [Agent vs Workflow](docs/agent-vs-workflow.md)
- [Evaluation Report](docs/eval-report.md)
- [Decisions (ADRs)](docs/decisions/)
- [Demo Script](docs/demo-script.md)
- [Interview Notes](docs/interview-notes.md)
- [Resume Bullets](docs/resume-bullets.md)

## Evaluation Results

All numbers in this README and docs trace to files in `evals/results/` produced by `make` targets.

| Config | Field F1 | Line-item F1 | STP@95% | Cost/Invoice | p95 Latency |
|--------|----------|--------------|---------|--------------|-------------|
| E0 (OCR + rules) | — | — | — | — | — |
| E1 (OCR + cheap LLM) | — | — | — | — | — |
| E2 (VLM only) | — | — | — | — | — |
| E3 (Fused) | — | — | — | — | — |
| E4 (Cascade) | — | — | — | — | — |
| E5 (E4 + vendor memory) | — | — | — | — | — |

*Results will be populated after M2 evaluation.*

## Disclaimer

**Synthetic data only.** No employer code, data, or model weights used. GST rules are illustrative, not tax advice. This is a portfolio project for demonstration purposes.

## License

MIT