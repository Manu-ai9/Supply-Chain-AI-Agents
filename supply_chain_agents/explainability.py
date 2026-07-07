"""
explainability.py
Implements roadmap Step 6: "Explain Every Decision."

Every agent already attaches a `reasoning` field to its structured output.
This module's job is just to assemble those into one consolidated,
human-readable report before the approval checkpoint -- so the human
reviewer sees a clear "why" for every order, every supplier choice, and
every delivery plan, not just the final numbers.
"""

from state import SupplyChainState


def build_line_items(state: SupplyChainState) -> dict:
    """Consolidate per-SKU agent outputs into reviewable bundles."""
    line_items = {}
    for sku in state.get("skus_needing_reorder", []):
        line_items[sku] = {
            "sku": sku,
            "product_name": state["forecasts"][sku].product_name,
            "forecast": state["forecasts"][sku],
            "stock_signal": state["stock_signals"][sku],
            "draft_order": state.get("draft_orders", {}).get(sku),
            "delivery_plan": state.get("delivery_plans", {}).get(sku),
        }
    return line_items


def format_approval_report(state: SupplyChainState) -> str:
    """Render the full explainable proposal as plain text for a human approver."""
    lines = ["=" * 78, "SUPPLY CHAIN REPLENISHMENT PROPOSAL — PENDING HUMAN APPROVAL", "=" * 78]

    if not state.get("skus_needing_reorder"):
        lines.append("\nNo SKUs require reordering this cycle. Nothing to approve.")
        return "\n".join(lines)

    total_cost = 0.0
    for sku in state["skus_needing_reorder"]:
        item = state["line_items"][sku]
        forecast = item["forecast"]
        stock = item["stock_signal"]
        order = item["draft_order"]
        delivery = item["delivery_plan"]

        lines.append(f"\n--- {sku}: {item['product_name']} ---")
        lines.append(f"  [Demand Agent]      {forecast.predicted_daily_demand} units/day forecast "
                      f"({forecast.trend}, {forecast.confidence:.0%} confidence)")
        lines.append(f"                      Why: {forecast.reasoning}")
        lines.append(f"  [Inventory Agent]   Urgency: {stock.urgency.upper()} | "
                      f"{stock.days_of_cover} days of cover left")
        lines.append(f"                      Why: {stock.reasoning}")

        if order:
            lines.append(f"  [Procurement Agent] Order {order.quantity} units from "
                          f"{order.chosen_supplier.supplier} | ${order.total_cost:,.2f}")
            lines.append(f"                      Why: {order.reasoning}")
            total_cost += order.total_cost
        if delivery:
            lines.append(f"  [Delivery Agent]    {delivery.carrier} | ETA {delivery.eta_days} days | "
                          f"${delivery.estimated_delivery_cost:,.2f} shipping")
            lines.append(f"                      Why: {delivery.reasoning}")

    lines.append(f"\nTOTAL PROPOSED SPEND: ${total_cost:,.2f} across "
                  f"{len(state['skus_needing_reorder'])} SKU(s)")
    lines.append("=" * 78)
    return "\n".join(lines)
