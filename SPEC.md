# LedgerLens: SPEC

## 0. How to use this spec

This is the source of truth for scope, architecture and acceptance criteria. Read sections 1-3 once per session, then only the milestone you are working on (sections 4-12) and section 13.
When reality disagrees with the spec, change the spec and add an ADR in docs/decisions/. Do not drift silently.
Every number in the README or docs must come from a file in evals/results/ produced by a make target.
Milestones are ordered so the project is resume-ready after M4. If time runs out, cut in this order: M9, UI polish in M8, load tests in M7. Never cut M1-M4.
Effort estimates in focused working days with Claude Code: M0 0.5, M1 3-4, M2 4-5, M3 3, M4 4-5, M5 3, M6 3, M7 3, M8 3-4 (about 15-18 days to M4, 27-32 in total). These are guesses; adjust after M1. Alongside a full-time job, expect roughly double the calendar time.

## 1. Product and scope

**Problem.** Accounts-payable (AP) teams receive invoices as PDFs, scans and phone photos. Matching them to purchase orders (PO) and goods receipts (GRN), chasing exceptions and catching fraud (duplicates, changed bank details, edited amounts) is slow and error-prone.

**System.** LedgerLens reads each invoice with per-field confidence, validates it (arithmetic and India GST checks), matches it to PO and GRN (3-way match), and routes it: auto-post (straight-through), investigate (agent), or escalate to a human with evidence. Every action is audited.

**Personas.** AP clerk (works the review queue), AP manager (approves high-risk items, watches metrics), auditor (reads the audit trail).

**Goals**

G1 Accurate, calibrated, cost-aware extraction.
G2 A deterministic, well-tested validation and matching core.
G3 Agentic exception investigation with evidence, human-in-the-loop and least privilege.
G4 Policy-grounded answers with citations, plus per-vendor correction memory.
G5 Resistance to prompt injection and tool misuse, with provable "no unauthorised writes".
G6 Production engineering: observability, resilience, CI evals, reproducibility, deployment, demo.

**Non-goals.** Real payments, real ERP integration, real personal or financial data, legal or tax advice, any employer code, data or model weights. GST rules here are illustrative; put that disclaimer in the README.

## 2. Architecture

**Flow:** upload -> API stores the document and creates a job -> worker runs the LangGraph workflow -> nodes call the extraction library and three MCP servers (ERP, policy, comms) over Streamable HTTP with bearer auth -> state is checkpointed in Postgres -> approvals arrive through the API/UI and resume the graph -> the ERP write goes through the ERP MCP server with a server-verified approval token -> audit log.

| Component | Purpose | Tech |
|-----------|---------|------|
| api | upload, job status, approvals, metrics | FastAPI (async), Pydantic v2 |
| worker | runs one workflow per invoice | async worker + Redis-backed queue, LangGraph |
| extraction | OCR + VLM + fusion + validators + calibration + cascade | library with OCR/VLM backend adapters |
| erp MCP | vendor/PO/GRN/invoice queries; guarded writes | Python MCP server over Postgres |
| policy MCP | policy RAG with citations | hybrid retrieval over Qdrant |
| comms MCP | drafts vendor emails and tickets into an outbox (never sends) | Python MCP server |
| db | ERP schema, jobs, approvals, audit log, checkpoints | PostgreSQL, SQLAlchemy 2, Alembic |
| vector store | policy chunks, vendor correction memory | Qdrant |
| observability | traces, cost, latency | OpenTelemetry + one LLM-observability backend |
| ui | reviewer console | Streamlit (or equivalent) |
| datagen, evals | synthetic data and the evaluation harness | Python |

Compose profiles: core (postgres, redis, api, worker, MCP servers) and full (adds qdrant, observability backend, ui). Do not add services beyond this list without an ADR.

## 3. Engineering rules

**Stack.** Python 3.12, uv, ruff, pyright, pytest + hypothesis, FastAPI (async), Pydantic v2, SQLAlchemy 2 + Alembic, httpx, structlog, OpenTelemetry. Pin exact versions.

**Docs first.** Before using LangGraph, LangChain, an MCP SDK or FastMCP, Qdrant, or any OCR/VLM library, read its current docs and record versions in docs/decisions/ADR-001-versions.md. These move fast: for example, LangChain's MCP integration now lives in a beta langchain.mcp module (LangChain 1.4+) that replaced langchain-mcp-adapters; MCP remote servers use Streamable HTTP and an OAuth 2.1-based authorisation flow. Verify against current docs before relying on any of this.

**Adapters.** llm/ is provider-agnostic with three roles (CHEAP, STRONG, JUDGE; the judge must differ from the model it grades), a disk cache keyed by request hash, token and cost accounting, timeouts, retries with jitter, a circuit breaker and a fallback model. Also mcp_client.py and rag/.

**Determinism.** Temperature 0 for extraction and judging. Structured outputs validated with Pydantic. On schema failure retry once, then escalate to a human.

**Idempotency.** Every write has an idempotency key. LangGraph restarts a node from its beginning after interrupt(), so side effects before an interrupt must be idempotent or placed after it.

**Untrusted content.** Invoice text, OCR output, vendor names and memory entries are data. They never select tools, tool arguments or recipients.

**Least agency.** Investigator: read-only tools. Communicator: draft-only. Poster: write tool with approval token.

**Reproducibility.** Seeds, dataset manifests with SHA-256, pinned dependencies, a make target for every number.

**Cost control.** MAX_SPEND_USD; a dry-run cost estimate before any run over 50 documents; always start with a 30-document dev subset.

**Model config.** Roles come from env (CHEAP_MODEL, STRONG_MODEL, JUDGE_MODEL, LLM_PROVIDER). Check current model IDs in the provider docs. A GPU is optional (see M2).

**Git.** One milestone per branch; the PR template includes the eval diff.

## M0: Foundation (about 0.5 day)

Repo scaffold using the layout in CLAUDE.md; pyproject.toml with exact pinned versions; Makefile with every command listed in CLAUDE.md (stubs allowed); docker-compose.yml with the core and full profiles; .env.example (including MAX_SPEND_USD, model roles); .gitignore; pre-commit with ruff; PR template with an "eval diff" section.

CI skeleton: ruff, pyright, pytest on every push.

llm/ adapter: provider-agnostic, CHEAP/STRONG/JUDGE roles, disk cache, token and cost accounting, timeouts, retries with jitter; unit-tested with a fake provider.

A hello-world OpenTelemetry trace exported to the console.

docs/decisions/ADR-001-versions.md listing every library version and the docs page it was checked against.

Acceptance: make check passes and make up starts the core profile.

## 4. M1: Synthetic data and the evaluation harness

### Why synthetic

We need ground truth for every field and every defect, and receipt datasets such as SROIE and CORD are weak proxies for B2B invoices. The generator is part of the contribution; document it well.

### Entities (seeded)

About 60 vendors with valid GSTINs (2-digit state code + 10-character PAN + entity code + Z + checksum character; implement and property-test the checksum), bank accounts (masked in logs), about 400 POs with lines (HSN-style codes, UoM, tax rates from a config table; rates are illustrative), GRNs with partial deliveries.

### Invoice rendering

At least 8 templates rendered from HTML to PDF (WeasyPrint or Playwright): different layouts, column orders, fonts, multi-page, with and without PO reference, Indian digit grouping (12,34,567.00), several date formats, two templates with bilingual headers (English plus Hindi or Kannada). Then degrade: skew, perspective "phone photo", blur, JPEG artefacts, shadows, stamps, handwriting-like annotations. Keep the PDF text layer in about half the PDFs and rasterise the rest.

### Ground truth per document (JSON)

Header fields, line items, taxes, totals, expected_decision (post | investigate | escalate | reject), defects[] (type, evidence), expected_actions[].

### Defect catalogue

About 55% clean; the rest spread across D02-D15 with at least 8 per defect type in the test split.

| ID | Defect | How it shows up | Expected handling |
|----|--------|-----------------|-------------------|
| D01 | Clean | everything consistent | auto-post |
| D02 | Price variance | unit price beyond tolerance vs PO | investigate; hold |
| D03 | Over-billing | quantity above goods received | investigate; partial approve or reject |
| D04 | No GRN | goods not yet received | hold until GRN |
| D05 | Exact duplicate | same supplier GSTIN + financial year + doc type + number | reject as duplicate |
| D06 | Near duplicate | same vendor and amount, number or date altered | escalate |
| D07 | Wrong tax type | IGST vs CGST+SGST inconsistent with places of supply | investigate; request corrected invoice |
| D08 | Tax arithmetic error | taxes or totals do not add up | investigate |
| D09 | Invalid or mismatched GSTIN | checksum fails or differs from vendor master | escalate |
| D10 | Bank-detail change | bank account differs from vendor master | escalate (fraud risk); never auto-update |
| D11 | Missing or wrong PO reference | PO absent or points to the wrong PO | fuzzy-resolve or escalate |
| D12 | Edited amount | post-render edit; text layer and pixels disagree, or totals inconsistent | escalate |
| D13 | Embedded instruction | text trying to steer the agent (visible, tiny, white-on-white, metadata) | ignore it, flag it, continue normal processing |
| D14 | Illegible or not an invoice | unreadable or wrong document type | reject; request resubmission |
| D15 | Policy violation | above approval limit, blocked vendor, missing second approver | escalate per policy |

### Splits

dev 300, test 300 (frozen, never used for tuning), adversarial 60 (M6), policy Q&A 60 (M5), real-capture 15-20 (print generated invoices and photograph them under varied light; labels come from the generator), optional out-of-distribution check on CORD (CC BY 4.0, receipts only, say clearly that receipts are not invoices).

### Manifest

Seeds, generator version and SHA-256 of every file. make datagen SEED=42 is deterministic.

### Eval harness skeleton (all unit-tested)

Field normalisation (numbers, dates, currency), line-item matching (Hungarian assignment), bootstrap confidence intervals, expected calibration error (ECE), selective-prediction (coverage vs precision) curves, a results writer (JSON + Markdown) and a baseline comparer for make gate.

### Oracle baseline

Run the downstream decision logic on ground-truth fields to get an upper bound; later stages report the gap to oracle so extraction errors are separated from logic errors.

### Acceptance M1

make datagen SEED=42 creates dev/test and the manifest; re-running gives identical hashes.
You have eyeballed 20 random documents (paths listed in docs/datagen-review.md).
make test passes; metric functions have unit tests including edge cases.
make eval-oracle writes results.

## 5. M2: Extraction

### Interface

Extractor.extract(document) -> ExtractionResult with fields (value, calibrated confidence, evidence boxes or text spans, source), line items, warnings.

### Backends (behind adapters)

**OCR:** Tesseract (CPU baseline), PaddleOCR or similar. Optional GPU path: a document-specialised OCR-VLM served behind an OpenAI-compatible endpoint. Candidates in 2026 include PaddleOCR-VL, GLM-OCR, olmOCR, DeepSeek-OCR and granite-docling; check current versions and licences before choosing.

**VLM:** a strong hosted vision model with JSON-schema output; optionally an open VLM (for example Qwen3-VL) behind the same interface.

**Text parser:** LLM parse of OCR text into the schema (cheap path).

### Key design: "plausible is not read"

General VLMs can return plausible values they never read, and OCR-specialised VLMs can omit or add passages. So:

Run OCR (tokens, boxes, confidences) and the VLM/LLM extraction.
Grounding check: every extracted value must be found in the OCR tokens after normalisation (numbers, dates, IDs, fuzzy for names). Ungrounded values get an ungrounded flag and lower confidence.
Deterministic validators: line totals sum to subtotal; taxes equal rate times taxable value; grand total consistent; date plausibility; GSTIN format and checksum; IRN recomputation when an IRN is printed (SHA-256 over supplier GSTIN, document type, document number and financial year in YYYY-YY form; read the official e-invoice spec for the exact input format and cite it in a code comment); for PDFs with a text layer, compare the text layer with OCR of the rendered pixels (edit detection).
Calibrated confidence: combine OCR confidence, OCR/VLM agreement, grounded flag and validator results in a small calibrated model (logistic regression or isotonic) fitted on dev only. Report ECE and a reliability diagram.
Cascade: cheap path first (OCR + cheap model); escalate to the strong VLM only for low-confidence fields or documents. Report the cost vs accuracy Pareto.
Vendor correction memory (wired up in M5): retrieved few-shot hints from past human corrections for the same vendor or layout.

### Ablation configs (all on the same splits)

| Config | Description |
|--------|-------------|
| E0 | OCR + rule/regex parsing (floor) |
| E1 | OCR + cheap LLM text parse |
| E2 | strong VLM only |
| E3 | fused: E1 + E2 with grounding, validators, calibrated confidence |
| E4 | E3 + cascade routing |
| E5 | E4 + vendor correction memory (after M5) |

### Metrics

Field-level exact match and F1 by field type; line-item F1; amount-field exact match; plausible-but-wrong number rate (a wrong numeric field that is not present in the OCR tokens); ECE; straight-through rate (STP) at a fixed precision (choose the threshold on dev, report on test); cost per document; p50 and p95 latency; bootstrap CIs. Also report on the real-capture slice and optional CORD check.

### Acceptance M2

make eval-extraction writes the E0-E4 table with CIs, ECE, STP at fixed precision, cost and latency.
A reliability diagram is saved. Thresholds are chosen on dev and applied to test.
docs/extraction-failures.md holds 10 real failures with images, cause and what you tried.
Dry-run cost estimate shown before any run over 50 documents; everything cached.

## 6. M3: ERP, validation, matching, risk, ERP MCP server

### ERP schema (Postgres, Alembic migrations)

vendors, purchase_orders, po_lines, goods_receipts, grn_lines, invoices, invoice_lines, approvals, posting_ledger (idempotency keys), audit_log (append-only; consider a hash chain), outbox (drafted emails and tickets).

### Validators (pure functions, property-tested with hypothesis)

V1 GSTIN format and checksum. V2 GSTIN matches vendor master. V3 tax type vs places of supply (intra-state CGST+SGST, inter-state IGST). V4 tax arithmetic. V5 totals and rounding. V6 IRN recomputation when printed. V7 invoice date within plausible range and not before PO date. V8 duplicate by identity (supplier GSTIN + financial year + doc type + number). V9 near-duplicate (vendor + amount + date proximity, fuzzy number). V10 bank details vs vendor master. V11 PO reference exists and belongs to the vendor. V12 text-layer vs pixel consistency (when a text layer exists). Document the source of each rule in a code comment; rules are illustrative.

### Entity resolution

Vendor: exact GSTIN, else fuzzy name + address (rapidfuzz) with thresholds. PO: explicit reference, else ranked candidates from vendor + amount + date + item similarity, with scores.

### 3-way match

Line-level matching invoice <-> PO <-> GRN with unit-of-measure normalisation and tolerance config in a versioned YAML (price percentage, quantity absolute). Output MatchResult with status and itemised discrepancies.

### Risk score

Rule-based first (new vendor, bank change, amount near approval limit, duplicate likelihood, low extraction confidence, injection flag). Output low / medium / high plus the reasons. Keep it explainable.

### ERP MCP server (Python, Streamable HTTP, bearer auth with scopes)

Read tools (erp.read): find_vendor_by_gstin, get_vendor, get_po, search_pos, get_grn, get_invoice_history, check_duplicate.
Write tools (erp.write): post_invoice, place_payment_hold. Each requires an idempotency key and an HMAC-signed approval token bound to invoice id, action and amount with a short TTL, verified server-side. A hijacked LLM must not be able to write.
Contract tests for every tool (schema, auth failure, scope failure, idempotent replay, bad token).

### Evaluation (make eval-matching)

Defect-detection precision and recall per defect type (D02-D15), run twice: on oracle fields and on extracted fields from the best M2 config. Report the gap.

### Acceptance M3

Validators and matching have thorough tests, including property-based tests for GSTIN checksum, tax maths and IRN.
The per-defect precision/recall table exists for both input modes.
MCP contract tests pass; a write without a valid token fails and the failure is audited.

## 7. M4: Agent workflow (resume-ready checkpoint)

### Graph (LangGraph, Postgres checkpointer, thread_id = invoice id)

ingest -> classify -> extract (cascade) -> validate -> resolve_entities -> match -> risk -> route

Route "clean and confident" to post (straight-through, still needs a system-issued approval token with auto-approval policy recorded in the audit log).
Route "exception" to investigate.
Route "high risk or low confidence or high value" to approval (human).
investigate produces a structured ExceptionReport: cause category, evidence items (each pointing to a document span, a validator result or an MCP tool result id), recommended action, confidence.
verify checks that every claim in the report is backed by evidence in the tool results; unsupported claims are removed or the report is escalated.
communicate drafts a vendor email into the outbox (never sends); templates plus constrained generation; no bank details or other vendors' data.
approval uses interrupt() with a JSON-serialisable payload. Resume with Command(resume=...). The node restarts from its beginning on resume, so keep everything before the interrupt idempotent.
post calls the ERP write tool with approval token and idempotency key, then finalize writes the audit entry.

### Budgets and caps

Max steps per run, max tokens and max spend per invoice, per-tool timeouts and retries with backoff. On breach, park the job in the human queue with a reason.

### Agents and permissions

Investigator (read-only tools), verifier (no tools, reads evidence), communicator (comms draft tool only). No agent holds write tools; only the post node does, and only with a valid token.

### Baselines (same test set)

B0 rules-only (no LLM in exception handling).
B1 fixed workflow with deterministic investigation steps and an LLM only to write the explanation.
B2 ReAct-style investigator with tool choice.
B3 B2 plus verifier.

### Metrics (make eval-agent)

Exception cause accuracy (multi-label F1), recommended-action accuracy, evidence-grounding rate (automatic via evidence ids, plus a calibrated LLM judge on a sample), escalation precision and recall, unsafe-action rate (any write without a valid token; must be 0), average tool calls, tokens, cost, latency. Bootstrap CIs.

### LLM-judge calibration

Label 60 exception reports yourself against a short rubric, then measure judge agreement (Cohen's kappa). Pick the judge prompt and model by agreement; test position and verbosity bias.

### Acceptance M4

Crash/resume test: kill the worker mid-run, restart, the run completes with zero duplicate posts.
Baseline comparison table B0-B3 with a written conclusion on when the agent is worth it and when it is not (docs/agent-vs-workflow.md).
make eval-agent reports every metric above; unsafe actions = 0.
Audit log reconstructs any decision end to end.

## 8. M5: Policy RAG and vendor correction memory

### Policy corpus

About 12 synthetic AP policy documents (approval matrix, tolerances, duplicate handling, vendor onboarding, payment terms, exception playbooks), clearly labelled synthetic, with deliberate near-duplicates, superseded versions and one contradiction to create real retrieval failures. Optionally add public GST or e-invoicing reference material (check each site's terms; keep it out of git; commit only a fetch script and manifest).

### Retrieval

Structure-aware chunking; dense (BAAI/bge-m3 is a reasonable default) plus BM25 sparse in Qdrant; reciprocal rank fusion; cross-encoder rerank (bge-reranker-v2-m3 is a reasonable default); metadata filters (status, effective date). Cited answers with abstention when evidence is missing. Verify current Qdrant hybrid-query syntax in its docs.

### Policy MCP server

search_policy(query, k, filters) returning passages with ids, source and heading path; get_policy_section(id).

### Evaluation (make eval-rag)

60 questions derived from the exception scenarios, including about 12 unanswerable ones. Recall@5/10, MRR, nDCG; ablation of dense vs BM25 vs hybrid vs hybrid + rerank; faithfulness and abstention accuracy for generated answers (judge differs from generator); failure taxonomy with examples. Labels are verified by you, not invented by the model.

### Vendor correction memory

Store human corrections (vendor, layout fingerprint, field, wrong value, right value, reviewer, timestamp) and retrieve them as few-shot hints at extraction time.
Learning-curve experiment: extraction accuracy as a function of the number of stored corrections (E4 vs E5).
Poisoning guard: corrections need an authenticated reviewer; they are versioned and low-trust until confirmed by a second reviewer or an approver; bank details are never updated from memory.

### Acceptance M5

Retrieval ablation table and failure taxonomy exist.
Exception reports cite policy passages; citations resolve to real chunks.
The learning curve is plotted from real runs.
A memory-poisoning test case fails to change a bank detail.

## 9. M6: Security and guardrails

### Threat model (docs/threat-model.md)

Assets (ERP writes, bank details, vendor data), actors (malicious vendor, careless reviewer, compromised document), trust boundaries (document -> extractor -> agent -> tools -> ERP), abuse cases, and a mapping to the OWASP Top 10 for Agentic Applications (published December 2025). Fetch the official document and use its exact category names; do not invent identifiers.

### Controls

C1 Untrusted-content boundary: documents and OCR text appear only inside clearly delimited data blocks; prompts say they are data.
C2 Structured outputs only; tool arguments are validated against schemas and against ERP state, never copied from document text.
C3 Per-node tool allowlists; investigator and communicator hold no write tools.
C4 Write actions need a server-verified approval token (see M3).
C5 Step, token and spend caps; kill switch.
C6 Injection scanner (heuristics plus an LLM classifier, canary strings) that flags and logs but never silently drops.
C7 PII and bank-detail masking in logs and traces.
C8 Authentication, scopes and rate limits on MCP servers and API.
C9 Vendor memory poisoning guard (see M5).
C10 Optional: hash-chained audit log.

### Adversarial suite (60 cases, make eval-security)

Embedded instructions (visible, tiny, white-on-white, in metadata, in the vendor-name field); tool coercion (try to make the agent call a write tool or email a different address); exfiltration (reveal other vendors' bank details); memory poisoning; schema-breaking outputs; oversized or malformed files. An open-source red-team tool can help generate attacks, but write the final cases yourself.

### Metrics

Attack success rate on write actions (target 0 of N), detection recall for injections, false-positive rate on benign documents, and any behaviour change caused by an embedded instruction.

### Acceptance M6

Threat model written and mapped to the OWASP categories.
make eval-security reports the metrics above; no unauthorised write succeeds.
The suite runs in CI on cached responses.

## 10. M7: Observability, cost and resilience

### Tracing

OpenTelemetry across API -> worker -> graph nodes -> MCP calls -> LLM/VLM calls. Span attributes: node, model, tokens, cost, cache hit, retry count, invoice id (hashed). Use one LLM-observability backend that runs in a single container or a free cloud tier (for example Arize Phoenix or Langfuse); OpenTelemetry stays the instrumentation layer so the backend is swappable. Record the choice in an ADR.

### Metrics and dashboard

STP rate, escalation rate, error rate, p50/p95 latency per stage, cost per invoice by config, queue depth. A replay command (make replay INVOICE=<id>) re-runs a recorded invoice from cached model responses for debugging.

### Cost and latency

Cascade routing config, caching of OCR and model calls, bounded concurrency, batch ingestion. Produce a cost vs accuracy Pareto chart and a throughput test (Locust or k6) with p95 under load, on the machine you actually have.

### Resilience tests (automated)

R1 Kill the worker mid-run: the job resumes from its checkpoint with no duplicate posts.
R2 ERP MCP server down: retries with backoff, then the job is parked with a reason.
R3 LLM timeout or rate limit: fallback model, then escalation.
R4 Malformed model output: one retry, then escalation.
R5 Duplicate upload: idempotent, no second job side effects.
R6 Database connection loss: reconnect and continue.

### Acceptance M7

A trace shows one invoice end to end with costs; the dashboard screenshot is in docs/.
Pareto chart and load-test results are saved under evals/results/.
R1-R6 pass in CI or in a documented make resilience run.

## 11. M8: UI, deployment, documentation, demo

### Reviewer console (Streamlit or equivalent)

Queue with filters (risk, status, vendor).
Review page: document image with OCR/VLM boxes, extracted fields with calibrated confidence and validator flags, the agent's exception report with clickable evidence (document span, validator result, ERP row, policy passage), edit, approve and reject controls.
Trace timeline per invoice (nodes, tool calls, latency, cost).
Metrics page (STP rate, accuracy on the eval sets, cost per invoice).

### Deployment

Compose on a small VM (or a free-tier cloud) behind HTTPS (for example Caddy). Demo mode: synthetic data only, basic auth, rate limits, a hard spend cap. A recorded 3-4 minute demo is mandatory in case the live link is down.

### Documentation (all generated from real results)

README.md order: one-paragraph problem, demo video/GIF, architecture diagram (Mermaid), results table (E0-E5, B0-B3, retrieval ablation, security), quickstart (one command), how to run evals, honest limitations, what you would do next, disclaimer (synthetic data, illustrative GST rules, not tax advice).
docs/architecture.md, docs/threat-model.md, docs/extraction-failures.md, docs/agent-vs-workflow.md, docs/eval-report.md, docs/decisions/ADR-*.md, docs/demo-script.md.
docs/interview-notes.md: 12 questions with answers that quote your own numbers. Include at least: why LangGraph rather than plain code and where plain code was better; how you stop hallucinated numbers; how confidence thresholds were chosen without touching test; what happens if the worker dies after an interrupt; how injected instructions in invoices are contained; how you evaluated the agent and the judge; what the cascade saved and what it cost in accuracy; why MCP servers rather than direct database tools; what failed and what you changed; how you would scale to 100k invoices per day; what you would not trust this system to do; what you would do with real data.
docs/resume-bullets.md: bullets with placeholders filled only from evals/results/.

### Acceptance M8

docker compose --profile full up works on a clean machine following the README.
Demo video recorded; live demo (if hosted) has a spend cap.
All docs above exist and every number in them traces to evals/results/.

## 12. M9: Stretch (pick at most two)

A2A: expose the communicator (or a policy agent) as a separate A2A service with an Agent Card and call it from the orchestrator. Read the current A2A spec and SDK docs first.
Multi-tenant: tenant id on every row with Postgres row-level security and tests that prove isolation.
Small-model extractor: fine-tune or distil a small open model on dev data; compare accuracy, cost and latency with E4; serve behind the same interface.
Indic templates: more Hindi and Kannada invoice layouts and an OCR comparison.
Tamper and recapture detector: a small CNN trained from scratch on your own synthetic tamper data as an extra risk signal. Do not reuse any employer code, data or weights.
Active learning: uncertainty sampling to choose which invoices humans review first; measure accuracy gained per review.

## 13. Evaluation governance

Tune only on dev. The test split is frozen at generation time and used once per reported configuration.
Report n, counts and bootstrap confidence intervals. With roughly 8-10 examples per defect type, treat small differences as noise.
Choose thresholds on dev; report test results with those thresholds.
Every LLM judge is calibrated against at least 50 human labels, and the judge model differs from the model being graded.
Cache all model calls so evals are repeatable; record the cache key scheme in docs/.
CI runs a small smoke eval on cached responses and make gate compares with evals/baseline.json; full evals run manually (workflow_dispatch) with a spend cap.
Keep a changelog of every metric that moved and why.

## 14. Definition of done (project)

[ ] M1-M8 acceptance criteria met; M9 optional.
[ ] README results table, demo video and quickstart verified on a clean machine.
[ ] make check, make gate and the resilience run are green.
[ ] Every number in docs traces to evals/results/.
[ ] Threat model, ADRs, failure analyses and interview notes written.
[ ] You can explain every module, every threshold and every trade-off without opening the code.