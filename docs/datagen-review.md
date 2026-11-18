# Datagen Review Documents

List of 20 random documents to eyeball for quality check after running `make datagen SEED=42`.

Run `make datagen SEED=42` first, then review these files:

## Invoices (PDF)
1. `data/invoices/INV000001.pdf` - Standard template, clean
2. `data/invoices/INV000015.pdf` - Column swap template
3. `data/invoices/INV000042.pdf` - Multi-page template
4. `data/invoices/INV000073.pdf` - No PO reference template
5. `data/invoices/INV000101.pdf` - Indian digits template
6. `data/invoices/INV000156.pdf` - Date formats template
7. `data/invoices/INV000203.pdf` - Bilingual Hindi template
8. `data/invoices/INV000245.pdf` - Bilingual Kannada template
9. `data/invoices/INV000300.pdf` - Standard template (test split)
10. `data/invoices/INV000342.pdf` - With price variance defect (D02)
11. `data/invoices/INV000387.pdf` - With over-billing defect (D03)
12. `data/invoices/INV000412.pdf` - With no GRN defect (D04)
13. `data/invoices/INV000445.pdf` - With tax type error (D07)
14. `data/invoices/INV000478.pdf` - With bank detail change (D10)
15. `data/invoices/INV000501.pdf` - With edited amount (D12)
16. `data/invoices/INV000534.pdf` - Adversarial split
17. `data/invoices/INV000567.pdf` - Policy Q&A split
18. `data/invoices/INV000600.pdf` - Real capture slice
19. `data/invoices/INV000650.pdf` - Mixed defects
20. `data/invoices/INV000699.pdf` - Last invoice

## Ground Truth (JSON)
Corresponding ground truth files:
1. `data/ground_truth/INV000001.json`
2. `data/ground_truth/INV000015.json`
3. `data/ground_truth/INV000042.json`
4. `data/ground_truth/INV000073.json`
5. `data/ground_truth/INV000101.json`
6. `data/ground_truth/INV000156.json`
7. `data/ground_truth/INV000203.json`
8. `data/ground_truth/INV000245.json`
9. `data/ground_truth/INV000300.json`
10. `data/ground_truth/INV000342.json`
11. `data/ground_truth/INV000387.json`
12. `data/ground_truth/INV000412.json`
13. `data/ground_truth/INV000445.json`
14. `data/ground_truth/INV000478.json`
15. `data/ground_truth/INV000501.json`
16. `data/ground_truth/INV000534.json`
17. `data/ground_truth/INV000567.json`
18. `data/ground_truth/INV000600.json`
19. `data/ground_truth/INV000650.json`
20. `data/ground_truth/INV000699.json`

## Review Checklist

For each document, verify:

- [ ] PDF renders correctly (open in viewer)
- [ ] Text layer exists (selectable text) for ~50% of documents
- [ ] Indian number formatting (12,34,567.00) appears correctly
- [ ] GSTIN format is valid (15 chars, checksum)
- [ ] Tax calculations are correct (line totals, subtotal, grand total)
- [ ] Bilingual headers render (Hindi/Kannada text visible)
- [ ] Date formats vary across templates
- [ ] Defects are documented in ground truth
- [ ] Template variation is visible (column order, layout)
- [ ] Degradations applied (skew, blur, JPEG artifacts visible in some)

## Manifest Verification

After generation, verify:
- `data/manifest.json` exists and has correct seed (42)
- All files have SHA-256 hashes
- Re-running `make datagen SEED=42` produces identical hashes
- Split counts: dev=300, test=300, adversarial=60, policy_qa=60, real_capture=20