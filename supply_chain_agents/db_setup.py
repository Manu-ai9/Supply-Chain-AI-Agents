"""
db_setup.py
Builds a real SQLite database (database/supply_chain.db) from the JSON
mock data files, normalized into proper relational tables.

Run with:
    python db_setup.py

This is idempotent -- safe to re-run any time you want to reset the
database back to the original mock data (e.g. after the demo writes
new rows into order_log).

Why both JSON and SQLite exist side by side in this project: tools.py
exposes the same functions (get_current_stock, get_supplier_catalog, etc.)
regardless of which backend is active. That's the actual point being
demonstrated -- agents call a tool function and get back the same shape
of data whether it's reading a flat file or a real database, so the
data layer can be upgraded without ever touching agent code.
"""

import json
import os
import sqlite3

_BASE_DIR = os.path.dirname(__file__)
_MOCK_DIR = os.path.join(_BASE_DIR, "mock_data")
_DB_PATH = os.path.join(_BASE_DIR, "database", "supply_chain.db")


SCHEMA = """
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS daily_sales;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS carriers;
DROP TABLE IF EXISTS warehouse_hours;
DROP TABLE IF EXISTS order_log;

CREATE TABLE products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trend TEXT NOT NULL CHECK (trend IN ('rising', 'falling', 'stable'))
);

CREATE TABLE daily_sales (
    sku TEXT NOT NULL REFERENCES products(sku),
    day_offset INTEGER NOT NULL,
    units INTEGER NOT NULL,
    PRIMARY KEY (sku, day_offset)
);

CREATE TABLE inventory (
    sku TEXT PRIMARY KEY REFERENCES products(sku),
    current_stock INTEGER NOT NULL,
    safety_stock_days INTEGER NOT NULL,
    warehouse TEXT NOT NULL
);

CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL REFERENCES products(sku),
    supplier TEXT NOT NULL,
    unit_price REAL NOT NULL,
    lead_time_days INTEGER NOT NULL,
    reliability_score REAL NOT NULL,
    min_order_qty INTEGER NOT NULL
);

CREATE TABLE carriers (
    name TEXT PRIMARY KEY,
    max_lead_time_days INTEGER NOT NULL,
    cost_multiplier REAL NOT NULL,
    reliability_score REAL NOT NULL
);

CREATE TABLE warehouse_hours (
    warehouse TEXT PRIMARY KEY,
    hours TEXT NOT NULL
);

CREATE TABLE order_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    supplier TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    confirmation_id TEXT NOT NULL
);
"""


def build_database():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    with open(os.path.join(_MOCK_DIR, "sales_history.json")) as f:
        sales = json.load(f)
    for sku, rec in sales.items():
        cur.execute("INSERT INTO products (sku, name, trend) VALUES (?, ?, ?)",
                    (sku, rec["name"], rec["trend"]))
        for day_offset, units in enumerate(rec["daily_sales_last_30_days"]):
            cur.execute("INSERT INTO daily_sales (sku, day_offset, units) VALUES (?, ?, ?)",
                        (sku, day_offset, units))

    with open(os.path.join(_MOCK_DIR, "inventory.json")) as f:
        inventory = json.load(f)
    for sku, rec in inventory.items():
        cur.execute(
            "INSERT INTO inventory (sku, current_stock, safety_stock_days, warehouse) VALUES (?, ?, ?, ?)",
            (sku, rec["current_stock"], rec["safety_stock_days"], rec["warehouse"]),
        )

    with open(os.path.join(_MOCK_DIR, "suppliers.json")) as f:
        suppliers = json.load(f)
    for sku, options in suppliers.items():
        for s in options:
            cur.execute(
                "INSERT INTO suppliers (sku, supplier, unit_price, lead_time_days, reliability_score, "
                "min_order_qty) VALUES (?, ?, ?, ?, ?, ?)",
                (sku, s["supplier"], s["unit_price"], s["lead_time_days"], s["reliability_score"],
                 s["min_order_qty"]),
            )

    with open(os.path.join(_MOCK_DIR, "fleet.json")) as f:
        fleet = json.load(f)
    for c in fleet["carriers"]:
        cur.execute(
            "INSERT INTO carriers (name, max_lead_time_days, cost_multiplier, reliability_score) "
            "VALUES (?, ?, ?, ?)",
            (c["name"], c["max_lead_time_days"], c["cost_multiplier"], c["reliability_score"]),
        )
    for warehouse, hours in fleet["warehouse_receiving_hours"].items():
        cur.execute("INSERT INTO warehouse_hours (warehouse, hours) VALUES (?, ?)", (warehouse, hours))

    conn.commit()
    conn.close()
    print(f"Built {_DB_PATH} from mock_data/*.json")


if __name__ == "__main__":
    build_database()
