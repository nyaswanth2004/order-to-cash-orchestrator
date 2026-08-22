"""Order Validation Agent: verifies required fields, customer, product, quantity."""
from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel

from agents.base import SpecialistAgent, OrderContext
from models.schemas import ValidationOutput
from services.audit_service import AuditService
from services.data_store import DataStore

logger = logging.getLogger(__name__)


class ValidationAgent(SpecialistAgent):
    name: ClassVar[str] = "Validation Agent"

    def __init__(self, store: DataStore, audit: AuditService) -> None:
        self._store = store
        self._audit = audit

    def execute(self, ctx: OrderContext) -> ValidationOutput:
        request = ctx.request
        failed_checks: list[str] = []

        if not request.customer_name.strip():
            failed_checks.append("Customer name is missing")
        if not request.product_name.strip():
            failed_checks.append("Product name is missing")
        if request.quantity <= 0:
            failed_checks.append(f"Quantity must be greater than zero (got {request.quantity})")

        customer = None
        product = None
        if request.customer_name.strip():
            customer = self._store.find_customer(request.customer_name)
            if customer is None:
                failed_checks.append(f"Unknown customer '{request.customer_name.strip()}'")
        if request.product_name.strip():
            product = self._store.find_product(request.product_name)
            if product is None:
                failed_checks.append(f"Unknown product '{request.product_name.strip()}'")

        checks_performed = [
            "required fields present",
            "customer exists",
            "product exists",
            "quantity > 0",
        ]
        passed = not failed_checks
        reason = "All validation checks passed" if passed else "; ".join(failed_checks)

        output = ValidationOutput(
            passed=passed,
            reason=reason,
            checks_performed=checks_performed,
            failed_checks=failed_checks,
            customer_id=customer.customer_id if customer else None,
            product_sku=product.sku if product else None,
        )

        status = "Passed" if passed else "Failed"
        self._audit.log(ctx.order_id, self.name, "order.validate", status, reason)
        logger.info("[%s] order=%s %s", self.name, ctx.order_id, reason)

        if passed:
            ctx.customer = customer
            ctx.product = product
        ctx.validation = output
        return output
