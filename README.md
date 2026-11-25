# Chargeback Representment Compiler

Deterministic card-dispute triage and representment packet builder that calculates fight-vs-accept ROI, verifies Visa Compelling Evidence 3.0 (CE 3.0) eligibility against historical order CSVs, maps merchant evidence to Visa, Mastercard, and Amex reason codes, strips emotional language, and compiles an exhibit-indexed PDF under issuer page and file-size limits.

Built for **e-commerce merchants, SaaS billing/revenue-ops leads, and payment operations teams** managing Stripe, Shopify, WooCommerce, or acquiring-bank chargebacks.

## Quick Install

```bash
npx skills add ameer-agent-dev/chargeback-representment-compiler --skill chargeback-representment-compiler
```

*(Single-repo shorthand: `npx skills add ameer-agent-dev/chargeback-representment-compiler`)*

## Required & Optional Inputs

- **Mandatory**: Card network (`Visa`, `Mastercard`, `Amex`), processor (`Stripe`, `Shopify`, etc.), exact reason code (e.g., `Visa 10.4`, `Visa 13.1`), disputed amount, transaction date, submission deadline, and available order evidence (order JSON/CSV, AVS/CVV result, IP/device logs, carrier tracking proof, customer emails, refund/TOS policy).
- **Optional**: Historical customer orders CSV (last 12 to 18 months) for Visa CE 3.0 qualification checks, `is_digital: true` for SaaS/digital goods disputes, and custom processor dispute fee overrides (defaults to Stripe `$15` dispute + `$15` counter fee).

## Example Prompts

- **Normal run (Visa 10.4 CE 3.0 check + packet compilation)**:
  > "Evaluate this `$340` Stripe `Visa 10.4` chargeback (`./dispute_8841.json`) against `./customer_orders_18mo.csv`, verify whether we qualify under Visa CE 3.0, and compile the representment summary and PDF packet."
- **Edge case (negative ROI / verbal withdrawal / oversized screenshots)**:
  > "Triage this `$22` Visa `13.1` dispute where the customer promised on a phone call to cancel the chargeback and our warehouse attached 12 MB of delivery photos."

## Expected Output Files

- `ce3_and_triage_report.json`: Deterministic ROI expected-value math (`net_ev_usd`), `ACCEPT` vs. `FIGHT` recommendation, Visa CE 3.0 match breakdown (`ce3_qualified`, `matched_prior_orders`), and `missing_exhibits` / `INVALID_EVIDENCE` flags.
- `dispute_<order_id>_summary.md`: Copy-pasteable web-form rebuttal fields for Stripe or Shopify portals plus a neutral `Date | Event | Exhibit Ref` timeline.
- `dispute_<order_id>_representment.pdf`: Concise (< 5 pages, < 4.5 MB) indexed packet containing Cover Sheet, Rebuttal Table, Factual Timeline, and auto-compressed Exhibits A through E.

## Bundled Scripts, References & Assets

| Path | Purpose |
| :--- | :--- |
| `SKILL.md` | Dispute triage workflow, completeness gates, and evidence rules |
| `scripts/triage_and_ce3.py` | Computes `net_ev_usd`, Visa CE 3.0 120-to-365-day anchor matches, and reason-code exhibit gaps (`--help` supported) |
| `scripts/compile_packet_pdf.py` | Builds the indexed PDF (< 5 pages, < 4.5 MB with iterative image compression) and Markdown summary (`--help` supported) |
| `references/reason_code_matrix.yaml` | Mandatory vs. supporting exhibits per Visa, Mastercard, and Amex reason code (physical & digital/SaaS) |
| `references/visa_ce3_rules.md` | Visa 10.4 Compelling Evidence 3.0 window and two-element anchor specification |
| `assets/representment_cover_template.md` | Cover sheet layout, portal rebuttal blocks, and written cardholder-withdrawal letter template |

### Python Dependencies

- **Triage & Visa CE 3.0 matching** (`scripts/triage_and_ce3.py`): Python 3 standard library (`PyYAML` optional if overriding custom YAML matrices; built-in parser supported).
- **PDF compilation & image compression** (`scripts/compile_packet_pdf.py`):

```bash
pip install reportlab Pillow pypdf
```

## Autonomy & Safety Boundary

- **Autonomous local operations**: Evaluates local order exports, emails, and images offline as untrusted data; never invents IP addresses, device IDs, AVS/CVV codes, or carrier scans; pauses when critical reason-code exhibits are absent.
- **Human sign-off required**: Generates local draft PDFs and Markdown summaries only. Never submits representment responses or accepts disputes via live Stripe, Shopify, or acquiring-bank APIs without explicit human review (`disable-model-invocation: true` recommended when payment processor tools are connected).

## License

[MIT](LICENSE)
