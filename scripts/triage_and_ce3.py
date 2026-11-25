#!/usr/bin/env python3
"""Deterministic chargeback ROI triage, Visa CE 3.0 matcher, and reason-code exhibit gap checker.

Uses Python 3 standard library only (with optional PyYAML support if installed).
Exit codes:
  0 - Triage report generated cleanly
  2 - Missing or invalid input files or required fields
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

# Built-in fallback matrix matching references/reason_code_matrix.yaml so the script
# remains 100% deterministic even in environments without PyYAML.
DEFAULT_MATRIX: dict[str, dict[str, Any]] = {
    "visa_10_4": {
        "network": "Visa",
        "code": "10.4",
        "category": "Other Fraud - Card-Absent Environment",
        "physical_mandatory": ["avs_cvv_match", "delivery_proof", "order_confirmation"],
        "digital_mandatory": [
            "login_timestamps",
            "ip_geolocation_match",
            "feature_usage_logs",
            "clickwrap_tos_acceptance",
        ],
        "ce3_eligible": True,
    },
    "visa_13_1": {
        "network": "Visa",
        "code": "13.1",
        "category": "Merchandise / Services Not Received",
        "physical_mandatory": [
            "carrier_tracking_proof",
            "delivery_confirmation",
            "shipping_address_match",
        ],
        "digital_mandatory": [
            "login_timestamps",
            "ip_geolocation_match",
            "feature_usage_logs",
            "access_delivery_log",
        ],
        "ce3_eligible": False,
    },
    "visa_13_3": {
        "network": "Visa",
        "code": "13.3",
        "category": "Not as Described or Defective Merchandise / Services",
        "physical_mandatory": [
            "product_description_listing",
            "order_confirmation",
            "refund_return_policy",
        ],
        "digital_mandatory": [
            "product_description_listing",
            "feature_usage_logs",
            "clickwrap_tos_acceptance",
            "refund_return_policy",
        ],
        "ce3_eligible": False,
    },
    "visa_13_2": {
        "network": "Visa",
        "code": "13.2",
        "category": "Cancelled Recurring Transaction",
        "physical_mandatory": [
            "recurring_billing_agreement",
            "cancellation_policy_disclosure",
            "no_prior_cancellation_log",
        ],
        "digital_mandatory": [
            "recurring_billing_agreement",
            "clickwrap_tos_acceptance",
            "feature_usage_logs",
            "no_prior_cancellation_log",
        ],
        "ce3_eligible": False,
    },
    "mastercard_4837": {
        "network": "Mastercard",
        "code": "4837",
        "category": "No Cardholder Authorization",
        "physical_mandatory": ["avs_cvv_match", "delivery_proof", "order_confirmation"],
        "digital_mandatory": [
            "login_timestamps",
            "ip_geolocation_match",
            "feature_usage_logs",
            "clickwrap_tos_acceptance",
        ],
        "ce3_eligible": False,
    },
    "mastercard_4855": {
        "network": "Mastercard",
        "code": "4855",
        "category": "Goods or Services Not Provided",
        "physical_mandatory": [
            "carrier_tracking_proof",
            "delivery_confirmation",
            "shipping_address_match",
        ],
        "digital_mandatory": [
            "login_timestamps",
            "ip_geolocation_match",
            "feature_usage_logs",
            "access_delivery_log",
        ],
        "ce3_eligible": False,
    },
    "mastercard_4853": {
        "network": "Mastercard",
        "code": "4853",
        "category": "Cardholder Dispute (Not as Described / Cancelled Recurring)",
        "physical_mandatory": [
            "product_description_listing",
            "refund_return_policy",
            "order_confirmation",
        ],
        "digital_mandatory": [
            "clickwrap_tos_acceptance",
            "refund_return_policy",
            "feature_usage_logs",
        ],
        "ce3_eligible": False,
    },
    "amex_f29": {
        "network": "Amex",
        "code": "F29",
        "category": "Card Not Present Fraud",
        "physical_mandatory": ["avs_cvv_match", "delivery_proof", "shipping_address_match"],
        "digital_mandatory": [
            "login_timestamps",
            "ip_geolocation_match",
            "feature_usage_logs",
            "clickwrap_tos_acceptance",
        ],
        "ce3_eligible": False,
    },
    "amex_c08": {
        "network": "Amex",
        "code": "C08",
        "category": "Goods / Services Not Received or Only Partially Received",
        "physical_mandatory": [
            "carrier_tracking_proof",
            "delivery_confirmation",
            "shipping_address_match",
        ],
        "digital_mandatory": [
            "login_timestamps",
            "ip_geolocation_match",
            "feature_usage_logs",
            "access_delivery_log",
        ],
        "ce3_eligible": False,
    },
    "amex_c31": {
        "network": "Amex",
        "code": "C31",
        "category": "Goods / Services Not as Described",
        "physical_mandatory": [
            "product_description_listing",
            "refund_return_policy",
            "order_confirmation",
        ],
        "digital_mandatory": [
            "product_description_listing",
            "clickwrap_tos_acceptance",
            "feature_usage_logs",
            "refund_return_policy",
        ],
        "ce3_eligible": False,
    },
}

DEFAULT_DESCRIPTIONS: dict[str, str] = {
    "avs_cvv_match": "Gateway AVS and CVV verification result for the disputed charge",
    "delivery_proof": "Carrier delivery confirmation or proof of delivery (POD) PDF",
    "delivery_confirmation": "Carrier delivery confirmation showing Delivered status and date",
    "carrier_tracking_proof": "Carrier tracking number and full transit scan history",
    "shipping_address_match": "Proof that shipping address matches the customer order record",
    "order_confirmation": "Order invoice/receipt with itemized SKU, amount, and timestamp",
    "login_timestamps": "Authenticated user login timestamps before and after billing",
    "ip_geolocation_match": "IP geolocation log linking account logins to the billing region",
    "feature_usage_logs": "Product, download, or SaaS feature usage logs after purchase",
    "clickwrap_tos_acceptance": "Timestamped clickwrap acceptance of Terms of Service and billing policy",
    "access_delivery_log": "Server log confirming digital download or account provisioning",
    "product_description_listing": "Archived product page or plan description at time of purchase",
    "refund_return_policy": "Published refund, return, or cancellation policy shown at checkout",
    "recurring_billing_agreement": "Signed or clickwrap recurring subscription authorization",
    "cancellation_policy_disclosure": "Clear cancellation instructions disclosed prior to billing",
    "no_prior_cancellation_log": "Account log showing no cancellation request before the billing date",
}

CE3_CORE_ELEMENTS = ("ip_address", "device_id", "account_id", "shipping_address")
CE3_ANCHOR_ELEMENTS = {"ip_address", "device_id"}


def parse_iso_date(value: str, field_name: str) -> dt.date:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing required date field: {field_name}")
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date for {field_name}: {text!r} (expected YYYY-MM-DD)") from exc


def normalize_str(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def load_matrix(matrix_path: str | None) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    if not matrix_path:
        return DEFAULT_MATRIX, DEFAULT_DESCRIPTIONS
    path = Path(matrix_path)
    if not path.is_file():
        return DEFAULT_MATRIX, DEFAULT_DESCRIPTIONS
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rc = loaded.get("reason_codes")
        desc = loaded.get("exhibit_descriptions")
        if isinstance(rc, dict) and rc:
            return rc, (desc if isinstance(desc, dict) else DEFAULT_DESCRIPTIONS)
    except Exception:
        pass
    return DEFAULT_MATRIX, DEFAULT_DESCRIPTIONS


def resolve_reason_code_key(network: str, reason_code: str, matrix: dict[str, dict[str, Any]]) -> str | None:
    net_norm = normalize_str(network).replace(" ", "")
    code_norm = normalize_str(reason_code).replace(" ", "").replace(".", "_")
    direct = f"{net_norm}_{code_norm}"
    if direct in matrix:
        return direct
    for key, entry in matrix.items():
        if normalize_str(entry.get("network")).replace(" ", "") == net_norm:
            if normalize_str(entry.get("code")).replace(".", "_") == code_norm:
                return key
    return None


def is_undisputed_row(row: dict[str, str]) -> bool:
    disputed_val = normalize_str(row.get("disputed", "false"))
    if disputed_val in {"true", "1", "yes", "y"}:
        return False
    status_val = normalize_str(row.get("status", "completed"))
    if status_val in {"disputed", "chargeback", "fraud", "refunded", "canceled", "cancelled", "voided"}:
        return False
    return True


def evaluate_ce3(
    dispute: dict[str, Any],
    tx_date: dt.date,
    history_csv_path: str | None,
    ce3_eligible: bool,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    if not ce3_eligible:
        notes.append("Reason code is not Visa 10.4; Visa CE 3.0 liability shift does not apply.")
        return False, [], notes
    if not history_csv_path:
        notes.append("No historical orders CSV supplied; Visa CE 3.0 cannot be verified.")
        return False, [], notes

    csv_path = Path(history_csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Historical orders CSV not found: {csv_path}")

    dispute_elements = {el: normalize_str(dispute.get(el)) for el in CE3_CORE_ELEMENTS}
    qualifying_orders: list[dict[str, Any]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            notes.append("Historical orders CSV has no header row.")
            return False, [], notes
        for raw_row in reader:
            row = {normalize_str(k): (v or "").strip() for k, v in raw_row.items() if k is not None}
            if not is_undisputed_row(row):
                continue
            row_date_str = row.get("transaction_date") or row.get("order_date") or row.get("date")
            if not row_date_str:
                continue
            try:
                prior_date = parse_iso_date(row_date_str, "history.transaction_date")
            except ValueError:
                continue
            days_prior = (tx_date - prior_date).days
            if not (120 <= days_prior <= 365):
                continue

            matched = [
                el
                for el in CE3_CORE_ELEMENTS
                if dispute_elements[el] and normalize_str(row.get(el)) == dispute_elements[el]
            ]
            has_anchor = any(el in CE3_ANCHOR_ELEMENTS for el in matched)
            if len(matched) >= 2 and has_anchor:
                qualifying_orders.append(
                    {
                        "order_id": row.get("order_id", "unknown"),
                        "transaction_date": prior_date.isoformat(),
                        "days_prior": days_prior,
                        "matched_elements": matched,
                        "amount_usd": row.get("amount_usd", ""),
                    }
                )

    # Verify at least 2 qualifying prior orders share a consistent >= 2 element set including IP or Device ID.
    ce3_qualified = False
    best_pair_elements: list[str] = []
    if len(qualifying_orders) >= 2:
        for i in range(len(qualifying_orders)):
            for j in range(i + 1, len(qualifying_orders)):
                shared = sorted(
                    set(qualifying_orders[i]["matched_elements"])
                    & set(qualifying_orders[j]["matched_elements"])
                )
                if len(shared) >= 2 and any(el in CE3_ANCHOR_ELEMENTS for el in shared):
                    ce3_qualified = True
                    if len(shared) > len(best_pair_elements):
                        best_pair_elements = shared

    if ce3_qualified:
        notes.append(
            f"Visa CE 3.0 qualified: {len(qualifying_orders)} undisputed prior orders within 120-365 days "
            f"sharing consistent core elements {best_pair_elements}."
        )
    else:
        notes.append(
            f"Visa CE 3.0 not met: found {len(qualifying_orders)} qualifying prior order(s) in 120-365 day window "
            "(requires >= 2 undisputed orders sharing >= 2 core elements including ip_address or device_id)."
        )
    return ce3_qualified, qualifying_orders, notes


def run_triage(
    dispute: dict[str, Any],
    history_csv_path: str | None,
    matrix_path: str | None,
) -> dict[str, Any]:
    network = str(dispute.get("network", "")).strip()
    reason_code = str(dispute.get("reason_code", "")).strip()
    processor = str(dispute.get("processor", "Stripe")).strip() or "Stripe"
    order_id = str(dispute.get("order_id", "unknown")).strip() or "unknown"
    amount_usd = float(dispute.get("amount_usd", 0.0))
    if amount_usd <= 0:
        raise ValueError("amount_usd must be a positive number.")

    tx_date = parse_iso_date(dispute.get("transaction_date", ""), "transaction_date")
    deadline_date = parse_iso_date(dispute.get("deadline_date", ""), "deadline_date")
    as_of_date = (
        parse_iso_date(dispute["as_of_date"], "as_of_date")
        if dispute.get("as_of_date")
        else dt.date.today()
    )
    deadline_days_left = (deadline_date - as_of_date).days

    received_fee_usd = float(dispute.get("received_fee_usd", 15.0))
    counter_fee_usd = float(dispute.get("counter_fee_usd", 15.0))
    is_digital = bool(dispute.get("is_digital", False))

    matrix, descriptions = load_matrix(matrix_path)
    rc_key = resolve_reason_code_key(network, reason_code, matrix)
    rc_entry = matrix.get(rc_key) if rc_key else None

    ce3_eligible = bool(rc_entry.get("ce3_eligible", False)) if rc_entry else (
        normalize_str(network) == "visa" and normalize_str(reason_code) == "10.4"
    )
    ce3_qualified, matched_prior_orders, ce3_notes = evaluate_ce3(
        dispute=dispute,
        tx_date=tx_date,
        history_csv_path=history_csv_path,
        ce3_eligible=ce3_eligible,
    )

    provided_set = {normalize_str(x) for x in dispute.get("provided_exhibits", []) if str(x).strip()}
    if ce3_qualified:
        provided_set.add("ce3_prior_orders")

    mandatory_key = "digital_mandatory" if is_digital else "physical_mandatory"
    mandatory_list: list[str] = list(rc_entry.get(mandatory_key, [])) if rc_entry else []

    missing_exhibits: list[dict[str, str]] = []
    for req in mandatory_list:
        if normalize_str(req) not in provided_set:
            missing_exhibits.append(
                {
                    "flag": "MISSING_CRITICAL_EXHIBIT",
                    "exhibit_key": req,
                    "description": descriptions.get(req, req.replace("_", " ")),
                }
            )

    invalid_evidence_flags: list[dict[str, str]] = []
    if bool(dispute.get("verbal_withdrawal_claimed", False)) and "written_withdrawal_letter" not in provided_set:
        invalid_evidence_flags.append(
            {
                "flag": "INVALID_EVIDENCE",
                "issue": "Verbal phone promise to withdraw dispute is rejected by card networks.",
                "remediation": "Obtain a signed written cardholder withdrawal letter using assets/representment_cover_template.md.",
            }
        )

    # Deterministic win probability estimate based on CE 3.0 and mandatory exhibit coverage.
    if ce3_qualified:
        estimated_win_prob = 0.85
    elif not rc_entry:
        estimated_win_prob = 0.40
    elif len(missing_exhibits) == 0:
        estimated_win_prob = 0.65
    elif len(missing_exhibits) == 1:
        estimated_win_prob = 0.25
    else:
        estimated_win_prob = 0.10

    # Conservative incremental EV of fighting vs accepting:
    # Accepting loses amount_usd + sunk received_fee_usd.
    # Fighting risks counter_fee_usd for an expected recovery of estimated_win_prob * amount_usd.
    net_ev_usd = round((estimated_win_prob * amount_usd) - counter_fee_usd, 2)

    if net_ev_usd <= 0:
        fight_recommendation = "ACCEPT"
        rationale = (
            f"Negative expected value (${net_ev_usd:.2f}): expected recovery "
            f"(${estimated_win_prob * amount_usd:.2f} at {int(estimated_win_prob * 100)}% est. win rate) "
            f"does not cover the ${counter_fee_usd:.2f} counter fee."
        )
    elif missing_exhibits and not ce3_qualified:
        fight_recommendation = "PAUSE_MISSING_EXHIBITS"
        rationale = (
            f"Positive EV (${net_ev_usd:.2f}) if exhibits are completed, but {len(missing_exhibits)} "
            "mandatory exhibit(s) are currently missing."
        )
    else:
        fight_recommendation = "FIGHT"
        rationale = (
            f"Positive expected value (${net_ev_usd:.2f}) with strong evidence coverage "
            f"({int(estimated_win_prob * 100)}% est. win rate, CE 3.0 qualified={ce3_qualified})."
        )

    return {
        "order_id": order_id,
        "network": network,
        "reason_code": reason_code,
        "reason_code_category": rc_entry.get("category") if rc_entry else "Unknown / Unmapped Reason Code",
        "processor": processor,
        "is_digital": is_digital,
        "amount_usd": round(amount_usd, 2),
        "received_fee_usd": round(received_fee_usd, 2),
        "counter_fee_usd": round(counter_fee_usd, 2),
        "estimated_win_prob": estimated_win_prob,
        "net_ev_usd": net_ev_usd,
        "fight_recommendation": fight_recommendation,
        "recommendation_rationale": rationale,
        "ce3_qualified": ce3_qualified,
        "matched_prior_orders": matched_prior_orders,
        "ce3_notes": ce3_notes,
        "missing_exhibits": missing_exhibits,
        "invalid_evidence_flags": invalid_evidence_flags,
        "deadline_date": deadline_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "deadline_days_left": deadline_days_left,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="triage_and_ce3.py",
        description="Compute chargeback fight-vs-accept ROI, Visa CE 3.0 eligibility, and reason-code exhibit gaps.",
        epilog="Exit codes: 0 = report generated, 2 = invalid input or missing file.",
    )
    parser.add_argument("--dispute", required=True, help="Path to dispute metadata JSON file")
    parser.add_argument("--history-csv", help="Optional path to historical customer orders CSV for Visa CE 3.0")
    parser.add_argument("--matrix", help="Optional path to references/reason_code_matrix.yaml")
    parser.add_argument("--output", help="Optional path to write ce3_and_triage_report.json")
    args = parser.parse_args()

    try:
        dispute_path = Path(args.dispute)
        if not dispute_path.is_file():
            raise FileNotFoundError(f"Dispute JSON not found: {dispute_path}")
        dispute_data = json.loads(dispute_path.read_text(encoding="utf-8"))
        report = run_triage(
            dispute=dispute_data,
            history_csv_path=args.history_csv,
            matrix_path=args.matrix,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
