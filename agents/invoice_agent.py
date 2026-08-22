"""Invoice Generation Agent: builds the structured invoice for the order."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel

from agents.base import AgentExecutionError, SpecialistAgent, OrderContext
from models.schemas import Invoice, InvoiceLineItem
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

TAX_RATE = 0.18


class InvoiceGenerationAgent(SpecialistAgent):
    name: ClassVar[str] = "Invoice Agent"

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    def execute(self, ctx: OrderContext) -> Invoice:
        if ctx.customer is None or ctx.product is None:
            raise AgentExecutionError("Invoice generation requires a validated customer and product")

        quantity = ctx.request.quantity
        unit_price = ctx.product.unit_price_usd
        subtotal = round(unit_price * quantity, 2)
        tax_amount = round(subtotal * TAX_RATE, 2)
        grand_total = round(subtotal + tax_amount, 2)
        issued_at = datetime.now(timezone.utc)

        invoice = Invoice(
            invoice_id=f"INV-{issued_at:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}",
            order_id=ctx.order_id,
            customer_id=ctx.customer.customer_id,
            customer_name=ctx.customer.name,
            line_items=[
                InvoiceLineItem(
                    sku=ctx.product.sku,
                    description=ctx.product.name,
                    quantity=quantity,
                    unit_price_usd=unit_price,
                    line_total_usd=subtotal,
                )
            ],
            subtotal_usd=subtotal,
            tax_rate=TAX_RATE,
            tax_amount_usd=tax_amount,
            grand_total_usd=grand_total,
            issued_at_utc=issued_at,
        )

        message = (
            f"Invoice {invoice.invoice_id} generated: subtotal ${subtotal:,.2f}, "
            f"tax (18%) ${tax_amount:,.2f}, grand total ${grand_total:,.2f}"
        )
        self._audit.log(ctx.order_id, self.name, "invoice.generate", "Completed", message)
        logger.info("[%s] order=%s %s", self.name, ctx.order_id, message)

        ctx.invoice = invoice
        return invoice
