"""
approval.py
Implements roadmap Step 5: "Add Human Approval."

The graph pauses here (using LangGraph's `interrupt`) and hands the
consolidated, explainable proposal to a human. Execution does not
continue until a real approval decision is returned and the graph is
resumed with `Command(resume=...)`. This is what makes the system
"human-controlled" rather than fully autonomous, matching the
infographic's subtitle: "Replenishment to Human-Controlled."

Risk-based auto-routing: low-cost, low-risk line items could be
auto-approved in a real deployment, but this demo always routes every
SKU through the human checkpoint to make the human-in-the-loop pattern
explicit and easy to inspect.
"""

from langgraph.types import interrupt
from state import SupplyChainState, ApprovalDecision
from explainability import build_line_items, format_approval_report
from tools import place_supplier_order


def prepare_for_approval(state: SupplyChainState) -> dict:
    """Consolidate agent outputs into reviewable bundles before pausing for a human."""
    line_items = build_line_items(state)
    return {"line_items": line_items, "audit_log": ["[Explainability] Built consolidated approval report."]}


def human_approval_node(state: SupplyChainState) -> dict:
    """Pause the graph and wait for a human decision on the proposal."""
    if not state.get("skus_needing_reorder"):
        decision = ApprovalDecision(approved=True, reasoning="No SKUs required action this cycle.")
        return {"approval": decision, "audit_log": ["[Approval] Auto-cleared: nothing pending."]}

    report = format_approval_report(state)
    human_response = interrupt({
        "report": report,
        "skus_pending": state["skus_needing_reorder"],
        "instructions": (
            "Reply with a dict like {'approved': true, 'skus_approved': [...], "
            "'skus_rejected': [...], 'reasoning': '...'} to resume the graph."
        ),
    })

    decision = ApprovalDecision(**human_response)
    return {
        "approval": decision,
        "audit_log": [f"[Approval] Human decision: approved={decision.approved} "
                       f"({len(decision.skus_approved)} approved, {len(decision.skus_rejected)} rejected)."],
    }


def execute_orders_node(state: SupplyChainState) -> dict:
    """Implements the final 'Execute' step of the workflow-at-a-glance row."""
    approval = state.get("approval")
    results = {}

    if approval is None or (not approval.skus_approved and not approval.approved):
        for sku in state.get("skus_needing_reorder", []):
            results[sku] = {"sku": sku, "status": "rejected", "detail": "Not approved by reviewer."}
        return {"execution_results": results, "audit_log": ["[Execution] No orders executed (rejected)."]}

    approved_skus = approval.skus_approved or state.get("skus_needing_reorder", [])
    for sku in state.get("skus_needing_reorder", []):
        if sku not in approved_skus:
            results[sku] = {"sku": sku, "status": "rejected", "detail": "Excluded by reviewer decision."}
            continue
        order = state["draft_orders"].get(sku)
        if not order:
            results[sku] = {"sku": sku, "status": "skipped", "detail": "No draft order was generated."}
            continue
        confirmation = place_supplier_order(sku, order.chosen_supplier.supplier, order.quantity)
        results[sku] = {
            "sku": sku,
            "status": "executed",
            "detail": f"PO {confirmation['confirmation_id']} submitted to {order.chosen_supplier.supplier} "
                      f"for {order.quantity} units.",
        }

    executed = sum(1 for r in results.values() if r["status"] == "executed")
    return {
        "execution_results": results,
        "audit_log": [f"[Execution] {executed} order(s) submitted to suppliers."],
    }
