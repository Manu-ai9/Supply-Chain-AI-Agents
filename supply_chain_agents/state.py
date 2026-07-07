"""
state.py
Structured data contracts passed between agents in the supply chain graph.

This is the implementation of roadmap Step 4: "Pass Structured State."
Every handoff between agents uses a typed Pydantic model instead of free
text, so each agent gets exactly the fields it needs and nothing is lost
or ambiguous between hops.

Pipeline of structured handoffs:
    ForecastSignal  -> StockSignal -> DraftOrder -> DeliveryPlan -> ApprovalDecision
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
import operator
from typing import Annotated, TypedDict


class ForecastSignal(BaseModel):
    """Output of the Demand Agent for a single SKU."""
    sku: str
    product_name: str
    predicted_daily_demand: float = Field(description="Forecasted average units sold per day")
    forecast_horizon_days: int = Field(default=14, description="How many days ahead this forecast covers")
    trend: Literal["rising", "falling", "stable"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="Plain-language justification for the forecast")


class StockSignal(BaseModel):
    """Output of the Inventory Agent for a single SKU."""
    sku: str
    current_stock: int
    forecasted_demand_units: float = Field(description="Forecasted demand over the safety window")
    safety_stock_days: int
    days_of_cover: float = Field(description="How many days current stock will last at forecasted demand")
    reorder_needed: bool
    urgency: Literal["none", "low", "medium", "high", "critical"]
    reasoning: str


class SupplierChoice(BaseModel):
    """A supplier evaluated for a SKU."""
    supplier: str
    unit_price: float
    lead_time_days: int
    reliability_score: float
    min_order_qty: int
    score: float = Field(description="Composite score used to rank this supplier")


class DraftOrder(BaseModel):
    """Output of the Procurement Agent for a single SKU."""
    sku: str
    product_name: str
    quantity: int
    chosen_supplier: SupplierChoice
    alternatives_considered: list[SupplierChoice] = Field(default_factory=list)
    total_cost: float
    reasoning: str


class DeliveryPlan(BaseModel):
    """Output of the Delivery Agent for a single SKU's order."""
    sku: str
    carrier: str
    eta_days: int
    estimated_delivery_cost: float
    warehouse: str
    reasoning: str


class LineItemDecision(BaseModel):
    """Full bundle of everything decided about one SKU, shown to the human approver."""
    sku: str
    product_name: str
    forecast: ForecastSignal
    stock_signal: StockSignal
    draft_order: Optional[DraftOrder] = None
    delivery_plan: Optional[DeliveryPlan] = None


class ApprovalDecision(BaseModel):
    """Human approval response captured at the human-in-the-loop checkpoint."""
    approved: bool
    approver: str = "human_reviewer"
    reasoning: str
    skus_approved: list[str] = Field(default_factory=list)
    skus_rejected: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Final outcome after attempting to execute approved orders."""
    sku: str
    status: Literal["executed", "rejected", "skipped"]
    detail: str


def merge_dict(left: dict, right: dict) -> dict:
    """Reducer used by LangGraph to merge per-SKU dict outputs from parallel agent runs."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class SupplyChainState(TypedDict, total=False):
    """
    Shared graph state. Each specialist agent reads what it needs and writes
    its own structured slice back. Dict fields are keyed by SKU so multiple
    SKUs can flow through the same graph run.
    """
    skus: list[str]
    forecasts: Annotated[dict, merge_dict]
    stock_signals: Annotated[dict, merge_dict]
    skus_needing_reorder: list[str]
    draft_orders: Annotated[dict, merge_dict]
    delivery_plans: Annotated[dict, merge_dict]
    line_items: Annotated[dict, merge_dict]
    approval: Optional[ApprovalDecision]
    execution_results: Annotated[dict, merge_dict]
    audit_log: Annotated[list, operator.add]
