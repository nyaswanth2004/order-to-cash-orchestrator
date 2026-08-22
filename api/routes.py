"""FastAPI routes exposing the orchestrator and reference data."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from agents.inventory_agent import InventoryVerificationAgent
from agents.invoice_agent import InvoiceGenerationAgent
from agents.orchestrator import OrchestratorAgent
from agents.risk_agent import RiskAssessmentAgent
from agents.validation_agent import ValidationAgent
from models.schemas import OrderRequest, OrchestrationResult
from services.audit_service import AuditService
from services.data_store import DataStore
from services.pdf_service import InvoicePdfError, InvoicePdfService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = PROJECT_ROOT / "data" / "storage"
INVOICE_PDF_DIR = PROJECT_ROOT / "generated_invoices"

audit_service = AuditService(STORAGE_DIR)
data_store = DataStore(DATA_DIR)
pdf_service = InvoicePdfService(INVOICE_PDF_DIR)

orchestrator = OrchestratorAgent(
    validation_agent=ValidationAgent(data_store, audit_service),
    inventory_agent=InventoryVerificationAgent(audit_service),
    risk_agent=RiskAssessmentAgent(audit_service),
    invoice_agent=InvoiceGenerationAgent(audit_service),
    audit=audit_service,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "order-to-cash-orchestrator", "version": "1.0.0"}


@router.post("/orders/process", response_model=OrchestrationResult)
def process_order(request: OrderRequest) -> OrchestrationResult:
    try:
        return orchestrator.process_order(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Orchestration failure: {exc}") from exc


@router.get("/inventory")
def get_inventory() -> dict[str, list]:
    return {"products": [product.model_dump() for product in data_store.products]}


@router.get("/customers")
def get_customers() -> dict[str, list]:
    return {"customers": [customer.model_dump() for customer in data_store.customers]}


@router.get("/audit/{order_id}", response_model=OrchestrationResult)
def get_audit(order_id: str) -> OrchestrationResult:
    record = audit_service.get_order(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No order found with id '{order_id}'")
    return record


@router.get("/orders/{order_id}/invoice.pdf")
def download_invoice_pdf(order_id: str) -> FileResponse:
    record = audit_service.get_order(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No order found with id '{order_id}'")
    if record.invoice is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Order {order_id} has no invoice: workflow finished with status "
                f"'{record.status.value}' before invoicing"
            ),
        )
    risk_trace = next(
        (trace for trace in record.agent_traces if trace.agent == "Risk Agent"),
        None,
    )
    risk_level = (risk_trace.output.get("level") if risk_trace else None) or "N/A"
    try:
        pdf_path = pdf_service.generate(
            record.invoice,
            risk_level=str(risk_level),
            order_status=record.status.value,
        )
    except InvoicePdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )
