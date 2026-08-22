"""Reusable ReportLab-based PDF invoice generation.

Kept free of web-framework dependencies so any client (API, UI, batch jobs)
can reuse it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from models.schemas import Invoice

logger = logging.getLogger(__name__)

COMPANY_NAME = "Demo Company"
COMPANY_TAGLINE = "AI-Powered Multi-Agent Order-to-Cash Orchestrator"
BRAND_COLOR = colors.HexColor("#1F3864")
LIGHT_ROW_COLOR = colors.HexColor("#EDF1F8")
BORDER_COLOR = colors.HexColor("#C9D2E3")


class InvoicePdfError(ValueError):
    """Raised when invoice data is missing or invalid and no PDF can be produced."""


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


class InvoicePdfService:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def invoice_path(self, invoice_id: str) -> Path:
        return self._output_dir / f"{invoice_id}.pdf"

    def generate(
        self,
        invoice: Optional[Invoice],
        *,
        risk_level: str = "N/A",
        order_status: str = "N/A",
    ) -> Path:
        """Render the invoice to PDF; idempotent per invoice ID."""
        self._validate(invoice)
        assert invoice is not None
        path = self.invoice_path(invoice.invoice_id)
        if path.exists():
            logger.info("Invoice PDF already generated, reusing %s", path)
            return path

        document = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            left_margin=18 * mm,
            right_margin=18 * mm,
            top_margin=16 * mm,
            bottom_margin=16 * mm,
            title=f"Invoice {invoice.invoice_id}",
            author=COMPANY_NAME,
        )
        try:
            document.build(self._build_story(invoice, risk_level, order_status))
        except OSError as exc:
            raise InvoicePdfError(f"Could not write PDF file {path}: {exc}") from exc
        logger.info("Generated invoice PDF %s", path)
        return path

    @staticmethod
    def _validate(invoice: Optional[Invoice]) -> None:
        if invoice is None:
            raise InvoicePdfError(
                "No invoice data available: the workflow did not reach the Invoice Agent"
            )
        if not invoice.invoice_id:
            raise InvoicePdfError("Invoice data is missing an invoice ID")
        if not invoice.line_items:
            raise InvoicePdfError(f"Invoice {invoice.invoice_id} has no line items")

    def _build_story(self, invoice: Invoice, risk_level: str, order_status: str) -> list:
        styles = getSampleStyleSheet()
        heading = ParagraphStyle(
            "BrandHeading",
            parent=styles["Title"],
            fontSize=22,
            textColor=BRAND_COLOR,
            alignment=TA_RIGHT,
            spaceAfter=0,
        )
        company = ParagraphStyle(
            "CompanyName",
            parent=styles["Title"],
            fontSize=20,
            textColor=BRAND_COLOR,
            alignment=0,
            spaceAfter=2,
        )
        tagline = ParagraphStyle(
            "Tagline",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#5A6478"),
        )
        label = ParagraphStyle(
            "MetaLabel",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#5A6478"),
        )
        value = ParagraphStyle(
            "MetaValue",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
        )

        story: list = []
        header = Table(
            [[Paragraph(COMPANY_NAME, company), Paragraph("INVOICE", heading)],
             [Paragraph(COMPANY_TAGLINE, tagline), ""]],
            colWidths=[110 * mm, 54 * mm],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        story += [
            header,
            Spacer(1, 4 * mm),
            HRFlowable(width="100%", thickness=1.2, color=BRAND_COLOR),
            Spacer(1, 6 * mm),
        ]

        issued = invoice.issued_at_utc.strftime("%d %b %Y, %H:%M UTC")
        meta_rows = [
            [Paragraph("Invoice ID", label), Paragraph(invoice.invoice_id, value),
             Paragraph("Customer", label), Paragraph(invoice.customer_name, value)],
            [Paragraph("Invoice Date", label), Paragraph(issued, value),
             Paragraph("Order ID", label), Paragraph(invoice.order_id, value)],
            [Paragraph("Order Status", label), Paragraph(order_status, value),
             Paragraph("Risk Level", label), Paragraph(risk_level, value)],
        ]
        meta = Table(meta_rows, colWidths=[28 * mm, 52 * mm, 28 * mm, 56 * mm])
        meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_ROW_COLOR),
            ("BOX", (0, 0), (-1, -1), 0.75, BORDER_COLOR),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story += [meta, Spacer(1, 8 * mm)]

        items_data = [["Product Name", "Quantity", "Unit Price", "Line Total"]]
        for item in invoice.line_items:
            items_data.append([
                item.description,
                str(item.quantity),
                _money(item.unit_price_usd),
                _money(item.line_total_usd),
            ])
        items = Table(items_data, colWidths=[76 * mm, 24 * mm, 32 * mm, 32 * mm])
        items.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_ROW_COLOR]),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story += [items, Spacer(1, 6 * mm)]

        totals_data = [
            ["Subtotal", _money(invoice.subtotal_usd)],
            [f"Tax ({invoice.tax_rate:.0%})", _money(invoice.tax_amount_usd)],
            ["Grand Total", _money(invoice.grand_total_usd)],
        ]
        totals = Table(totals_data, colWidths=[112 * mm, 32 * mm], hAlign="RIGHT")
        totals.setStyle(TableStyle([
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BACKGROUND", (0, 2), (-1, 2), LIGHT_ROW_COLOR),
            ("LINEABOVE", (0, 0), (-1, 0), 0.75, BORDER_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story += [totals, Spacer(1, 14 * mm)]

        footer = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#8A93A6"),
        )
        story.append(
            Paragraph(
                f"Generated by {COMPANY_NAME} · {COMPANY_TAGLINE}. "
                "This is a system-generated demo invoice.",
                footer,
            )
        )
        return story
