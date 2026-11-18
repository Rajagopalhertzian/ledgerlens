# LedgerLens: Milestone Plan

**Generated:** 2026-11-18
**Source:** SPEC.md sections M0-M9, Section 13

Each milestone produces specific evidence files under `evals/results/` that must exist before the milestone is considered complete. All numbers in documentation must trace to these files.

---

## M0: Foundation (0.5 days)

**Goal:** Repo scaffold, CI, Docker, LLM adapter, OpenTelemetry, ADR-001

### Evidence Files (evals/results/)
- `m0-check.json` - Output of `make check` (ruff, pyright, pytest pass)
- `m0-docker-up.json` - Output of `make up` (core profile starts successfully)

### Deliverables
- [x] Repo layout per CLAUDE.md
- [x] pyproject.toml with exact pinned versions
- [x] Makefile with all commands
- [x] docker-compose.yml (core + full profiles)
- [x] .env.example with LLM_* variables
- [x] .gitignore
- [x] .pre-commit-config.yaml (ruff)
- [x] PR template with eval diff section
- [x] GitHub Actions CI (ruff, pyright, pytest)
- [x] llm/ adapter (roles, disk cache, cost tracking, retries, circuit breaker)
- [x] llm/ tests with fake provider
- [x] OpenTelemetry tracing (console exporter hello-world)
- [x] docs/decisions/ADR-001-versions.md

### Acceptance
- `make check` passes
- `make up` starts core profile (postgres, redis, api, worker, 3 MCP servers)

---

## M1: Synthetic Data & Eval Harness (3-4 days)

**Goal:** Deterministic synthetic generator, ERP seed data, eval harness, oracle baseline

### Evidence Files (evals/results/)
- `m1-datagen-manifest.json` - SHA-256 manifest from `make datagen SEED=42`
- `m1-datagen-hashes.json` - Verification that re-run produces identical hashes
- `m1-test-results.json` - Output of `make test` (all metric unit tests pass)
- `m1-oracle-results.json` - Output of `make eval-oracle` (oracle baseline metrics)
- `docs/datagen-review.md` - 20 random document paths for manual review

### Deliverables
- Synthetic generator (60 vendors, 400 POs, GRNs, 8+ invoice templates)
- Degradations: skew, perspective, blur, JPEG, shadows, stamps, handwriting
- Defect catalogue D01-D15 with 55% clean, 8+ per defect in test
- Dataset splits: dev 300, test 300 (frozen), adversarial 60, policy Q&A 60, real-capture 15-20
- Manifest with seeds, generator version, SHA-256 of every file
- Metric library: normalization, Hungarian line-item matching, bootstrap CIs, ECE, selective-prediction curves
- Results writer (JSON + Markdown), baseline comparer for `make gate`
- Oracle baseline: downstream decision logic on ground-truth fields

### Acceptance
- `make datagen SEED=42` reproducible (identical hashes)
- `make test` passes (metric functions have unit tests including edge cases)
- `make eval-oracle` writes results
- 20 random documents listed in `docs/datagen-review.md`

---

## M2: Extraction (4-5 days)

**Goal:** OCR + VLM extraction with grounding, validators, calibration, cascade

### Evidence Files (evals/results/)
- `m2-extraction-ablation.json` - E0-E4 table with bootstrap CIs, ECE, STP@precision, cost, latency
- `m2-reliability-diagram.png` - Reliability diagram (calibration)
- `m2-extraction-failures.md` - 10 real failures with images, cause, what tried

### Deliverables
- OCR backends: Tesseract (CPU), PaddleOCR (optional GPU)
- VLM backend with JSON-schema output
- Text parser (cheap LLM parse of OCR text)
- Grounding check: every value found in OCR tokens after normalization
- Deterministic validators: line totals, taxes, grand total, dates, GSTIN checksum, IRN recomputation, text-layer vs pixel
- Calibrated confidence (logistic/isotonic on dev only): ECE + reliability diagram
- Cascade router: cheap path first, escalate to strong VLM for low-confidence
- Ablation configs E0-E4 on same splits

### Metrics
- Field-level exact match & F1 by type
- Line-item F1
- Amount-field exact match
- Plausible-but-wrong number rate
- ECE
- STP at fixed precision (threshold chosen on dev, reported on test)
- Cost per document, p50/p95 latency
- Bootstrap CIs
- Real-capture slice + optional CORD check

### Acceptance
- `make eval-extraction` writes E0-E4 table with CIs, ECE, STP@precision, cost, latency
- Reliability diagram saved
- Thresholds chosen on dev, applied to test
- `docs/extraction-failures.md` with 10 real failures
- Dry-run cost estimate before runs >50 docs; everything cached

---

## M3: ERP, Validation, Matching, ERP MCP Server (3 days)

**Goal:** ERP schema, validators V1-V12, 3-way match, ERP MCP server with guarded writes

### Evidence Files (evals/results/)
- `m3-matching-oracle.json` - Per-defect precision/recall on oracle fields
- `m3-matching-extracted.json` - Per-defect precision/recall on extracted fields (with gap)
- `m3-mcp-contract-tests.json` - MCP contract test results

### Deliverables
- ERP schema (Postgres, Alembic): vendors, POs, PO lines, GRNs, GRN lines, invoices, invoice lines, approvals, posting_ledger, audit_log, outbox
- Validators V1-V12 as pure functions with property-based tests (hypothesis)
  - V1: GSTIN format & checksum
  - V2: GSTIN matches vendor master
  - V3: Tax type vs place of supply
  - V4: Tax arithmetic
  - V5: Totals & rounding
  - V6: IRN recomputation
  - V7: Invoice date plausibility
  - V8: Duplicate by identity
  - V9: Near-duplicate
  - V10: Bank details vs vendor master
  - V11: PO reference exists & belongs to vendor
  - V12: Text-layer vs pixel consistency
- Entity resolution: exact GSTIN, else fuzzy name+address (rapidfuzz)
- 3-way match: line-level invoice↔PO↔GRN, UoM normalization, tolerance YAML
- Risk scoring: rule-based (new vendor, bank change, amount near limit, duplicate likelihood, low confidence, injection flag)
- ERP MCP server (Streamable HTTP, bearer auth with scopes)
  - Read tools: find_vendor_by_gstin, get_vendor, get_po, search_pos, get_grn, get_invoice_history, check_duplicate
  - Write tools: post_invoice, place_payment_hold (require idempotency key + HMAC approval token)
- Contract tests for every tool (schema, auth failure, scope failure, idempotent replay, bad token)

### Acceptance
- Validators & matching thoroughly tested (property-based for GSTIN, tax math, IRN)
- Per-defect precision/recall table for both oracle and extracted inputs
- MCP contract tests pass; write without valid token fails and is audited

---

## M4: Agent Workflow (4-5 days) — **Resume-Ready Checkpoint**

**Goal:** LangGraph workflow with Postgres checkpointer, human approval, baselines B0-B3

### Evidence Files (evals/results/)
- `m4-crash-resume.json` - Crash/resume test: zero duplicate posts
- `m4-agent-ablation.json` - B0-B3 comparison table with all metrics
- `m4-agent-eval.json` - Full eval metrics (cause accuracy, action accuracy, evidence grounding, escalation P/R, unsafe actions=0, tool calls, cost, latency)
- `docs/agent-vs-workflow.md` - Written conclusion on when agent is/isn't worth it

### Deliverables
- LangGraph workflow: ingest → classify → extract (cascade) → validate → resolve_entities → match → risk → route
- Postgres checkpointer (thread_id = invoice_id)
- Routes: clean+confident → post (auto-approval token), exception → investigate, high-risk → approval (human)
- Investigator: produces ExceptionReport (cause, evidence items, recommended action, confidence)
- Verifier: checks every claim backed by evidence; removes unsupported or escalates
- Communicator: drafts vendor email to outbox (never sends)
- Approval: interrupt() with JSON payload, resume with Command(resume=...)
- Post: calls ERP write tool with approval token + idempotency key
- Budgets: max steps, max tokens, max spend per invoice, per-tool timeouts/retries
- Agent permissions: Investigator (read-only), Verifier (no tools), Communicator (draft only), Post (write with token)
- Baselines: B0 (rules-only), B1 (fixed workflow + LLM explanation), B2 (ReAct investigator), B3 (B2 + verifier)
- LLM-judge calibration: label 60 exception reports, measure Cohen's kappa

### Acceptance
- Crash/resume test passes with zero duplicate posts
- Baseline comparison table B0-B3 with written conclusion
- `make eval-agent` reports all metrics; unsafe actions = 0
- Audit log reconstructs any decision end-to-end
- `docs/agent-vs-workflow.md` completed

---

## M5: Policy RAG & Vendor Correction Memory (3 days)

**Goal:** Policy corpus, hybrid retrieval, policy MCP, vendor memory with poisoning guard

### Evidence Files (evals/results/)
- `m5-rag-ablation.json` - Retrieval ablation (dense, BM25, hybrid, hybrid+rerank)
- `m5-rag-failures.md` - Failure taxonomy with examples
- `m5-learning-curve.json` - Extraction accuracy vs corrections (E4 vs E5)
- `m5-poisoning-test.json` - Memory poisoning test fails to change bank detail

### Deliverables
- Policy corpus: ~12 synthetic AP policies with near-duplicates, superseded versions, 1 contradiction
- Structure-aware chunking; dense (bge-m3) + BM25 in Qdrant; RRF + cross-encoder rerank (bge-reranker-v2-m3)
- Metadata filters (status, effective date); cited answers with abstention
- Policy MCP server: search_policy, get_policy_section
- Vendor correction memory: store (vendor, layout, field, wrong, right, reviewer, timestamp), retrieve as few-shot hints
- Learning curve: extraction accuracy vs number of corrections (E4 vs E5)
- Poisoning guard: authenticated reviewer, versioned, low-trust until confirmed, bank details never updated from memory

### Acceptance
- Retrieval ablation table + failure taxonomy exist
- Exception reports cite policy passages resolving to real chunks
- Learning curve plotted from real runs
- Poisoning test fails to change bank detail

---

## M6: Security & Guardrails (3 days)

**Goal:** Threat model, controls C1-C10, 60-case adversarial suite

### Evidence Files (evals/results/)
- `m6-security-eval.json` - Attack success rate on writes (target 0/N), injection detection recall, FP rate on benign
- `docs/threat-model.md` - Threat model mapped to OWASP Top 10 for Agentic Applications

### Deliverables
- Threat model: assets, actors, trust boundaries, abuse cases, OWASP mapping (fetch official Dec 2025 doc, use exact category names)
- Controls:
  - C1: Untrusted-content boundary (delimited data blocks)
  - C2: Structured outputs only; tool args validated against schemas & ERP state
  - C3: Per-node tool allowlists (investigator/communicator no write tools)
  - C4: Write actions need server-verified approval token
  - C5: Step/token/spend caps; kill switch
  - C6: Injection scanner (heuristics + LLM classifier + canary strings)
  - C7: PII/bank-detail masking in logs/traces
  - C8: Auth, scopes, rate limits on MCP servers & API
  - C9: Vendor memory poisoning guard
  - C10: Hash-chained audit log (optional)
- Adversarial suite (60 cases): embedded instructions (visible, tiny, white-on-white, metadata, vendor-name), tool coercion, exfiltration, memory poisoning, schema-breaking, oversized/malformed files

### Acceptance
- Threat model written & mapped to OWASP categories
- `make eval-security` reports metrics; no unauthorized write succeeds
- Suite runs in CI on cached responses

---

## M7: Observability, Cost & Resilience (3 days)

**Goal:** End-to-end tracing, metrics dashboard, Pareto chart, load test, resilience tests R1-R6

### Evidence Files (evals/results/)
- `m7-trace-example.json` - One invoice end-to-end trace with costs
- `m7-pareto-chart.png` - Cost vs accuracy Pareto chart
- `m7-load-test.json` - Locust/k6 results with p95 under load
- `m7-resilience.json` - R1-R6 test results

### Deliverables
- OpenTelemetry across API → worker → graph nodes → MCP calls → LLM/VLM calls
- Span attributes: node, model, tokens, cost, cache hit, retry count, invoice_id (hashed)
- LLM observability backend (Arize Phoenix or Langfuse) in single container/free tier
- Metrics dashboard: STP rate, escalation rate, error rate, p50/p95 latency per stage, cost per invoice by config, queue depth
- Replay command: `make replay INVOICE=<id>` from cached responses
- Cost/latency optimization: cascade config, caching, bounded concurrency, batch ingestion
- Resilience tests (automated):
  - R1: Kill worker mid-run → resumes from checkpoint, no duplicate posts
  - R2: ERP MCP down → retries with backoff, then parks job
  - R3: LLM timeout/rate limit → fallback model, then escalation
  - R4: Malformed model output → one retry, then escalation
  - R5: Duplicate upload → idempotent, no second job effects
  - R6: DB connection loss → reconnect and continue

### Acceptance
- Trace shows one invoice end-to-end with costs
- Pareto chart & load-test results saved under evals/results/
- R1-R6 pass in CI or documented `make resilience` run

---

## M8: UI, Deployment, Docs, Demo (3-4 days)

**Goal:** Reviewer console, deployment with demo mode, documentation from real results

### Evidence Files (evals/results/)
- `m8-deployment-verify.json` - Clean machine `docker compose --profile full up` verification

### Deliverables
- Reviewer console (Streamlit):
  - Queue with filters (risk, status, vendor)
  - Review page: document image with OCR/VLM boxes, extracted fields with confidence & validator flags, exception report with clickable evidence, edit/approve/reject
  - Trace timeline per invoice (nodes, tool calls, latency, cost)
  - Metrics page (STP rate, eval accuracy, cost per invoice)
- Deployment: Compose on small VM/free-tier behind HTTPS (Caddy), demo mode (synthetic data, basic auth, rate limits, spend cap)
- Documentation (all from evals/results/):
  - README.md: problem, demo, architecture diagram, results table, quickstart, evals, limitations, next steps, disclaimer
  - docs/architecture.md, threat-model.md, extraction-failures.md, agent-vs-workflow.md, eval-report.md, decisions/ADR-*.md, demo-script.md
  - docs/interview-notes.md: 12 questions with answers quoting own numbers
  - docs/resume-bullets.md: bullets with placeholders from evals/results/

### Acceptance
- `docker compose --profile full up` works on clean machine per README
- Demo video recorded; live demo has spend cap
- All docs exist; every number traces to evals/results/

---

## M9: Stretch (Pick ≤2) (variable)

**Options:**
- A2A: Expose communicator/policy agent as A2A service with Agent Card
- Multi-tenant: Tenant ID on every row with Postgres RLS + isolation tests
- Small-model extractor: Fine-tune/distill small open model on dev data; compare with E4
- Indic templates: More Hindi/Kannada layouts + OCR comparison
- Tamper detector: Small CNN from scratch on synthetic tamper data
- Active learning: Uncertainty sampling for human review prioritization

### Evidence Files
- `m9-<feature>-results.json` - Feature-specific metrics
- `m9-<feature>-flag.md` - Feature flag documentation

---

## Evaluation Governance (Section 13)

- Tune only on dev; test split frozen at generation, used once per config
- Report n, counts, bootstrap CIs; treat small differences as noise (8-10 per defect type)
- Thresholds chosen on dev; report test with those thresholds
- Every LLM judge calibrated against ≥50 human labels; judge model ≠ graded model
- Cache all model calls; record cache key scheme in docs/
- CI: smoke eval on cached responses; `make gate` compares with evals/baseline.json; full evals manual (workflow_dispatch) with spend cap
- Changelog of every metric that moved and why

---

## Definition of Done (Section 14)

- [ ] M1-M8 acceptance criteria met; M9 optional
- [ ] README results table, demo video, quickstart verified on clean machine
- [ ] `make check`, `make gate`, resilience run are green
- [ ] Every number in docs traces to evals/results/
- [ ] Threat model, ADRs, failure analyses, interview notes written
- [ ] Can explain every module, threshold, trade-off without opening code