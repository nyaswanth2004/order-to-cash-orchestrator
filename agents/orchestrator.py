"""Orchestrator Agent: delegates to specialists, routes the workflow, decides."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from agents.base import OrderContext, SpecialistAgent
from agents.inventory_agent import InventoryVerificationAgent
from agents.invoice_agent import InvoiceGenerationAgent
from agents.risk_agent import RiskAssessmentAgent
from agents.validation_agent import ValidationAgent
from models.schemas import (
    AgentTrace,
    AuditEntry,
    HandoffStep,
    InventoryOutput,
    Invoice,
    OrderRequest,
    OrderStatus,
    OrchestrationResult,
    RiskLevel,
    RiskOutput,
    ValidationOutput,
)
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    name = "Orchestrator Agent"

    def __init__(
        self,
        validation_agent: ValidationAgent,
        inventory_agent: InventoryVerificationAgent,
        risk_agent: RiskAssessmentAgent,
        invoice_agent: InvoiceGenerationAgent,
        audit: AuditService,
    ) -> None:
        self._validation_agent = validation_agent
        self._inventory_agent = inventory_agent
        self._risk_agent = risk_agent
        self._invoice_agent = invoice_agent
        self._audit = audit

    def process_order(self, request: OrderRequest) -> OrchestrationResult:
        order_id = f"ORD-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        ctx = OrderContext(order_id=order_id, request=request)
        handoffs: list[HandoffStep] = []
        traces: list[AgentTrace] = []

        self._audit.log(
            order_id,
            self.name,
            "order.received",
            "Info",
            f"Order received: {request.quantity} x '{request.product_name}' "
            f"for customer '{request.customer_name}'",
        )

        validation = self._delegate(self._validation_agent, "validate order", ctx, handoffs, traces)
        if validation is None:
            return self._finalize(
                ctx,
                OrderStatus.FAILED,
                "Workflow aborted: Validation Agent crashed",
                ["Validation Agent raised an unexpected error; no decision could be produced."],
                handoffs,
                traces,
            )
        if not validation.passed:
            return self._finalize(
                ctx,
                OrderStatus.REJECTED,
                f"Rejected at validation: {validation.reason}",
                [
                    f"Validation failed: {validation.reason}.",
                    "Workflow halted before inventory, risk, and invoicing steps.",
                ],
                handoffs,
                traces,
            )

        inventory = self._delegate(self._inventory_agent, "verify stock", ctx, handoffs, traces)
        if inventory is None:
            return self._finalize(
                ctx,
                OrderStatus.FAILED,
                "Workflow aborted: Inventory Agent crashed",
                ["Inventory Agent raised an unexpected error."],
                handoffs,
                traces,
            )
        if inventory.escalated:
            return self._finalize(
                ctx,
                OrderStatus.ESCALATED,
                f"Escalated due to stock shortage ({inventory.shortage_quantity} units short)",
                [
                    "Validation successful.",
                    f"Inventory shortage: requested {inventory.requested_quantity}, "
                    f"available {inventory.available_quantity} "
                    f"(short {inventory.shortage_quantity}).",
                    "Order escalated to procurement for a restocking/backorder decision.",
                ],
                handoffs,
                traces,
            )

        risk = self._delegate(self._risk_agent, "assess payment risk", ctx, handoffs, traces)
        if risk is None:
            return self._finalize(
                ctx,
                OrderStatus.FAILED,
                "Workflow aborted: Risk Agent crashed",
                ["Risk Agent raised an unexpected error."],
                handoffs,
                traces,
            )
        if risk.level == RiskLevel.HIGH:
            return self._finalize(
                ctx,
                OrderStatus.MANUAL_REVIEW,
                f"Manual review required: {risk.explanation}",
                [
                    "Validation successful.",
                    "Inventory available.",
                    f"Risk unacceptable for auto-approval: {risk.level.value} "
                    f"(confidence {risk.confidence:.0%}). {risk.explanation}",
                    "Routed to a human reviewer instead of auto-generating an invoice.",
                ],
                handoffs,
                traces,
            )

        invoice = self._delegate(self._invoice_agent, "generate invoice", ctx, handoffs, traces)
        if invoice is None:
            return self._finalize(
                ctx,
                OrderStatus.FAILED,
                "Workflow aborted: Invoice Agent crashed",
                ["Invoice Agent raised an unexpected error."],
                handoffs,
                traces,
            )

        explanation = [
            "Validation successful.",
            f"Inventory available ({inventory.available_quantity} on hand).",
            f"Risk acceptable: {risk.level.value} (confidence {risk.confidence:.0%}).",
            f"Invoice generated: {invoice.invoice_id}, grand total "
            f"${invoice.grand_total_usd:,.2f}.",
        ]
        note = (
            " Approved with standard payment monitoring."
            if risk.level == RiskLevel.MEDIUM
            else ""
        )
        return self._finalize(
            ctx,
            OrderStatus.APPROVED,
            f"Approved: invoice {invoice.invoice_id}.{note}",
            explanation,
            handoffs,
            traces,
        )

    def _delegate(
        self,
        agent: SpecialistAgent,
        action: str,
        ctx: OrderContext,
        handoffs: list[HandoffStep],
        traces: list[AgentTrace],
    ) -> Optional[BaseModel]:
        handoffs.append(
            HandoffStep(
                sequence=len(handoffs) + 1,
                from_agent=self.name,
                to_agent=agent.name,
                action=action,
            )
        )
        self._audit.log(
            ctx.order_id,
            agent.name,
            f"{action}.started",
            "Info",
            f"{self.name} handed control to {agent.name}",
        )
        try:
            output = agent.execute(ctx)
        except Exception as exc:
            logger.exception("[%s] %s failed for order %s", self.name, agent.name, ctx.order_id)
            message = f"{agent.name} raised {type(exc).__name__}: {exc}"
            self._audit.log(ctx.order_id, self.name, f"{action}.failed", "Error", message)
            traces.append(AgentTrace(agent=agent.name, status="Failed", summary=message))
            return None
        summary = self._summarize(output)
        self._audit.log(
            ctx.order_id,
            agent.name,
            f"{action}.completed",
            "Completed",
            summary,
        )
        traces.append(
            AgentTrace(
                agent=agent.name,
                status="Completed",
                summary=summary,
                output=json.loads(output.model_dump_json()),
            )
        )
        return output

    @staticmethod
    def _summarize(output: BaseModel) -> str:
        if isinstance(output, ValidationOutput):
            return output.reason
        if isinstance(output, InventoryOutput):
            return output.message
        if isinstance(output, RiskOutput):
            return output.explanation
        if isinstance(output, Invoice):
            return (
                f"Invoice {output.invoice_id} issued to {output.customer_name}; "
                f"grand total ${output.grand_total_usd:,.2f}"
            )
        return output.model_dump_json()

    def _finalize(
        self,
        ctx: OrderContext,
        status: OrderStatus,
        decision_reason: str,
        explanation: list[str],
        handoffs: list[HandoffStep],
        traces: list[AgentTrace],
    ) -> OrchestrationResult:
        handoffs.append(
            HandoffStep(
                sequence=len(handoffs) + 1,
                from_agent=self.name,
                to_agent=status.value,
                action="final decision",
            )
        )
        self._audit.log(
            ctx.order_id,
            self.name,
            "decision.finalized",
            status.value,
            decision_reason,
        )
        result = OrchestrationResult(
            order_id=ctx.order_id,
            status=status,
            decision_reason=decision_reason,
            explanation=explanation,
            handoffs=handoffs,
            agent_traces=traces,
            audit_trail=self._audit.get_entries(ctx.order_id),
            invoice=ctx.invoice,
            created_at_utc=datetime.now(timezone.utc),
        )
        self._audit.persist_order(result)
        logger.info("[%s] order=%s final status=%s", self.name, ctx.order_id, status.value)
        return result
