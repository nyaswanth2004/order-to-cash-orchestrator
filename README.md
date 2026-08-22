# AI-Powered Multi-Agent Order-to-Cash Orchestrator

A multi-agent system that processes a sales order end to end. An **Orchestrator Agent** receives the order and delegates work to four specialist agents — **Validation**, **Inventory**, **Risk**, and **Invoice** — routing the workflow, handling exceptions, tracking every handoff, and maintaining a full audit trail.

Built for a Forward Deployed Engineer technical assessment: FastAPI backend, Streamlit dashboard, JSON storage, zero external AI dependencies (deterministic, explainable business rules).

---

## Project Overview

| Layer | Technology | Role |
|---|---|---|
| API | FastAPI + Pydantic v2 | Exposes orchestration, reference data, and audit endpoints |
| Agents | Python classes | Orchestrator + 4 specialists with strictly separated responsibilities |
| Storage | JSON files | Reference data (`data/`), per-order records + global audit log (`data/storage/`), generated invoice PDFs (`generated_invoices/`) |
| UI | Streamlit | Order form, live workflow status, agent outputs, invoice view, audit trail |

The orchestrator contains **no specialist logic** — it only delegates, collects results, routes the workflow based on agent-reported statuses, and produces the final decision.

## Architecture Diagram

```
                        ┌──────────────────────────────┐
                        │      Streamlit Dashboard     │
                        │  frontend/app.py  (:8501)    │
                        └──────────────┬───────────────┘
                                       │ HTTP (REST)
                        ┌──────────────▼───────────────┐
                        │        FastAPI App           │
                        │  main.py → api/routes.py     │
                        │  GET /health                 │
                        │  POST /orders/process        │
                        │  GET /inventory /customers   │
                        │  GET /audit/{order_id}       │
                        │  GET /orders/{id}/invoice.pdf│
                        └──────────────┬───────────────┘
                                       │
              ┌────────────────────────▼────────────────────────┐
              │             ORCHESTRATOR AGENT                  │
              │  delegate → collect → route → decide → audit    │
              └───┬───────────┬───────────────┬───────────┬─────┘
                  ▼           ▼               ▼           ▼
           ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
           │Validation │ │ Inventory │ │   Risk    │ │ Invoice   │
           │   Agent   │ │   Agent   │ │   Agent   │ │   Agent   │
           └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
                  │             │             │             │
                  └─────────────┴──────┬──────┴─────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
                    │  Shared services                     │
                    │  • DataStore      (customers.json,   │
                    │                    inventory.json)   │
                    │  • AuditService   (audit_log.json,   │
                    │                    orders/*.json)    │
                    └──────────────────────────────────────┘
```

## Agent Responsibilities

| Agent | Single responsibility | Output |
|---|---|---|
| **Orchestrator** (`agents/orchestrator.py`) | Receives order, delegates in sequence, halts on failure, generates final decision + explanation | `OrchestrationResult` |
| **Validation Agent** (`validation_agent.py`) | Required fields present · customer exists · product exists · quantity > 0 | `ValidationOutput` (passed/reason) |
| **Inventory Verification Agent** (`inventory_agent.py`) | Compares requested qty vs stock; flags shortage for escalation | `InventoryOutput` (available/shortage/escalated) |
| **Risk Assessment Agent** (`risk_agent.py`) | Deterministic rules: new customer → Medium; ≥2 late payments or order ≥ $10,000 → High; clean returning customer → Low. Confidence score grows with number of contributing factors | `RiskOutput` (level/confidence/factors/explanation) |
| **Invoice Generation Agent** (`invoice_agent.py`) | Invoice ID, line item, subtotal, **18% tax**, grand total | `Invoice` |

Specialists share state through an immutable-in-spirit `OrderContext` dataclass; each agent enriches it and returns its own typed Pydantic output. Every agent writes its own audit entries via the injected `AuditService`.

## Workflow Explanation

```
Order Received
      ↓
Validation Agent ──── fail ──→ REJECTED            (e.g. quantity = -5, unknown product)
      ↓ pass
Inventory Agent ────── shortage ──→ ESCALATED      (e.g. request 80, stock 50)
      ↓ available
Risk Agent ─────────── HIGH ──→ MANUAL REVIEW      (e.g. Cortex Labs: 3 late payments)
      ↓ Low/Medium
Invoice Agent ──────── invoice issued ──→ APPROVED (Medium adds "payment monitoring" note)
```

- The pipeline **short-circuits**: once an agent reports a blocking condition, downstream agents are never invoked and the reason is recorded.
- Any unexpected agent exception is caught by the orchestrator → status `Failed`, logged as `Error` in the audit trail.
- Every delegation is recorded twice: as a **handoff step** (for the UI chain) and as **audit entries** (`*.started` / `*.completed`).

## Exception Handling

| Case | Example input | Result |
|---|---|---|
| 1. Insufficient inventory | Delta Foods · Industrial Drone X200 · qty 80 (stock 50) | **Escalated** (30 units short) |
| 2. Invalid quantity | Acme Manufacturing · Vision Sensor Pro · qty −5 | **Rejected** at validation |
| 3. Unknown product | Brightline Retail Group · "Teleportation Beam" | **Rejected** at validation |
| 4. High-risk customer | Cortex Labs (3 late payments) · Robotic Arm RA-7 | **Manual Review Required** |

Note: `OrderRequest.quantity` is deliberately *unconstrained* at the HTTP layer so that business rules like `quantity > 0` are enforced by the Validation Agent, not by request parsing — this keeps validation where it belongs and makes Case 2 demonstrable.

## Invoice Download Feature

Approved orders can be downloaded as a professional PDF invoice directly from the dashboard.

- **UI:** Streamlit → *Invoice View* section → **📄 Download Invoice** button (rendered only when an invoice exists). On success it confirms with *"Invoice downloaded successfully"*; on failure it shows a descriptive warning instead of the button.
- **Reusable service:** `services/pdf_service.py` exposes `InvoicePdfService`, a framework-agnostic ReportLab generator. It validates input (raises `InvoicePdfError` when invoice data is missing/invalid), is idempotent per invoice ID, and is usable by any client — API, UI, or batch jobs.
- **API:** `GET /orders/{order_id}/invoice.pdf` generates (or reuses) the PDF and streams it back as an `application/pdf` attachment named after the invoice file.
- **Storage & naming:** PDFs are written to `generated_invoices/` as `INV-<invoice_id>.pdf`, e.g. `INV-20260821-3E18AA.pdf`.
- **PDF contents:** Demo Company header · Invoice ID · Invoice Date · Customer Name · Product Name · Quantity · Unit Price · Subtotal · Tax (18%) · Grand Total · Risk Level · Order Status.
- **Error handling:** missing order → 404 (`No order found…`); order without invoice → 404 explaining the workflow halted at its actual status; unwritable output → 500; invalid invoice data → 422.

## PDF Generation Workflow

```
Order Submitted
      ↓
Validation Agent
      ↓
Inventory Agent
      ↓
Risk Agent
      ↓
Invoice Agent
      ↓
Invoice Generated  ──►  stored on the order record (data/storage/orders/*.json)
      ↓
User clicks "📄 Download Invoice" in the dashboard
      ↓
GET /orders/{order_id}/invoice.pdf
      ↓
InvoicePdfService.generate()   (skipped if the PDF already exists)
      ↓
generated_invoices/INV-<invoice_id>.pdf
      ↓
Browser download + "Invoice downloaded successfully"
```

## Folder Structure

```
order_to_cash_orchestrator/
├── agents/
│   ├── base.py               # SpecialistAgent contract + OrderContext
│   ├── orchestrator.py       # Orchestrator Agent (routing, decisions)
│   ├── validation_agent.py
│   ├── inventory_agent.py
│   ├── risk_agent.py
│   └── invoice_agent.py
├── models/
│   └── schemas.py            # All Pydantic models/enums
├── services/
│   ├── data_store.py         # customers/inventory JSON access
│   ├── audit_service.py      # Audit trail + per-order persistence
│   └── pdf_service.py        # ReportLab invoice PDF generation
├── api/
│   └── routes.py             # FastAPI endpoints (composition root)
├── frontend/
│   └── app.py                # Streamlit dashboard
├── scripts/
│   └── demo_scenarios.py     # Runs success case + all 4 exception cases
├── data/
│   ├── customers.json        # 5 customers, different risk profiles
│   ├── inventory.json        # 5 products
│   └── storage/              # generated: audit_log.json, orders/*.json
├── generated_invoices/       # generated: INV-*.pdf files
├── main.py                   # `python main.py`
├── requirements.txt
└── README.md
```

## Assumptions

1. **Inventory is not decremented** after approval — checks are read-only so demos are repeatable. A production system would reserve stock transactionally.
2. Risk rules are deterministic business rules (no LLM calls), chosen so every decision is explainable and reproducible.
3. High-value threshold is **$10,000 subtotal**; tax is flat **18%**.
4. Medium-risk orders are auto-approved with a monitoring note; only High risk forces manual review.
5. One product per order; prices in USD.
6. JSON storage is adequate for demo scale; the `AuditService` isolates persistence behind an interface so swapping to a database touches one class.

## Setup Instructions

Requires **Python 3.11+**.

```bat
:: 1. Install dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

:: 2. Start the API (terminal 1)
.venv\Scripts\python main.py

:: 3. Start the dashboard (terminal 2)
.venv\Scripts\streamlit run frontend/app.py
```

Open the dashboard at http://localhost:8501 and the interactive API docs at http://127.0.0.1:8000/docs.

To verify everything headlessly (API must be running):

```bat
.venv\Scripts\python scripts\demo_scenarios.py
```

## Sample Inputs

```json
// Approved (Low risk)
{ "customer_name": "Acme Manufacturing", "product_name": "Vision Sensor Pro", "quantity": 10 }

// Escalated (shortage)
{ "customer_name": "Delta Foods", "product_name": "Industrial Drone X200", "quantity": 80 }

// Rejected (invalid quantity)
{ "customer_name": "Acme Manufacturing", "product_name": "Vision Sensor Pro", "quantity": -5 }

// Rejected (unknown product)
{ "customer_name": "Brightline Retail Group", "product_name": "Teleportation Beam", "quantity": 3 }

// Manual review (high risk)
{ "customer_name": "Cortex Labs", "product_name": "Robotic Arm RA-7", "quantity": 1 }
```

## Sample Outputs

Approved order (`POST /orders/process`, abbreviated):

```json
{
  "order_id": "ORD-20260821-2A06FD",
  "status": "Approved",
  "decision_reason": "Approved: invoice INV-20260821-3E18AA.",
  "explanation": [
    "Validation successful.",
    "Inventory available (400 on hand).",
    "Risk acceptable: Low (confidence 80%).",
    "Invoice generated: INV-20260821-3E18AA, grand total $8,850.00."
  ],
  "handoffs": [
    { "sequence": 1, "from_agent": "Orchestrator Agent", "to_agent": "Validation Agent", "action": "validate order" },
    { "sequence": 2, "from_agent": "Orchestrator Agent", "to_agent": "Inventory Agent", "action": "verify stock" },
    { "sequence": 3, "from_agent": "Orchestrator Agent", "to_agent": "Risk Agent", "action": "assess payment risk" },
    { "sequence": 4, "from_agent": "Orchestrator Agent", "to_agent": "Invoice Agent", "action": "generate invoice" },
    { "sequence": 5, "from_agent": "Orchestrator Agent", "to_agent": "Approved", "action": "final decision" }
  ],
  "invoice": {
    "invoice_id": "INV-20260821-3E18AA",
    "subtotal_usd": 7500.0,
    "tax_rate": 0.18,
    "tax_amount_usd": 1350.0,
    "grand_total_usd": 8850.0
  }
}
```

Escalated order:

```json
{
  "status": "Escalated",
  "decision_reason": "Escalated due to stock shortage (30 units short)",
  "explanation": [
    "Validation successful.",
    "Inventory shortage: requested 80, available 50 (short 30).",
    "Order escalated to procurement for a restocking/backorder decision."
  ]
}
```

## Design Tradeoff

**Deterministic rule-based agents instead of LLM-powered agents.**
An LLM inside each agent would look impressive but would make decisions non-reproducible, slow, costly, and hard to unit-test — unacceptable when the same order must always produce the same invoice and the same risk verdict. This project demonstrates the *architecture* assessors actually care about — genuine delegation, typed agent contracts, short-circuit routing, handoff tracking, auditability — while keeping each agent's brain swappable: because agents implement one `execute(ctx)` method behind a shared contract, replacing a rule engine with a model call later changes exactly one file per agent.

Other deliberate tradeoffs:
- **JSON files over a database** — zero-setup demo; isolated behind `DataStore`/`AuditService`.
- **Synchronous pipeline over a message bus** — a 4-step flow completes in milliseconds; queues would add ops burden without benefit at this scale.
- **Frontend talks to the API over HTTP only** — proves the UI consumes the same contract as any other client (no shared code shortcuts).
