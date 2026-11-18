# LedgerLens: prompts for Claude Code

## How to use

Create an empty repo. Copy CLAUDE.md and SPEC.md into its root.
Start Claude Code in plan mode (claude --permission-mode plan, or press Shift+Tab until plan mode shows). Review and edit the plan before approving it.
One milestone per session. When a milestone is done: run make check, commit, run /clear, then paste the next prompt.
If Claude gets something wrong twice, run /clear and rewrite the prompt with what you learned instead of arguing in the same session.
You write and verify labels (golden sets, rubric scores). Claude Code drafts, you decide.

## Prompt 0: kickoff (M0)

You are my pair-programmer for "LedgerLens", a portfolio-grade, multimodal agentic accounts-payable platform for Indian GST invoices. It must be end-to-end, evaluated with real numbers, and defensible in GenAI / agentic AI / AI engineer interviews.

Start in plan mode. First read CLAUDE.md and SPEC.md (sections 1-3 and M0 only), then:
1. Propose the repo layout, the dependency list and a Makefile. Check each library's CURRENT docs and pin exact versions; do not rely on memory for LangGraph, LangChain, MCP SDK / FastMCP, Qdrant or any OCR/VLM library.
2. Write docs/PLAN.md: milestones M0-M9 with the evidence file each one must produce under evals/results/.
3. Implement M0 only: scaffold, docker compose (core and full profiles), CI skeleton (ruff, pyright, pytest), the provider-agnostic LLM adapter (roles, disk cache, token/cost accounting, retries, timeouts) with tests, a hello-world OpenTelemetry trace, and ADR-001 with the versions you verified.

Rules: never fabricate metrics or labels; every number must come from a command that writes to evals/results/; write tests before logic for validators; ask before adding heavy dependencies; secrets only in .env; small commits; run `make check` before saying done.

Stop after M0 with a summary of what exists, what you verified, and what you would do next. I will start a fresh session for each later milestone.

## M1: synthetic data and eval harness

Read SPEC.md section M1 and section 13. Plan first, then implement: the synthetic generator (entities, 8+ invoice templates, degradations, defect catalogue D01-D15), ERP seed data, dataset manifest with SHA-256 hashes, the metric library (normalisation, line-item matching, bootstrap CIs, ECE, selective-prediction curves, results writer, baseline comparer) and the oracle baseline.

Constraints: deterministic with SEED; the test split is frozen after generation and never used for tuning; metric functions need unit tests including edge cases.

Done when: `make datagen SEED=42` is reproducible (identical hashes on re-run), `make test` passes, `make eval-oracle` writes results. Before moving on, list 20 random document paths in docs/datagen-review.md so I can eyeball them.

## M2: extraction

Read SPEC.md section M2 and section 13. Plan first, then implement the extraction subsystem: OCR backends, VLM backend with JSON-schema output, OCR grounding check, deterministic validators, calibrated confidence (fit on dev only), cascade router, and the ablation runner for E0-E4.

Start with the 30-document dev subset and show me a cost estimate before any run over 50 documents; cache everything.

Done when: `make eval-extraction` writes the E0-E4 table with bootstrap CIs, ECE, STP at fixed precision, cost and latency; the reliability diagram is saved; thresholds were chosen on dev and applied to test. Write docs/extraction-failures.md with 10 real failures (image, cause, what we tried). Do not hide bad results.

## M3: ERP, validation, matching, ERP MCP server

Read SPEC.md section M3. Plan first, then implement: ERP schema with Alembic migrations and seed, validators V1-V12 as pure functions with property-based tests, entity resolution, 3-way matching with a versioned tolerance YAML, rule-based risk scoring, and the ERP MCP server (Streamable HTTP, bearer auth with scopes, HMAC approval-token verification on write tools, idempotency keys).

Check the current MCP SDK / FastMCP docs before writing the server and wrap them behind our own thin layer.

Done when: validators and matching are thoroughly tested; `make eval-matching` reports per-defect precision/recall on oracle fields and on extracted fields (with the gap); MCP contract tests pass, including a failed write without a valid token that is audited.

## M4: agent workflow

Read SPEC.md section M4. Plan first, then implement the LangGraph workflow with a Postgres checkpointer, interrupt()-based approval, investigator / verifier / communicator roles with separate tool permissions, budget and step caps, and the audit log. Implement baselines B0-B3.

Check the current LangGraph and LangChain MCP docs first. Remember: a node restarts from its beginning after an interrupt resumes, so keep pre-interrupt side effects idempotent.

Done when: the crash/resume test passes with zero duplicate posts; `make eval-agent` reports cause accuracy, action accuracy, evidence-grounding rate, escalation precision/recall, unsafe actions (must be 0), tool calls, cost and latency for B0-B3; docs/agent-vs-workflow.md states when the agent is and is not worth it. Remind me to label 60 exception reports for judge calibration.

## M5: policy RAG and vendor memory

Read SPEC.md section M5. Plan first, then implement: the synthetic policy corpus (with near-duplicates, superseded versions and one contradiction), structure-aware chunking, hybrid retrieval with rerank and metadata filters, the policy MCP server, cited answers with abstention, and the vendor correction memory with its poisoning guard. Check current Qdrant hybrid-query docs first.

Done when: `make eval-rag` writes the retrieval ablation (dense, BM25, hybrid, hybrid + rerank) and a failure taxonomy; exception reports cite policy passages that resolve to real chunks; the learning curve (E4 vs E5) is plotted from real runs; a memory-poisoning test fails to change a bank detail. I will verify the 60 question labels myself.

## M6: security and guardrails

Read SPEC.md section M6. Fetch the official OWASP Top 10 for Agentic Applications and use its exact category names. Plan first, then implement controls C1-C10 and the 60-case adversarial suite, and write docs/threat-model.md.

Done when: `make eval-security` reports attack success rate on write actions (target 0 of N), injection detection recall, and false-positive rate on benign documents; the suite runs in CI on cached responses. Show me any case that got through and fix the design, not just the prompt.

## M7: observability, cost, resilience

Read SPEC.md section M7. Plan first, then implement OpenTelemetry tracing across API, worker, graph nodes, MCP calls and model calls, one LLM-observability backend (record the choice in an ADR), the metrics dashboard, a replay command, cost/latency optimisation with a Pareto chart, a load test, and resilience tests R1-R6.

Done when: one invoice shows end to end in a trace with costs; the Pareto chart and load-test results are saved under evals/results/; R1-R6 pass.

## M8: UI, deployment, docs, demo

Read SPEC.md section M8. Plan first, then build the reviewer console (queue, review page with evidence, trace timeline, metrics), deployment with a demo mode (synthetic data, basic auth, rate limits, spend cap), and generate the documentation set from evals/results/ only. Write docs/demo-script.md for a 3-4 minute demo.

Done when: `docker compose --profile full up` works from a clean checkout following the README, and every number in the docs traces to a results file. Then draft docs/interview-notes.md and docs/resume-bullets.md using only real numbers.

## M9: stretch (choose at most two)

Read SPEC.md section M9. I choose: <A2A | multi-tenant RLS | small-model extractor | Indic templates | tamper detector | active learning>. Plan first, state the evidence it will produce, implement it behind a feature flag, and add it to the eval report only if the numbers justify it.

## Utility prompts

### Security review

Review the current diff like a senior security reviewer. Look for prompt-injection paths (any place untrusted text can influence tools, arguments or recipients), SSRF, SQL injection, secrets, PII in logs or traces, missing idempotency, race conditions, and write paths that skip approval-token checks. List findings by severity with file and line, and propose fixes.

### Metric integrity check

List every number in README.md and docs/. For each, name the file in evals/results/ and the make target that produced it. Flag anything without a source or from a stale run.

### Interview rehearsal (run this near the end, in a fresh session)

Act as a tough interviewer for GenAI / agentic AI / AI engineer roles. Using this repo's actual code, ADRs and evals/results/, ask me one hard question at a time (design trade-offs, failures, metrics, security, scaling). After each answer, critique it: what was vague, what number I should have quoted, and what follow-up a real interviewer would ask. Do 12 questions.