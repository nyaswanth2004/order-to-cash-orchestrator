"""Pydantic contracts shared across agents, API routes, storage, and the UI."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    APPROVED = "Approved"
    REJECTED = "Rejected"
    ESCALATED = "Escalated"
    MANUAL_REVIEW = "Manual Review Required"
    FAILED = "Failed"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Customer(BaseModel):
    customer_id: str
    name: str
    segment: str
    years_active: int
    late_payments_12m: int
    lifetime_value_usd: float


class Product(BaseModel):
    sku: str
    name: str
    unit_price_usd: float
    stock_quantity: int


class OrderRequest(BaseModel):
    """Raw order as submitted. Deliberately unconstrained so that business
    rules (e.g. quantity > 0) are enforced by the Validation Agent, not by
    request parsing."""

    customer_name: str
    product_name: str
    quantity: int


class ValidationOutput(BaseModel):
    passed: bool
    reason: str
    checks_performed: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    customer_id: Optional[str] = None
    product_sku: Optional[str] = None


class InventoryOutput(BaseModel):
    available: bool
    escalated: bool
    requested_quantity: int
    available_quantity: int
    shortage_quantity: int
    message: str


class RiskOutput(BaseModel):
    level: RiskLevel
    confidence: float
    factors: list[str]
    explanation: str


class InvoiceLineItem(BaseModel):
    sku: str
    description: str
    quantity: int
    unit_price_usd: float
    line_total_usd: float


class Invoice(BaseModel):
    invoice_id: str
    order_id: str
    customer_id: str
    customer_name: str
    line_items: list[InvoiceLineItem]
    subtotal_usd: float
    tax_rate: float
    tax_amount_usd: float
    grand_total_usd: float
    issued_at_utc: datetime


class HandoffStep(BaseModel):
    sequence: int
    from_agent: str
    to_agent: str
    action: str


class AuditEntry(BaseModel):
    timestamp_utc: datetime
    order_id: str
    agent: str
    action: str
    status: str
    message: str


class AgentTrace(BaseModel):
    agent: str
    status: str
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)


class OrchestrationResult(BaseModel):
    order_id: str
    status: OrderStatus
    decision_reason: str
    explanation: list[str]
    handoffs: list[HandoffStep]
    agent_traces: list[AgentTrace]
    audit_trail: list[AuditEntry]
    invoice: Optional[Invoice] = None
    created_at_utc: datetime
