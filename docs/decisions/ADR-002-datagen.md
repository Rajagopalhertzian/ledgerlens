# ADR-002: Synthetic Data Generation Design Decisions

## Status
Accepted

## Context
M1 requires a synthetic data generator for Indian GST invoices with ground truth for evaluation. The generator must be deterministic, produce valid GSTINs, render realistic PDFs with degradations, and create a comprehensive defect catalogue.

## Decisions

### 1. GSTIN Checksum Algorithm
**Decision**: Implement the official GSTIN checksum algorithm per GST specification.
- Format: 2-digit state code + 10-char PAN (5 letters + 4 digits + 1 letter) + 1 entity code + 1 'Z' + 1 checksum
- Checksum: Weighted sum modulo 36 with weights 1-14 (right to left), character set 0-9, A-Z
- Validation: Full validation including state code, PAN format, entity code (not 0), Z character, and checksum

**Rationale**: Required for realistic test data. Property-tested with Hypothesis.

### 2. Invoice Templates (8+)
**Decision**: Create 8 distinct Jinja2 HTML templates covering:
1. Standard layout
2. Column-swapped layout
3. Multi-page (with page breaks)
4. No PO reference
5. Indian digit grouping (12,34,567.00)
6. Multiple date formats (DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD)
7. Bilingual English+Hindi
8. Bilingual English+Kannada

**Rationale**: SPEC requires ≥8 templates with different layouts, fonts, column orders, multi-page, bilingual headers, Indian digit grouping, and multiple date formats.

### 3. PDF Rendering with WeasyPrint
**Decision**: Use WeasyPrint for HTML→PDF conversion.
- Text layer kept in 50% of PDFs (default WeasyPrint behavior)
- Degradations applied via PIL/Pillow: skew (±3°), perspective, blur, JPEG artifacts (quality 60-80), shadows, stamps, handwriting annotations
- 50% probability for each degradation type

**Rationale**: WeasyPrint is pure Python, no external dependencies (unlike Playwright), supports CSS @page, and produces high-quality PDFs with text layers.

### 4. Defect Distribution
**Decision**: 
- 55% clean (D01)
- 45% spread across D02-D15 (~3.2% each)
- Test split: guaranteed ≥8 per defect type
- Total: 720 invoices (300 dev, 300 test, 60 adversarial, 60 policy QA, 20 real-capture)

**Rationale**: SPEC mandates 55% clean, test split frozen with minimum per defect type.

### 5. Deterministic Generation
**Decision**: Use Python's `random.Random(seed)` and `numpy.random.seed(seed)` for full reproducibility.
- Single seed controls all randomness
- Manifest includes SHA-256 of every file
- Re-running with same seed produces identical output

**Rationale**: SPEC requires `make datagen SEED=42` to be deterministic with manifest verification.

### 6. Ground Truth Structure
**Decision**: Ground truth JSON includes:
- All header fields, line items, taxes, totals
- Expected decision (post/investigate/escalate/reject)
- Defects array with type and evidence
- Expected actions array
- PO/GRN references for matching

**Rationale**: Needed for oracle baseline and all downstream evaluations.

### 7. Evaluation Harness Metrics
**Decision**: Implement core metrics in `evals/harness.py`:
- Field normalization (numbers, dates, currency)
- Line-item matching via Hungarian algorithm (scipy.optimize.linear_sum_assignment)
- Bootstrap confidence intervals
- Expected Calibration Error (ECE)
- Selective prediction curves (coverage vs precision)
- Results writer (JSON + Markdown)
- Baseline comparer for `make gate`

**Rationale**: SPEC requires all these metrics, unit-tested.

### 8. Oracle Baseline
**Decision**: Run decision logic on ground-truth fields (not extracted) to get upper bound.
- Validators: tax arithmetic, GST rules, duplicates, bank details, PO reference, edited amounts, embedded instructions, illegible, policy
- Decision mapping: D01→POST, D05/D14→REJECT, D06/D09/D10/D15→ESCALATE, others→INVESTIGATE

**Rationale**: Separates extraction errors from logic errors per SPEC.

### 9. Dependencies Added
- `jinja2>=3.1.4` - Template rendering
- `scipy>=1.13.0` - Hungarian algorithm for line matching
- `hypothesis>=6.100.0` - Property-based testing (already in pyproject.toml)
- `weasyprint>=62.0` - HTML to PDF (already in pyproject.toml)

## Consequences

### Positive
- Fully deterministic, reproducible data generation
- Comprehensive defect coverage for evaluation
- Realistic PDF variations with degradations
- Valid GSTINs with proper checksums
- Unit-tested metrics for reliable evaluation

### Negative
- WeasyPrint requires system dependencies (cairo, pango, gdk-pixbuf) - handled in Docker
- Degradations require pdf2image+poppler for full implementation (stubbed for now)
- Hindi/Kannada fonts need Noto fonts installed

## Verification
- `make datagen SEED=42` creates dev/test + manifest
- Re-running gives identical SHA-256 hashes
- `make test` passes all unit tests
- `make eval-oracle` writes results
- 20 documents reviewed per docs/datagen-review.md