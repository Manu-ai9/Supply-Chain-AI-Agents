"""
agents/demand_agent.py
Specialist Agent #1: Demand.

Single job: look at sales history and produce a demand forecast per SKU.
Does not know anything about stock levels, suppliers, or delivery --
that separation is the point of Step 2 ("Split into Specialist Agents").
"""

import statistics
from tools import get_sales_history, get_all_skus
from state import SupplyChainState, ForecastSignal
from llm_utils import structured_call


def _heuristic_forecast(sku: str, history: dict) -> ForecastSignal:
    sales = history["daily_sales_last_30_days"]
    recent_avg = statistics.mean(sales[-7:])
    overall_avg = statistics.mean(sales)
    trend = history["trend"]

    if trend == "rising":
        predicted = recent_avg * 1.08
    elif trend == "falling":
        predicted = recent_avg * 0.92
    else:
        predicted = (recent_avg + overall_avg) / 2

    variance = statistics.pstdev(sales)
    confidence = max(0.5, min(0.97, 1 - (variance / (overall_avg + 1e-6)) * 0.5))

    reasoning = (
        f"Last 7-day average sales were {recent_avg:.1f} units/day vs a 30-day "
        f"average of {overall_avg:.1f}. Trend is '{trend}', so the forecast was "
        f"adjusted from the recent average. Day-to-day variance was "
        f"{'low' if variance < overall_avg * 0.15 else 'moderate'}, giving "
        f"{confidence:.0%} confidence."
    )

    return ForecastSignal(
        sku=sku,
        product_name=history["name"],
        predicted_daily_demand=round(predicted, 1),
        trend=trend,
        confidence=round(confidence, 2),
        reasoning=reasoning,
    )


def demand_agent(state: SupplyChainState) -> dict:
    skus = state.get("skus") or get_all_skus()
    forecasts = {}
    for sku in skus:
        history = get_sales_history(sku)
        fallback = _heuristic_forecast(sku, history)

        prompt = (
            f"You are a demand forecasting analyst for a retail supply chain. "
            f"Product: {history['name']} ({sku}). "
            f"Daily sales for the last 30 days: {history['daily_sales_last_30_days']}. "
            f"Trend label from the system: {history['trend']}. "
            f"Forecast the average daily demand for the next 14 days and explain your reasoning "
            f"in 1-2 sentences referencing the actual numbers."
        )
        forecast = structured_call(prompt, ForecastSignal, fallback)
        forecast.sku = sku
        forecast.product_name = history["name"]
        forecasts[sku] = forecast

    return {
        "skus": skus,
        "forecasts": forecasts,
        "audit_log": [f"[Demand Agent] Forecasted demand for {len(forecasts)} SKUs."],
    }
