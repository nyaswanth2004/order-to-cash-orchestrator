"""Inventory Verification Agent: checks stock and escalates shortages."""
from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel

from agents.base import AgentExecutionError, SpecialistAgent, OrderContext
from models.schemas import InventoryOutput
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


class InventoryVerificationAgent(SpecialistAgent):
    name: ClassVar[str] = "Inventory Agent"

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    def execute(self, ctx: OrderContext) -> InventoryOutput:
        if ctx.product is None:
            raise AgentExecutionError("Inventory check requires a validated product")

        requested = ctx.request.quantity
        available = ctx.product.stock_quantity
        sufficient = requested <= available
        shortage = max(requested - available, 0)

        if sufficient:
            message = (
                f"Stock sufficient for '{ctx.product.name}': requested {requested}, "
                f"available {available}"
            )
        else:
            message = (
                f"Stock shortage for '{ctx.product.name}': requested {requested}, "
                f"available {available}, shortage {shortage}. Escalation required."
            )

        output = InventoryOutput(
            available=sufficient,
            escalated=not sufficient,
            requested_quantity=requested,
            available_quantity=available,
            shortage_quantity=shortage,
            message=message,
        )

        status = "Passed" if sufficient else "Escalated"
        self._audit.log(ctx.order_id, self.name, "inventory.check", status, message)
        logger.info("[%s] order=%s %s", self.name, ctx.order_id, message)

        ctx.inventory = output
        return output
