"""Demo driver: runs one successful workflow and all four exception cases.

Usage:
    python scripts/demo_scenarios.py            (API must be running)
    python scripts/demo_scenarios.py --local    (runs in-process, no API needed)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.schemas import OrderRequest  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"

SCENARIOS: list[tuple[str, OrderRequest]] = [
    ("SUCCESS - approved order", OrderRequest(customer_name="Acme Manufacturing", product_name="Vision Sensor Pro", quantity=10)),
    ("CASE 1 - insufficient inventory (escalated)", OrderRequest(customer_name="Delta Foods", product_name="Industrial Drone X200", quantity=80)),
    ("CASE 2 - invalid quantity (rejected)", OrderRequest(customer_name="Acme Manufacturing", product_name="Vision Sensor Pro", quantity=-5)),
    ("CASE 3 - unknown product (rejected)", OrderRequest(customer_name="Brightline Retail Group", product_name="Teleportation Beam", quantity=3)),
    ("CASE 4 - high risk customer (manual review)", OrderRequest(customer_name="Cortex Labs", product_name="Robotic Arm RA-7", quantity=1)),
]


def run_remote() -> None:
    for label, request in SCENARIOS:
        response = requests.post(f"{BASE_URL}/orders/process", json=request.model_dump(), timeout=30)
        response.raise_for_status()
        result = response.json()
        print("=" * 78)
        print(f"{label}")
        print(f"order_id : {result['order_id']}")
        print(f"status   : {result['status']}")
        print(f"decision : {result['decision_reason']}")
        print("handoffs : " + " -> ".join(step["to_agent"] for step in result["handoffs"]))
        print("why      :")
        for line in result["explanation"]:
            print(f"  - {line}")


def run_local() -> None:
    from api.routes import orchestrator

    for label, request in SCENARIOS:
        result = orchestrator.process_order(request)
        print("=" * 78)
        print(label)
        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str)[:4000])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="run without the HTTP server")
    args = parser.parse_args()
    run_local() if args.local else run_remote()
