# Supply Chain AI Agent System

A working, runnable implementation of the "Replenishment to Human-Controlled"
7-step agent roadmap, built with **LangGraph**. Demand forecasting, stock
checks, supplier selection, and delivery planning are each handled by a
separate specialist agent, coordinated through typed shared state, with a
real human-approval gate before any order executes.

No API key is required to run it — agents use deterministic, explainable
heuristics by default. Set `ANTHROPIC_API_KEY` and every agent switches to
Claude-driven structured reasoning instead, with zero changes to the graph
or agent interfaces.

## How this maps to the 7-step roadmap

| Step | Roadmap concept | Where it lives in this repo |
|---|---|---|
| 1 | Map the workflow | `graph.py` — the topology is documented and built before any agent logic runs |
| 2 | Split into specialist agents | `agents/` — one file per agent (Demand, Inventory, Procurement, Delivery), one job each |
| 3 | Connect real tools | `tools.py` + `data_backends/` — POS/inventory/supplier/fleet reads, backed by either flat JSON files or a real SQLite database, swappable with zero changes to agent code |
| 4 | Pass structured state | `state.py` — typed Pydantic models for every handoff: `ForecastSignal -> StockSignal -> DraftOrder -> DeliveryPlan` |
| 5 | Add human approval | `approval.py` — `human_approval_node` pauses the graph with LangGraph's `interrupt()` until a real decision comes back |
| 6 | Explain every decision | every agent writes a `reasoning` field; `explainability.py` renders the consolidated report |
| 7 | Evaluate the workflow | `evaluate.py` — checks handoff correctness, routing logic, and explainability completeness |

## Data layer: JSON files and a real SQLite database, side by side

This project ships with both, on purpose, to demonstrate that agents are
written against a stable tool interface, not against a specific data
source:

- `mock_data/*.json` — flat files, the simplest possible backend.
- `database/supply_chain.db` — a real, normalized SQLite database (tables
  for products, daily sales, inventory, suppliers, carriers, and an
  order log), built from those same JSON files by `db_setup.py`.

`tools.py` is a thin dispatcher: it picks one of `data_backends/json_backend.py`
or `data_backends/sqlite_backend.py` and re-exports its functions under the
same names (`get_current_stock`, `get_supplier_catalog`, etc.). Every agent
just does `from tools import get_current_stock` — it has no idea, and
doesn't need to care, which backend is actually answering that call.

Backend selection is automatic: if `database/supply_chain.db` exists,
SQLite is used; otherwise it falls back to JSON. You can force either one
explicitly with an environment variable:

```bash
python db_setup.py              # builds/resets the SQLite database from the JSON source
python main.py                  # auto-detects -> uses SQLite since the db now exists
DATA_BACKEND=json python main.py    # force the flat-file backend
DATA_BACKEND=sqlite python main.py  # force the database backend explicitly
```

Both backends were verified to return identical results: `evaluate.py`
passes with 0 issues under either one.


## Architecture

```
demand_agent
     |
inventory_agent
     |
(any SKU need reorder?)
   /            \
procurement   prepare_for_approval  (skip straight here if nothing needs action)
   |
delivery_agent
   |
prepare_for_approval
   |
human_approval   <-- graph PAUSES here until a human responds
   |
execute_orders
   |
  END
```

Six mock SKUs are included with different demand/stock profiles, so a single
run exercises both branches: most SKUs trigger a reorder, one (steady demand,
healthy stock) does not — letting you see the conditional routing skip
procurement and delivery for that SKU.

## Setup

```bash
pip install -r requirements.txt
python db_setup.py   # builds database/supply_chain.db from the mock JSON data
```

## Run it

Interactive (you play the human approver):
```bash
python main.py
```
At the approval prompt, type `a` to approve everything, `n` to reject
everything, or `s` to select specific SKUs by name.

Run the evaluation suite:
```bash
python evaluate.py
```

## Going from mock to live

- **Real systems instead of SQLite**: the SQLite database already proves
  the pattern (agents call a tool function and get data back, with no idea
  where it came from). Pointing at a real production database, or a real
  POS/supplier/fleet API, just means writing a third file in
  `data_backends/` with the same six function names and adding it to the
  dispatcher in `tools.py` — agent code never changes.
- **LLM-driven reasoning**: copy `.env.example` to `.env`, set
  `ANTHROPIC_API_KEY`, and load it into your shell environment before
  running. Each agent will then call Claude through
  `llm_utils.structured_call()`, which forces the model's output into the
  exact same Pydantic schema the rule-based fallback produces — so nothing
  downstream needs to know which one ran.
- **Persistent checkpointing**: swap `MemorySaver()` in `graph.py` for
  `SqliteSaver` or `PostgresSaver` so an approval can sit pending for hours
  or days without losing state, instead of only living in memory.

## Notes on what's deliberately simplified

- The supplier scoring function (`procurement_agent._score_supplier`) is a
  simple weighted formula (price/speed/reliability) — a real system might
  also weigh contract terms, sustainability requirements, or volume
  discounts. The point is that the score and its weights are explicit and
  swappable, not buried in an opaque LLM call.
- Delivery cost/ETA estimates don't account for weekends, holidays, or
  customs — fine for a demo, not for production.
- Every SKU needing reorder is routed through human approval in this demo,
  by design, to make the human-in-the-loop pattern explicit. A production
  system might auto-approve low-cost, low-risk line items and only escalate
  high-value or high-uncertainty ones to a human.
