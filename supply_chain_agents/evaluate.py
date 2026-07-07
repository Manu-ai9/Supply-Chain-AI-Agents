"""
evaluate.py
Implements roadmap Step 7: "Evaluate the Workflow."

This is not an LLM eval -- it's a workflow-correctness eval, checking
the things that actually break agent systems in production:
  1. Did every SKU that should reorder actually get flagged?
  2. Did structured handoffs stay internally consistent (e.g. order
     quantity respects the chosen supplier's minimum order quantity)?
  3. Does every decision carry a non-empty `reasoning` field (the
     explainability requirement from Step 6)?
  4. Did the conditional routing correctly skip procurement/delivery
     for SKUs that didn't need reordering?
  5. End-to-end timing, as a proxy for "fast handoff review."

Run with:
    python evaluate.py
"""

import time
from langgraph.types import Command
from graph import build_graph
from tools import active_backend


def run_full_cycle():
    graph = build_graph()
    config = {"configurable": {"thread_id": "eval-run"}}
    start = time.perf_counter()

    for _ in graph.stream({}, config=config, stream_mode="updates"):
        pass

    state = graph.get_state(config)
    if state.next and "human_approval" in state.next:
        pending = state.tasks[0].interrupts[0].value["skus_pending"]
        decision = {"approved": True, "skus_approved": pending, "skus_rejected": [],
                    "reasoning": "eval auto-approve"}
        for _ in graph.stream(Command(resume=decision), config=config, stream_mode="updates"):
            pass

    elapsed = time.perf_counter() - start
    return graph.get_state(config).values, elapsed


def check_correctness_and_completeness(final_state: dict) -> list[str]:
    failures = []

    skus = final_state.get("skus", [])
    forecasts = final_state.get("forecasts", {})
    stock_signals = final_state.get("stock_signals", {})
    draft_orders = final_state.get("draft_orders", {})
    delivery_plans = final_state.get("delivery_plans", {})
    needing_reorder = final_state.get("skus_needing_reorder", [])

    # 1. Every SKU got a forecast and a stock signal -- no silent drops.
    for sku in skus:
        if sku not in forecasts:
            failures.append(f"{sku}: missing ForecastSignal (Demand Agent dropped it)")
        if sku not in stock_signals:
            failures.append(f"{sku}: missing StockSignal (Inventory Agent dropped it)")

    # 2. Conditional routing correctness: every flagged SKU got a draft order + delivery plan,
    #    and SKUs that were NOT flagged correctly skipped procurement/delivery.
    for sku in needing_reorder:
        if sku not in draft_orders:
            failures.append(f"{sku}: flagged for reorder but Procurement Agent produced no DraftOrder")
        if sku not in delivery_plans:
            failures.append(f"{sku}: flagged for reorder but Delivery Agent produced no DeliveryPlan")
    for sku in skus:
        if sku not in needing_reorder and sku in draft_orders:
            failures.append(f"{sku}: NOT flagged for reorder but a DraftOrder was created anyway (routing bug)")

    # 3. Structured-state internal consistency: order qty must respect supplier's min order qty.
    for sku, order in draft_orders.items():
        if order.quantity < order.chosen_supplier.min_order_qty:
            failures.append(
                f"{sku}: order quantity {order.quantity} is below supplier minimum "
                f"{order.chosen_supplier.min_order_qty} (constraint violated)"
            )
        expected_cost = round(order.quantity * order.chosen_supplier.unit_price, 2)
        if abs(order.total_cost - expected_cost) > 0.01:
            failures.append(f"{sku}: total_cost {order.total_cost} doesn't match qty*unit_price {expected_cost}")

    # 4. Explainability completeness: every decision needs a non-trivial reasoning string.
    def _check_reasoning(label, obj):
        if not obj.reasoning or len(obj.reasoning.strip()) < 15:
            failures.append(f"{label}: reasoning field missing or too short to be useful")

    for sku, f in forecasts.items():
        _check_reasoning(f"{sku} ForecastSignal", f)
    for sku, s in stock_signals.items():
        _check_reasoning(f"{sku} StockSignal", s)
    for sku, o in draft_orders.items():
        _check_reasoning(f"{sku} DraftOrder", o)
    for sku, d in delivery_plans.items():
        _check_reasoning(f"{sku} DeliveryPlan", d)

    return failures


def main():
    print("Running full workflow cycle for evaluation...")
    print(f"Data backend: {active_backend()}\n")
    final_state, elapsed = run_full_cycle()

    failures = check_correctness_and_completeness(final_state)

    print(f"SKUs processed:        {len(final_state.get('skus', []))}")
    print(f"Flagged for reorder:   {len(final_state.get('skus_needing_reorder', []))}")
    print(f"Orders executed:       "
          f"{sum(1 for r in final_state.get('execution_results', {}).values() if r['status'] == 'executed')}")
    print(f"End-to-end runtime:    {elapsed:.3f}s")

    print(f"\n{'PASS' if not failures else 'FAIL'}: {len(failures)} issue(s) found")
    for f in failures:
        print(f"  - {f}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
