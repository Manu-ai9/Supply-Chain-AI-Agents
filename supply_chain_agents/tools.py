"""
tools.py
Implements roadmap Step 3: "Connect Real Tools."

This module no longer holds any data logic itself -- it just decides
WHICH backend implements the tools (data_backends/json_backend.py or
data_backends/sqlite_backend.py) and re-exports that backend's functions
under the same names. Every agent does:

    from tools import get_current_stock

and has no idea, and doesn't need to care, whether that's reading a flat
JSON file or querying a real SQLite database. That's the actual point of
"connecting real tools": agents are written against a stable interface,
not against a specific data source, so the data source can be swapped or
upgraded later with zero changes to agent logic.

Backend selection:
  - Set the DATA_BACKEND environment variable to "json" or "sqlite" to
    force a specific backend.
  - If unset, this module auto-detects: it uses sqlite if
    database/supply_chain.db exists (run `python db_setup.py` to create
    it), otherwise it falls back to the JSON files in mock_data/.
"""

import os
from data_backends import json_backend, sqlite_backend

_DB_PATH = os.path.join(os.path.dirname(__file__), "database", "supply_chain.db")


def _resolve_backend() -> str:
    requested = os.environ.get("DATA_BACKEND", "").strip().lower()
    if requested in ("json", "sqlite"):
        return requested
    return "sqlite" if os.path.exists(_DB_PATH) else "json"


_BACKEND = _resolve_backend()
_impl = sqlite_backend if _BACKEND == "sqlite" else json_backend


def active_backend() -> str:
    """Returns which backend ('json' or 'sqlite') is currently wired up."""
    return _BACKEND


get_sales_history = _impl.get_sales_history
get_all_skus = _impl.get_all_skus
get_current_stock = _impl.get_current_stock
get_supplier_catalog = _impl.get_supplier_catalog
get_fleet_options = _impl.get_fleet_options
place_supplier_order = _impl.place_supplier_order
