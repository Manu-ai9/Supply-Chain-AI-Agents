"""
agents/delivery_agent.py
Specialist Agent #4: Delivery.

Single job: given a draft order, pick a carrier/delivery option and
produce a delivery plan. This corresponds to the "Plan Delivery" step
in the workflow-at-a-glance row of the original roadmap.
"""

from tools import get_fleet_options, get_current_stock
from state import SupplyChainState, DeliveryPlan
from llm_utils import structured_call


def _heuristic_delivery_plan(sku: str, draft_order, urgency: str, fleet: dict, warehouse: str) -> DeliveryPlan:
    carriers = fleet["carriers"]
    if urgency in ("critical", "high"):
        chosen = min(carriers, key=lambda c: c["max_lead_time_days"])
    else:
        chosen = min(carriers, key=lambda c: c["cost_multiplier"])

    eta_days = draft_order.chosen_supplier.lead_time_days + max(chosen["max_lead_time_days"] - 5, 1)
    cost = round(draft_order.total_cost * 0.04 * chosen["cost_multiplier"], 2)

    reasoning = (
        f"Urgency is '{urgency}', so the agent prioritized "
        f"{'delivery speed' if urgency in ('critical', 'high') else 'cost efficiency'} "
        f"and selected {chosen['name']}. Combined with the supplier's "
        f"{draft_order.chosen_supplier.lead_time_days}-day production lead time, "
        f"estimated arrival is in {eta_days} days at warehouse {warehouse}."
    )

    return DeliveryPlan(
        sku=sku,
        carrier=chosen["name"],
        eta_days=eta_days,
        estimated_delivery_cost=cost,
        warehouse=warehouse,
        reasoning=reasoning,
    )


def delivery_agent(state: SupplyChainState) -> dict:
    draft_orders = state.get("draft_orders", {})
    stock_signals = state["stock_signals"]
    fleet = get_fleet_options()
    delivery_plans = {}

    for sku, order in draft_orders.items():
        urgency = stock_signals[sku].urgency
        warehouse = get_current_stock(sku)["warehouse"]
        fallback = _heuristic_delivery_plan(sku, order, urgency, fleet, warehouse)

        prompt = (
            f"You are a logistics planner. A purchase order for {order.quantity} units of "
            f"{order.product_name} ({sku}) was placed with {order.chosen_supplier.supplier}, "
            f"who has a {order.chosen_supplier.lead_time_days}-day lead time. Stock urgency is "
            f"'{urgency}'. Available carriers: {fleet['carriers']}. Destination warehouse: {warehouse}. "
            f"Choose a carrier, estimate total ETA in days (supplier lead time + transit), estimate "
            f"delivery cost, and explain your reasoning."
        )
        plan = structured_call(prompt, DeliveryPlan, fallback)
        plan.sku = sku
        delivery_plans[sku] = plan

    return {
        "delivery_plans": delivery_plans,
        "audit_log": [f"[Delivery Agent] Planned delivery for {len(delivery_plans)} order(s)."],
    }
