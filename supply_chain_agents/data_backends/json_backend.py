"""
data_backends/json_backend.py
Reads/writes the mock_data/*.json files.

Implements the exact same function signatures as sqlite_backend.py, so
tools.py can point at either one without any other code knowing which
is active.
"""

import json
import os
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mock_data")


def _load(filename: str) -> dict:
    with open(os.path.join(_DATA_DIR, filename)) as f:
        return json.load(f)


def get_sales_history(sku: str) -> dict:
    data = _load("sales_history.json")
    if sku not in data:
        raise ValueError(f"No sales history found for {sku}")
    return data[sku]


def get_all_skus() -> list[str]:
    return list(_load("sales_history.json").keys())


def get_current_stock(sku: str) -> dict:
    data = _load("inventory.json")
    if sku not in data:
        raise ValueError(f"No inventory record found for {sku}")
    return data[sku]


def get_supplier_catalog(sku: str) -> list[dict]:
    data = _load("suppliers.json")
    return data.get(sku, [])


def get_fleet_options() -> dict:
    return _load("fleet.json")


def place_supplier_order(sku: str, supplier: str, quantity: int) -> dict:
    log_path = os.path.join(_DATA_DIR, "order_log.json")
    log = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            log = json.load(f)
    entry = {
        "sku": sku,
        "supplier": supplier,
        "quantity": quantity,
        "submitted_at": datetime.utcnow().isoformat(),
        "confirmation_id": f"PO-{sku}-{int(datetime.utcnow().timestamp())}",
    }
    log.append(entry)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)
    return entry
