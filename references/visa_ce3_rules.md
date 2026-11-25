# Visa Compelling Evidence 3.0 (CE 3.0) Rules Reference

## Contents

- [Scope and Eligibility](#scope-and-eligibility)
- [Mandatory Prior-Transaction Criteria](#mandatory-prior-transaction-criteria)
- [Core Data Elements Matching Rule](#core-data-elements-matching-rule)
- [Disqualifying Conditions](#disqualifying-conditions)
- [Required CSV Columns for Automated Matching](#required-csv-columns-for-automated-matching)
- [Packet Presentation Checklist](#packet-presentation-checklist)

## Scope and Eligibility

Visa Compelling Evidence 3.0 applies exclusively to **Visa Reason Code 10.4 (Other Fraud - Card-Absent Environment)** disputes. When a merchant satisfies all CE 3.0 requirements, liability shifts back to the issuing bank (or blocks the dispute pre-dispute via Verifi Order Insight).

## Mandatory Prior-Transaction Criteria

To qualify under Visa CE 3.0, the merchant must supply **at least two (2) prior undisputed transactions** meeting all of the following conditions:

- **Same payment credential and merchant**: Both prior transactions must have been settled by the same merchant with the same cardholder payment credential (same Primary Account Number / card fingerprint or customer payment method).
- **120-to-365-day lookback window**: Each prior transaction date must fall strictly between **120 days and 365 days** (inclusive) prior to the disputed transaction date. Transactions younger than 120 days or older than 365 days do not qualify.
- **Undisputed status**: Neither prior transaction may have been reported as fraud (TC40) or disputed as a chargeback. Refunded or canceled orders should also be excluded from qualifying matches.

## Core Data Elements Matching Rule

Across the disputed transaction and both qualifying prior undisputed transactions, the merchant must demonstrate matching values for **at least two (2) of the four (4) core data elements**:

1. **IP address** (`ip_address`)
2. **Device ID or device fingerprint** (`device_id`)
3. **User account ID or login ID** (`account_id`)
4. **Shipping address** (`shipping_address`)

**Critical requirement**: At least **one (1)** of the two matching core elements MUST be either **IP address** or **Device ID**. Matching only `account_id` and `shipping_address` without an IP address or Device ID match does **not** satisfy Visa CE 3.0.

## Disqualifying Conditions

- Fewer than 2 prior undisputed orders inside the 120-to-365-day window.
- Matching elements exist on one prior order but not consistently across at least two prior orders.
- Prior orders share only account ID and shipping address with no matching IP address or device ID.
- Dispute reason code is not Visa 10.4 (for example, Visa 13.1 Merchandise Not Received or Mastercard 4837 do not use Visa CE 3.0 liability shift, although prior undisputed orders remain helpful supporting context).

## Required CSV Columns for Automated Matching

Pass a historical orders CSV to `scripts/triage_and_ce3.py --history-csv` with these columns (case-insensitive header matching supported):

- `order_id`: Unique merchant order identifier.
- `transaction_date`: ISO date (`YYYY-MM-DD`) of the historical order.
- `status`: Order status (`completed`, `paid`, `fulfilled`, `refunded`, `disputed`, `canceled`).
- `disputed`: Boolean flag (`false`, `0`, `no`, `true`, `1`, `yes`).
- `ip_address`: Checkout or session IP address.
- `device_id`: Device fingerprint or hardware identifier (may be blank if unavailable).
- `account_id`: Merchant customer account ID or login email.
- `shipping_address`: Normalized delivery address string.
- `amount_usd`: Optional transaction amount for the exhibit table.

## Packet Presentation Checklist

When `ce3_qualified` is `true`, include all of the following in the representment packet:

- Explicit statement on the Cover Sheet invoking **Visa Compelling Evidence 3.0 (Visa 10.4)**.
- Side-by-side comparison table showing the disputed transaction alongside the two qualifying prior undisputed transactions, their dates, days-prior delta (120 to 365 days), and the matching core elements (highlighting IP address or Device ID).
- Supporting order confirmations and gateway logs as indexed exhibits.
