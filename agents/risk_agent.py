"""Risk Assessment Agent: deterministic business rules with explainable output."""
from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel

from agents.base import AgentExecutionError, SpecialistAgent, OrderContext
from models.schemas import RiskLevel, RiskOutput
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

HIGH_VALUE_ORDER_USD = 10_000.0
LATE_PAYMENTS_HIGH_RISK = 2


class RiskAssessmentAgent(SpecialistAgent):
    name: ClassVar[str] = "Risk Agent"

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    def execute(self, ctx: OrderContext) -> RiskOutput:
        if ctx.customer is None or ctx.product is None:
            raise AgentExecutionError("Risk assessment requires a validated customer and product")

        customer = ctx.customer
        order_value = ctx.order_value_usd
        factors: list[str] = []
        level = RiskLevel.LOW

        if customer.segment == "new":
            factors.append(
                f"New customer ({customer.customer_id}) has no payment history yet"
            )
            level = RiskLevel.MEDIUM

        if customer.late_payments_12m >= LATE_PAYMENTS_HIGH_RISK:
            factors.append(
                f"{customer.late_payments_12m} late payments in the last 12 months"
            )
            level = RiskLevel.HIGH
        elif customer.late_payments_12m == 1:
            factors.append("1 late payment in the last 12 months")
            if level == RiskLevel.LOW:
                level = RiskLevel.MEDIUM

        if order_value >= HIGH_VALUE_ORDER_USD:
            factors.append(
                f"High-value order (${order_value:,.2f} >= ${HIGH_VALUE_ORDER_USD:,.2f})"
            )
            level = RiskLevel.HIGH

        if not factors:
            factors.append(
                f"Established customer ({customer.years_active} yrs) with clean payment history"
            )
            factors.append(f"Order value ${order_value:,.2f} below high-value threshold")

        confidence = round(min(0.60 + 0.10 * len(factors), 0.95), 2)
        explanation = (
            f"{level.value} risk because: " + "; ".join(factors) + "."
        )

        output = RiskOutput(
            level=level,
            confidence=confidence,
            factors=factors,
            explanation=explanation,
        )

        self._audit.log(
            ctx.order_id,
            self.name,
            "risk.assess",
            "Completed",
            explanation,
        )
        logger.info("[%s] order=%s %s", self.name, ctx.order_id, explanation)

        ctx.risk = output
        return output
