"""
graph.py
Implements roadmap Step 1 ("Map the Workflow") and the orchestration that
ties Steps 2-5 together into one running system.

Graph topology:

    demand_agent
         |
    inventory_agent
         |
    (conditional: any SKU need reorder?)
       /        \\
   procurement   prepare_for_approval (nothing to do, skip straight there)
       |
   delivery_agent
       |
   prepare_for_approval
       |
   human_approval  <-- graph PAUSES here (interrupt) until a human responds
       |
   execute_orders
       |
      END

A checkpointer (MemorySaver) is required for the interrupt/resume pattern:
LangGraph needs to persist state across the pause so the same run can be
resumed later with the human's decision.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from state import SupplyChainState
from agents.demand_agent import demand_agent
from agents.inventory_agent import inventory_agent
from agents.procurement_agent import procurement_agent
from agents.delivery_agent import delivery_agent
from approval import prepare_for_approval, human_approval_node, execute_orders_node


def _route_after_inventory(state: SupplyChainState) -> str:
    """Conditional edge: skip procurement/delivery entirely if nothing needs reordering."""
    if state.get("skus_needing_reorder"):
        return "procurement_agent"
    return "prepare_for_approval"


def build_graph():
    workflow = StateGraph(SupplyChainState)

    workflow.add_node("demand_agent", demand_agent)
    workflow.add_node("inventory_agent", inventory_agent)
    workflow.add_node("procurement_agent", procurement_agent)
    workflow.add_node("delivery_agent", delivery_agent)
    workflow.add_node("prepare_for_approval", prepare_for_approval)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("execute_orders", execute_orders_node)

    workflow.set_entry_point("demand_agent")
    workflow.add_edge("demand_agent", "inventory_agent")
    workflow.add_conditional_edges(
        "inventory_agent",
        _route_after_inventory,
        {"procurement_agent": "procurement_agent", "prepare_for_approval": "prepare_for_approval"},
    )
    workflow.add_edge("procurement_agent", "delivery_agent")
    workflow.add_edge("delivery_agent", "prepare_for_approval")
    workflow.add_edge("prepare_for_approval", "human_approval")
    workflow.add_edge("human_approval", "execute_orders")
    workflow.add_edge("execute_orders", END)

    return workflow.compile(checkpointer=MemorySaver(serde=JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("state", "ForecastSignal"),
            ("state", "StockSignal"),
            ("state", "SupplierChoice"),
            ("state", "DraftOrder"),
            ("state", "DeliveryPlan"),
            ("state", "ApprovalDecision"),
        ]
    )))
