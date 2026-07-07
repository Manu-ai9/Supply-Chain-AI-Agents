"""
agents/inventory_agent.py
Specialist Agent #2: Inventory.

Single job: combine the Demand Agent's forecast with current stock levels
to decide whether each SKU needs reordering, and how urgently.
Receives ForecastSignal (structured handoff), produces StockSignal.
"""

from tools import get_current_stock
from state import SupplyChainState, StockSignal
from llm_utils import structured_call


def _urgency_from_days_of_cover(days_of_cover: float, safety_stock_days: int) -> str:
    if days_of_cover <= 0:
        return "critical"
    ratio = days_of_cover / safety_stock_days
    if ratio < 0.5:
        return "critical"
    if ratio < 1.0:
        return "high"
    if ratio < 1.5:
        return "medium"
    if ratio < 2.5:
        return "low"
    return "none"


def _heuristic_stock_signal(sku: str, forecast, inventory: dict) -> StockSignal:
    current_stock = inventory["current_stock"]
    safety_days = inventory["safety_stock_days"]
    daily_demand = max(forecast.predicted_daily_demand, 0.1)
    days_of_cover = current_stock / daily_demand
    forecasted_demand_units = daily_demand * safety_days

    urgency = _urgency_from_days_of_cover(days_of_cover, safety_days)
    reorder_needed = urgency != "none"

    reasoning = (
        f"Current stock of {current_stock} units covers about {days_of_cover:.1f} days "
        f"at the forecasted demand of {daily_demand:.1f} units/day. The safety stock "
        f"policy requires {safety_days} days of cover, so urgency is '{urgency}'."
    )

    return StockSignal(
        sku=sku,
        current_stock=current_stock,
        forecasted_demand_units=round(forecasted_demand_units, 1),
        safety_stock_days=safety_days,
        days_of_cover=round(days_of_cover, 1),
        reorder_needed=reorder_needed,
        urgency=urgency,
        reasoning=reasoning,
    )


def inventory_agent(state: SupplyChainState) -> dict:
    forecasts = state["forecasts"]
    stock_signals = {}
    needing_reorder = []

    for sku, forecast in forecasts.items():
        inventory = get_current_stock(sku)
        fallback = _heuristic_stock_signal(sku, forecast, inventory)

        prompt = (
            f"You are an inventory planning analyst. Product {sku} has current stock of "
            f"{inventory['current_stock']} units, a safety stock policy of "
            f"{inventory['safety_stock_days']} days, and forecasted demand of "
            f"{forecast.predicted_daily_demand} units/day (confidence {forecast.confidence}). "
            f"Decide whether this SKU needs reordering and assign an urgency level "
            f"(none/low/medium/high/critical) based on how many days of cover remain "
            f"versus the safety stock policy. Explain your reasoning with the actual numbers."
        )
        signal = structured_call(prompt, StockSignal, fallback)
        signal.sku = sku
        stock_signals[sku] = signal
        if signal.reorder_needed:
            needing_reorder.append(sku)

    return {
        "stock_signals": stock_signals,
        "skus_needing_reorder": needing_reorder,
        "audit_log": [
            f"[Inventory Agent] {len(needing_reorder)} of {len(stock_signals)} SKUs flagged for reorder."
        ],
    }
