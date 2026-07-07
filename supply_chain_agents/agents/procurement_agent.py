"""
agents/procurement_agent.py
Specialist Agent #3: Procurement.

Single job: for SKUs flagged by the Inventory Agent, draft an order
quantity and select a supplier. Only runs on the subset of SKUs that
actually need it -- this is the conditional routing that keeps agents
from doing wasted work on SKUs that are already healthy.
"""

from tools import get_supplier_catalog
from state import SupplyChainState, DraftOrder, SupplierChoice
from llm_utils import structured_call


def _score_supplier(s: dict) -> float:
    # Composite score: cheaper, faster, more reliable = higher score.
    # Weighted toward reliability since stockouts are costlier than a slightly higher unit price.
    price_score = 1 / (s["unit_price"] + 1e-6)
    speed_score = 1 / (s["lead_time_days"] + 1e-6)
    norm_price = price_score / (price_score + 0.15)
    norm_speed = speed_score / (speed_score + 0.08)
    return round(0.35 * norm_price + 0.25 * norm_speed + 0.40 * s["reliability_score"], 3)


def _heuristic_draft_order(sku: str, product_name: str, stock_signal, suppliers: list[dict]) -> DraftOrder:
    scored = []
    for s in suppliers:
        choice = SupplierChoice(
            supplier=s["supplier"],
            unit_price=s["unit_price"],
            lead_time_days=s["lead_time_days"],
            reliability_score=s["reliability_score"],
            min_order_qty=s["min_order_qty"],
            score=_score_supplier(s),
        )
        scored.append(choice)
    scored.sort(key=lambda c: c.score, reverse=True)
    best = scored[0]

    gap_units = max(stock_signal.forecasted_demand_units - stock_signal.current_stock, 0)
    quantity = max(int(gap_units * 1.15), best.min_order_qty)
    total_cost = round(quantity * best.unit_price, 2)

    reasoning = (
        f"Selected {best.supplier} (score {best.score}) over "
        f"{len(scored) - 1} alternative(s) based on price, lead time, and reliability. "
        f"Order quantity of {quantity} units covers the projected shortfall of "
        f"{gap_units:.0f} units plus a buffer, while meeting the {best.min_order_qty}-unit "
        f"minimum order requirement."
    )

    return DraftOrder(
        sku=sku,
        product_name=product_name,
        quantity=quantity,
        chosen_supplier=best,
        alternatives_considered=scored[1:],
        total_cost=total_cost,
        reasoning=reasoning,
    )


def procurement_agent(state: SupplyChainState) -> dict:
    skus_needing_reorder = state.get("skus_needing_reorder", [])
    forecasts = state["forecasts"]
    stock_signals = state["stock_signals"]
    draft_orders = {}

    for sku in skus_needing_reorder:
        suppliers = get_supplier_catalog(sku)
        if not suppliers:
            continue
        stock_signal = stock_signals[sku]
        product_name = forecasts[sku].product_name
        fallback = _heuristic_draft_order(sku, product_name, stock_signal, suppliers)

        prompt = (
            f"You are a procurement analyst drafting a purchase order for {product_name} ({sku}). "
            f"Stock urgency is '{stock_signal.urgency}' with {stock_signal.days_of_cover} days of cover "
            f"remaining. Available suppliers: {suppliers}. "
            f"Choose the best supplier weighing price, lead time, and reliability (reliability matters most "
            f"since a stockout is costly), pick an order quantity that covers the shortfall plus a buffer "
            f"while respecting each supplier's minimum order quantity, and explain your reasoning."
        )
        order = structured_call(prompt, DraftOrder, fallback)
        order.sku = sku
        order.product_name = product_name
        draft_orders[sku] = order

    return {
        "draft_orders": draft_orders,
        "audit_log": [f"[Procurement Agent] Drafted {len(draft_orders)} purchase order(s)."],
    }
