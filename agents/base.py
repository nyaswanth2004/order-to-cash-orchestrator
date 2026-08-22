"""Shared agent plumbing: execution context and specialist-agent contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Optional

from pydantic import BaseModel

from models.schemas import (
    Customer,
    InventoryOutput,
    Invoice,
    OrderRequest,
    Product,
    RiskOutput,
    ValidationOutput,
)


class AgentExecutionError(RuntimeError):
    """Raised when an agent cannot run because its preconditions are unmet."""


@dataclass
class OrderContext:
    """State that flows through the pipeline as agents enrich it."""

    order_id: str
    request: OrderRequest
    customer: Optional[Customer] = None
    product: Optional[Product] = None
    validation: Optional[ValidationOutput] = None
    inventory: Optional[InventoryOutput] = None
    risk: Optional[RiskOutput] = None
    invoice: Optional[Invoice] = None

    @property
    def order_value_usd(self) -> float:
        if self.product is None:
            return 0.0
        return round(self.product.unit_price_usd * self.request.quantity, 2)


class SpecialistAgent(ABC):
    """Contract every specialist agent fulfils for the orchestrator."""

    name: ClassVar[str] = "Specialist Agent"

    @abstractmethod
    def execute(self, ctx: OrderContext) -> BaseModel:
        """Perform this agent's single responsibility and return its output."""
        raise NotImplementedError
