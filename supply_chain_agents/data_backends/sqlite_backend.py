"""
data_backends/sqlite_backend.py
Reads/writes the real SQLite database at database/supply_chain.db.

Implements the exact same function signatures as json_backend.py, so
tools.py can point at either one without any other code knowing which
is active. Run `python db_setup.py` first to create/reset this database
from the mock_data/*.json source files.
"""

import os
import sqlite3
from datetime import datetime

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "supply_chain.db")


def _connect() -> sqlite3.Connection:
    if not os.path.exists(_DB_PATH):
        raise FileNotFoundError(
            f"No database found at {_DB_PATH}. Run `python db_setup.py` first to build it "
            f"from mock_data/*.json, or set DATA_BACKEND=json to use the flat files instead."
        )
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_sales_history(sku: str) -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT name, trend FROM products WHERE sku = ?", (sku,)).fetchone()
        if row is None:
            raise ValueError(f"No sales history found for {sku}")
        sales_rows = cur.execute(
            "SELECT units FROM daily_sales WHERE sku = ? ORDER BY day_offset", (sku,)
        ).fetchall()
        return {
            "name": row["name"],
            "trend": row["trend"],
            "daily_sales_last_30_days": [r["units"] for r in sales_rows],
        }
    finally:
        conn.close()


def get_all_skus() -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT sku FROM products ORDER BY sku").fetchall()
        return [r["sku"] for r in rows]
    finally:
        conn.close()


def get_current_stock(sku: str) -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT current_stock, safety_stock_days, warehouse FROM inventory WHERE sku = ?", (sku,)
        ).fetchone()
        if row is None:
            raise ValueError(f"No inventory record found for {sku}")
        return dict(row)
    finally:
        conn.close()


def get_supplier_catalog(sku: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT supplier, unit_price, lead_time_days, reliability_score, min_order_qty "
            "FROM suppliers WHERE sku = ? ORDER BY id", (sku,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_fleet_options() -> dict:
    conn = _connect()
    try:
        carrier_rows = conn.execute(
            "SELECT name, max_lead_time_days, cost_multiplier, reliability_score FROM carriers"
        ).fetchall()
        hours_rows = conn.execute("SELECT warehouse, hours FROM warehouse_hours").fetchall()
        return {
            "carriers": [dict(r) for r in carrier_rows],
            "warehouse_receiving_hours": {r["warehouse"]: r["hours"] for r in hours_rows},
        }
    finally:
        conn.close()


def place_supplier_order(sku: str, supplier: str, quantity: int) -> dict:
    conn = _connect()
    try:
        submitted_at = datetime.utcnow().isoformat()
        confirmation_id = f"PO-{sku}-{int(datetime.utcnow().timestamp())}"
        conn.execute(
            "INSERT INTO order_log (sku, supplier, quantity, submitted_at, confirmation_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (sku, supplier, quantity, submitted_at, confirmation_id),
        )
        conn.commit()
        return {
            "sku": sku,
            "supplier": supplier,
            "quantity": quantity,
            "submitted_at": submitted_at,
            "confirmation_id": confirmation_id,
        }
    finally:
        conn.close()
