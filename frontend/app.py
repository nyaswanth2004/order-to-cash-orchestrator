"""Streamlit dashboard for the Order-to-Cash Orchestrator.

Run with:  streamlit run frontend/app.py
Requires the FastAPI backend:  python main.py
"""
from __future__ import annotations

import os
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT_SECONDS = 30

AGENT_ICONS = {
    "Orchestrator Agent": "Orchestrator",
    "Validation Agent": "Validation",
    "Inventory Agent": "Inventory",
    "Risk Agent": "Risk",
    "Invoice Agent": "Invoice",
}

STATUS_BANNERS = {
    "Approved": ("success", "Approved"),
    "Rejected": ("error", "Rejected"),
    "Escalated": ("warning", "Escalated"),
    "Manual Review Required": ("warning", "Manual Review Required"),
    "Failed": ("error", "Failed"),
}

SCENARIOS = {
    "Successful order (Approved)": {
        "customer": "Acme Manufacturing",
        "product_mode": "catalog",
        "product": "Vision Sensor Pro",
        "custom_product": "",
        "quantity": 10,
    },
    "Insufficient inventory (Escalated)": {
        "customer": "Delta Foods",
        "product_mode": "catalog",
        "product": "Industrial Drone X200",
        "custom_product": "",
        "quantity": 80,
    },
    "Invalid quantity (Rejected)": {
        "customer": "Acme Manufacturing",
        "product_mode": "catalog",
        "product": "Vision Sensor Pro",
        "custom_product": "",
        "quantity": -5,
    },
    "Unknown product (Rejected)": {
        "customer": "Brightline Retail Group",
        "product_mode": "custom",
        "product": "",
        "custom_product": "Teleportation Beam",
        "quantity": 3,
    },
    "High-risk customer (Manual Review)": {
        "customer": "Cortex Labs",
        "product_mode": "catalog",
        "product": "Robotic Arm RA-7",
        "custom_product": "",
        "quantity": 1,
    },
}

st.set_page_config(
    page_title="Order-to-Cash Orchestrator",
    page_icon="O2C",
    layout="wide",
)


def api_get(path: str) -> Optional[Any]:
    try:
        response = requests.get(f"{API_BASE}{path}", timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def check_health() -> bool:
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        return response.ok
    except requests.RequestException:
        return False


def submit_order(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        response = requests.post(
            f"{API_BASE}/orders/process",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        if not response.ok:
            st.error(f"API error {response.status_code}: {response.text}")
            return None
        return response.json()
    except requests.RequestException:
        st.error("Could not reach the backend. Please verify it is running.")
        return None


def render_invoice_download(order_id: str, invoice_id: str) -> None:
    bytes_key = f"pdf_bytes_{order_id}"
    error_key = f"pdf_error_{order_id}"
    if bytes_key not in st.session_state:
        try:
            response = requests.get(
                f"{API_BASE}/orders/{order_id}/invoice.pdf",
                timeout=TIMEOUT_SECONDS,
            )
            if response.ok and response.content[:4] == b"%PDF":
                st.session_state[bytes_key] = response.content
                st.session_state[error_key] = None
            else:
                st.session_state[bytes_key] = None
                try:
                    detail = response.json().get("detail", response.text)
                except ValueError:
                    detail = response.text
                st.session_state[error_key] = f"API error {response.status_code}: {detail}"
        except requests.RequestException as exc:
            st.session_state[bytes_key] = None
            st.session_state[error_key] = str(exc)

    pdf_bytes = st.session_state.get(bytes_key)
    pdf_error = st.session_state.get(error_key)
    if pdf_bytes is None:
        st.warning(f"Invoice PDF unavailable -- {pdf_error}")
        return
    if st.download_button(
        label="Download Invoice PDF",
        data=pdf_bytes,
        file_name=f"{invoice_id}.pdf",
        mime="application/pdf",
        use_container_width=True,
    ):
        st.success("Invoice downloaded successfully")


st.title("AI-Powered Multi-Agent Order-to-Cash Orchestrator")
st.caption(
    "An Orchestrator Agent delegates each order to specialist agents -- "
    "Validation, Inventory, Risk, Invoice -- with full handoff tracking and audit trail."
)

with st.sidebar:
    st.header("Backend")
    healthy = check_health()
    st.markdown("Status: **online**" if healthy else "Status: **offline**")
    if st.button("Refresh health"):
        st.rerun()
    if not healthy:
        st.info("Start the API first:  python main.py")

    st.divider()
    st.header("Demo scenarios")
    for label, defaults in SCENARIOS.items():
        if st.button(label, use_container_width=True):
            st.session_state["scenario"] = defaults
            st.session_state["result"] = None
            st.rerun()

    if "history" in st.session_state and st.session_state["history"]:
        st.divider()
        st.header("Recent orders")
        for entry in reversed(st.session_state["history"][-8:]):
            st.markdown(f"`{entry['order_id']}` -- **{entry['status']}**")

scenario = st.session_state.pop("scenario", None)
if scenario is not None:
    st.session_state["customer_choice"] = scenario["customer"]
    st.session_state["product_mode"] = (
        0 if scenario["product_mode"] == "catalog" else 1
    )
    st.session_state["product_choice"] = scenario["product"]
    st.session_state["custom_product"] = scenario["custom_product"]
    st.session_state["quantity_input"] = scenario["quantity"]

customers_payload = api_get("/customers") or {}
products_payload = api_get("/inventory") or {}
customer_names = [c["name"] for c in customers_payload.get("customers", [])]
product_names = [p["name"] for p in products_payload.get("products", [])]

st.header("Place an Order")
with st.form("order_form", clear_on_submit=False):
    col_a, col_b = st.columns(2)
    with col_a:
        customer = st.selectbox(
            "Customer Name",
            options=customer_names or ["(backend offline)"],
            key="customer_choice",
        )
        product_mode = st.radio(
            "Product selection",
            options=["Select from catalog", "Enter manually"],
            key="product_mode",
            horizontal=True,
        )
    with col_b:
        if product_mode == "Select from catalog":
            product = st.selectbox("Product", options=product_names, key="product_choice")
        else:
            product = st.text_input(
                "Product name / SKU",
                value=st.session_state.get("custom_product", ""),
                key="custom_product",
            )
        quantity = st.number_input(
            "Quantity",
            value=1,
            step=1,
            key="quantity_input",
            help="Try a negative number to see the Validation Agent reject it.",
        )
    submitted = st.form_submit_button("Process Order", use_container_width=True)

if submitted:
    payload = {
        "customer_name": customer,
        "product_name": product,
        "quantity": int(quantity),
    }
    result = submit_order(payload)
    if result is not None:
        st.session_state["result"] = result
        history = st.session_state.setdefault("history", [])
        history.append({"order_id": result["order_id"], "status": result["status"]})

result: Optional[dict[str, Any]] = st.session_state.get("result")

if result is None:
    st.info("Submit an order (or click a demo scenario) to watch the agent workflow run.")
    st.stop()

banner_kind, banner_icon = STATUS_BANNERS.get(result["status"], ("info", ""))
traces = result["agent_traces"]

st.header("Final Decision")
getattr(st, banner_kind)(
    f"**{result['status'].upper()}** -- order `{result['order_id']}` -- "
    f"{result['decision_reason']}"
)

st.subheader("Why was this decision made?")
for line in result["explanation"]:
    st.markdown(f"- {line}")

st.header("Workflow Status (Agent Handoffs)")
specialists = ["Validation Agent", "Inventory Agent", "Risk Agent", "Invoice Agent"]
trace_by_agent = {t["agent"]: t for t in traces}
chips = []
for agent_name in specialists:
    trace = trace_by_agent.get(agent_name)
    if trace is None:
        chips.append(f"{agent_name}: not reached")
    elif trace["status"] == "Completed":
        chips.append(f"{agent_name}: done")
    else:
        chips.append(f"{agent_name}: failed")
st.caption(" | ".join(chips))

chain = st.container(border=True)
for i, step in enumerate(result["handoffs"]):
    target = step["to_agent"]
    chain.markdown(f"**{target}**")
    chain.caption(f"step {step['sequence']} -- {step['from_agent']} to {target} -- {step['action']}")
    if i < len(result["handoffs"]) - 1:
        chain.markdown("v")

st.header("Agent Outputs")
for trace in traces:
    with st.expander(
        f"{trace['agent']} -- {trace['status']}: {trace['summary']}",
        expanded=False,
    ):
        st.json(trace["output"])

invoice = result.get("invoice")
st.header("Invoice View")
if invoice is None:
    st.caption("No invoice was generated for this order (workflow halted earlier).")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Invoice ID", invoice["invoice_id"])
    m2.metric("Subtotal", f"${invoice['subtotal_usd']:,.2f}")
    m3.metric(f"Tax ({invoice['tax_rate']:.0%})", f"${invoice['tax_amount_usd']:,.2f}")
    m4.metric("Grand Total", f"${invoice['grand_total_usd']:,.2f}", border=True)
    st.dataframe(
        pd.DataFrame(invoice["line_items"]),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"Billed to {invoice['customer_name']} ({invoice['customer_id']}) -- "
        f"issued {invoice['issued_at_utc']}"
    )
    render_invoice_download(result["order_id"], invoice["invoice_id"])

st.header("Audit Trail")
audit_rows = [
    {
        "Timestamp (UTC)": entry["timestamp_utc"],
        "Agent": entry["agent"],
        "Action": entry["action"],
        "Status": entry["status"],
        "Message": entry["message"],
    }
    for entry in result["audit_trail"]
]
st.dataframe(
    pd.DataFrame(audit_rows),
    use_container_width=True,
    hide_index=True,
)
