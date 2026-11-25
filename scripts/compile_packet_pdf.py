#!/usr/bin/env python3
"""Compile a neutral, exhibit-indexed chargeback representment PDF (<5 pages, <4.5 MB) and Markdown summary.

Requires reportlab, Pillow, and pypdf for PDF generation and image compression.
Exit codes:
  0 - Packet PDF and Markdown summary compiled cleanly within limits
  1 - Packet compiled but exceeded page or size limits
  2 - Missing dependency or invalid input
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

EMOTIONAL_TERMS = [
    "scammer",
    "scam",
    "liar",
    "lying",
    "fraudster",
    "thief",
    "stealing",
    "ridiculous",
    "outrageous",
    "unbelievable",
    "absurd",
    "furious",
    "pathetic",
    "crook",
]


def sanitize_neutral(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    cleaned = str(text or "")
    for term in EMOTIONAL_TERMS:
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        if pattern.search(cleaned):
            found.append(term)
            cleaned = pattern.sub("[redacted non-factual term]", cleaned)
    cleaned = re.sub(r"!{2,}", ".", cleaned)
    return cleaned.strip(), found


def build_summary_markdown(packet: dict[str, Any], triage: dict[str, Any] | None) -> str:
    order_id = packet.get("order_id", "unknown")
    merchant = packet.get("merchant_name", "Merchant")
    dispute = packet.get("dispute", {})
    network = dispute.get("network", "")
    reason_code = dispute.get("reason_code", "")
    processor = dispute.get("processor", "Stripe")
    amount = dispute.get("amount_usd", 0.0)
    tx_date = dispute.get("transaction_date", "")
    deadline = dispute.get("deadline_date", "")
    ce3_flag = "Yes" if (triage and triage.get("ce3_qualified")) else "No"

    lines = [
        f"# Chargeback Representment Summary: Order {order_id}",
        "",
        "## Stripe / Shopify Web-Form Fields",
        "",
        f"- **Merchant**: {merchant}",
        f"- **Order ID**: {order_id}",
        f"- **Processor**: {processor}",
        f"- **Card Network & Reason Code**: {network} {reason_code}",
        f"- **Disputed Amount**: ${float(amount):.2f}",
        f"- **Transaction Date**: {tx_date}",
        f"- **Submission Deadline**: {deadline}",
        f"- **Visa CE 3.0 Qualified**: {ce3_flag}",
        f"- **Product / Service Description**: {packet.get('product_description', 'Not provided')}",
        f"- **Shipping / Delivery Proof**: {packet.get('delivery_summary', 'Not provided')}",
        "",
        "## Copy-Paste Rebuttal Statement",
        "",
        sanitize_neutral(packet.get("executive_summary", ""))[0],
        "",
        "## Chronological Timeline",
        "",
        "| Date | Event | Exhibit Ref |",
        "| --- | --- | --- |",
    ]
    for item in packet.get("timeline", []):
        ev_clean, _ = sanitize_neutral(item.get("event", ""))
        lines.append(f"| {item.get('date', '')} | {ev_clean} | {item.get('exhibit_ref', '')} |")

    lines.extend(["", "## Exhibit Checklist", ""])
    for ex in packet.get("exhibits", []):
        lines.append(f"- **{ex.get('label', 'Exhibit')}**: {ex.get('title', 'Untitled')} ({ex.get('type', 'text')})")

    if triage and triage.get("missing_exhibits"):
        lines.extend(["", "## Missing Critical Exhibits", ""])
        for m in triage["missing_exhibits"]:
            lines.append(f"- **MISSING_CRITICAL_EXHIBIT**: {m.get('exhibit_key')} - {m.get('description')}")

    if triage and triage.get("invalid_evidence_flags"):
        lines.extend(["", "## Invalid Evidence Warnings", ""])
        for flag in triage["invalid_evidence_flags"]:
            lines.append(f"- **INVALID_EVIDENCE**: {flag.get('issue')} Remediation: {flag.get('remediation')}")

    return "\n".join(lines) + "\n"


def compress_image_to_buffer(image_path: Path, max_dim: int, jpeg_quality: int) -> tuple[io.BytesIO, int, int]:
    from PIL import Image

    with Image.open(image_path) as img:
        rgb = img.convert("RGB")
        rgb.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        buf.seek(0)
        return buf, rgb.width, rgb.height


def render_pdf(
    packet: dict[str, Any],
    triage: dict[str, Any] | None,
    pdf_path: Path,
    img_max_dim: int,
    jpeg_quality: int,
) -> list[str]:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    redacted_terms: list[str] = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PacketTitle",
        parent=styles["Heading1"],
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1B365D"),
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "PacketH2",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1B365D"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "PacketBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
    )
    cell_style = ParagraphStyle(
        "CellBody",
        parent=styles["BodyText"],
        fontSize=8.5,
        leading=10.5,
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    story: list[Any] = []

    order_id = packet.get("order_id", "unknown")
    merchant = packet.get("merchant_name", "Merchant")
    dispute = packet.get("dispute", {})
    network = dispute.get("network", "")
    reason_code = dispute.get("reason_code", "")
    amount = float(dispute.get("amount_usd", 0.0))

    # Section 1: Cover Sheet
    story.append(Paragraph(f"Chargeback Representment Packet: Order {order_id}", title_style))
    meta_rows = [
        ["Merchant", str(merchant), "Processor", str(dispute.get("processor", "Stripe"))],
        ["Network / Code", f"{network} {reason_code}", "Disputed Amount", f"${amount:.2f}"],
        ["Transaction Date", str(dispute.get("transaction_date", "")), "Deadline", str(dispute.get("deadline_date", ""))],
        [
            "Visa CE 3.0 Qualified",
            "Yes" if (triage and triage.get("ce3_qualified")) else "No",
            "Order ID",
            str(order_id),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[1.35 * inch, 2.25 * inch, 1.35 * inch, 2.25 * inch])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2F7")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EEF2F7")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 6))

    exec_clean, found = sanitize_neutral(packet.get("executive_summary", ""))
    redacted_terms.extend(found)
    story.append(Paragraph("Executive Rebuttal Statement", h2_style))
    story.append(Paragraph(exec_clean or "Factual merchant representment summary enclosed.", body_style))

    # Section 2: Reason-Code Rebuttal Table
    rebuttal_rows = packet.get("rebuttal_rows", [])
    if rebuttal_rows:
        story.append(Paragraph("Reason-Code Rebuttal Table", h2_style))
        tbl_data = [["Requirement", "Merchant Evidence", "Exhibit"]]
        for row in rebuttal_rows:
            ev_clean, found_r = sanitize_neutral(row.get("evidence", ""))
            redacted_terms.extend(found_r)
            tbl_data.append(
                [
                    Paragraph(str(row.get("requirement", "")), cell_style),
                    Paragraph(ev_clean, cell_style),
                    Paragraph(str(row.get("exhibit_ref", "")), cell_style),
                ]
            )
        r_table = Table(tbl_data, colWidths=[1.8 * inch, 4.4 * inch, 1.0 * inch])
        r_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B365D")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(r_table)

    # Optional Visa CE 3.0 Prior Orders Table
    if triage and triage.get("ce3_qualified") and triage.get("matched_prior_orders"):
        story.append(Paragraph("Visa CE 3.0 Qualifying Prior Undisputed Transactions", h2_style))
        ce3_data = [["Prior Order ID", "Date", "Days Prior", "Matched Core Elements"]]
        for po in triage["matched_prior_orders"][:4]:
            ce3_data.append(
                [
                    str(po.get("order_id", "")),
                    str(po.get("transaction_date", "")),
                    str(po.get("days_prior", "")),
                    ", ".join(po.get("matched_elements", [])),
                ]
            )
        ce3_table = Table(ce3_data, colWidths=[1.5 * inch, 1.2 * inch, 1.0 * inch, 3.5 * inch])
        ce3_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F5132")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(ce3_table)

    # Section 3: Chronological Timeline
    timeline = packet.get("timeline", [])
    if timeline:
        story.append(Paragraph("Chronological Timeline", h2_style))
        t_data = [["Date", "Event", "Exhibit Ref"]]
        for item in timeline:
            ev_clean, found_t = sanitize_neutral(item.get("event", ""))
            redacted_terms.extend(found_t)
            t_data.append(
                [
                    Paragraph(str(item.get("date", "")), cell_style),
                    Paragraph(ev_clean, cell_style),
                    Paragraph(str(item.get("exhibit_ref", "")), cell_style),
                ]
            )
        t_table = Table(t_data, colWidths=[1.1 * inch, 5.1 * inch, 1.0 * inch])
        t_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t_table)

    # Section 4: Indexed Exhibits (A through E)
    exhibits = packet.get("exhibits", [])[:5]
    if exhibits:
        story.append(Paragraph("Indexed Exhibits", h2_style))
        for ex in exhibits:
            label = str(ex.get("label", "Exhibit"))
            title = str(ex.get("title", ""))
            ex_type = str(ex.get("type", "text")).lower()
            story.append(Paragraph(f"<b>{label}: {title}</b>", body_style))

            if ex_type == "image":
                img_path = Path(str(ex.get("path", "")))
                if img_path.is_file():
                    buf, w_px, h_px = compress_image_to_buffer(img_path, img_max_dim, jpeg_quality)
                    max_w_pt = 6.5 * inch
                    max_h_pt = 3.2 * inch
                    scale = min(max_w_pt / max(w_px, 1), max_h_pt / max(h_px, 1))
                    story.append(RLImage(buf, width=w_px * scale, height=h_px * scale))
                    story.append(Spacer(1, 4))
                else:
                    story.append(Paragraph(f"[Image file not found: {img_path.name}]", body_style))
            elif ex_type == "pdf":
                src_pdf = Path(str(ex.get("path", "")))
                if src_pdf.is_file():
                    from pypdf import PdfReader

                    reader = PdfReader(str(src_pdf))
                    extracted_parts = []
                    for idx, page in enumerate(reader.pages[:2]):
                        txt = (page.extract_text() or "").strip()
                        if txt:
                            extracted_parts.append(f"[Page {idx + 1}] {txt[:600]}")
                    joined = " ".join(extracted_parts) or f"Attached PDF source: {src_pdf.name} ({len(reader.pages)} page(s))."
                    clean_pdf_txt, found_p = sanitize_neutral(joined)
                    redacted_terms.extend(found_p)
                    story.append(Paragraph(clean_pdf_txt, body_style))
                else:
                    story.append(Paragraph(f"[PDF file not found: {src_pdf.name}]", body_style))
            else:
                clean_txt, found_e = sanitize_neutral(str(ex.get("content", "")))
                redacted_terms.extend(found_e)
                story.append(Paragraph(clean_txt, body_style))

    doc.build(story)
    return sorted(set(redacted_terms))


def count_pdf_pages(pdf_path: Path) -> int:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="compile_packet_pdf.py",
        description="Compile a neutral, indexed chargeback representment PDF (<5 pages, <4.5 MB) and Markdown summary.",
        epilog="Exit codes: 0 = compiled within limits, 1 = exceeded limits, 2 = invalid input or missing dependency.",
    )
    parser.add_argument("--packet-json", required=True, help="Path to structured packet JSON")
    parser.add_argument("--output-dir", required=True, help="Directory for output PDF and summary Markdown")
    parser.add_argument("--triage-json", help="Optional path to ce3_and_triage_report.json")
    parser.add_argument("--max-mb", type=float, default=4.5, help="Maximum PDF file size in MB (default: 4.5)")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum PDF page count (default: 5)")
    args = parser.parse_args()

    try:
        import PIL  # noqa: F401
        import pypdf  # noqa: F401
        import reportlab  # noqa: F401
    except ImportError as exc:
        print(json.dumps({"error": f"Missing required dependency: {exc}"}, indent=2), file=sys.stderr)
        return 2

    try:
        packet_path = Path(args.packet_json)
        if not packet_path.is_file():
            raise FileNotFoundError(f"Packet JSON not found: {packet_path}")
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        triage = None
        if args.triage_json:
            triage_path = Path(args.triage_json)
            if triage_path.is_file():
                triage = json.loads(triage_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    order_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(packet.get("order_id", "unknown")))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / f"dispute_{order_id}_summary.md"
    summary_path.write_text(build_summary_markdown(packet, triage), encoding="utf-8")

    pdf_path = out_dir / f"dispute_{order_id}_representment.pdf"
    max_bytes = int(args.max_mb * 1024 * 1024)

    # Iteratively compress embedded images if needed to stay under max_mb while preserving legibility.
    compression_profiles = [(1400, 82), (1100, 72), (900, 62), (720, 52)]
    redacted_terms: list[str] = []
    size_bytes = 0
    used_profile = compression_profiles[0]

    for max_dim, quality in compression_profiles:
        used_profile = (max_dim, quality)
        redacted_terms = render_pdf(packet, triage, pdf_path, img_max_dim=max_dim, jpeg_quality=quality)
        size_bytes = pdf_path.stat().st_size
        if size_bytes <= max_bytes:
            break

    page_count = count_pdf_pages(pdf_path)
    size_mb = round(size_bytes / (1024 * 1024), 4)
    within_limits = (size_bytes <= max_bytes) and (page_count <= args.max_pages)

    result = {
        "order_id": order_id,
        "pdf_path": str(pdf_path),
        "summary_md_path": str(summary_path),
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "max_mb": args.max_mb,
        "page_count": page_count,
        "max_pages": args.max_pages,
        "compression_profile": {"max_dim_px": used_profile[0], "jpeg_quality": used_profile[1]},
        "redacted_emotional_terms": redacted_terms,
        "within_limits": within_limits,
    }
    print(json.dumps(result, indent=2))
    return 0 if within_limits else 1


if __name__ == "__main__":
    sys.exit(main())
