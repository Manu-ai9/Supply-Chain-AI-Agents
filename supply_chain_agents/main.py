"""
main.py
CLI demo runner for the Supply Chain AI Agent System.

Run with:
    python main.py

This drives the graph from Demand -> Inventory -> (conditionally)
Procurement -> Delivery -> Explainability -> Human Approval -> Execution,
printing each agent's output as it happens, then pausing for a real
decision from you at the approval checkpoint -- demonstrating the
human-in-the-loop interrupt/resume pattern live.

Set ANTHROPIC_API_KEY in your environment (see .env.example) to have
agents reason with Claude instead of the deterministic fallback heuristics.
"""

from langgraph.types import Command
from graph import build_graph
from llm_utils import llm_available
from tools import active_backend


def _print_header(title: str):
    print(f"\n{'-' * 78}\n{title}\n{'-' * 78}")


def run():
    graph = build_graph()
    config = {"configurable": {"thread_id": "demo-run-1"}}

    mode = "LLM-driven (Claude)" if llm_available() else "Rule-based fallback (no ANTHROPIC_API_KEY set)"
    backend = active_backend()
    _print_header(f"SUPPLY CHAIN AI AGENT SYSTEM -- reasoning: {mode} | data backend: {backend}")

    for event in graph.stream({}, config=config, stream_mode="updates"):
        for node_name, payload in event.items():
            if node_name == "__interrupt__":
                continue
            log_lines = payload.get("audit_log", []) if isinstance(payload, dict) else []
            for line in log_lines:
                print(line)

    state = graph.get_state(config)
    if state.next and "human_approval" in state.next:
        interrupt_payload = state.tasks[0].interrupts[0].value
        print(interrupt_payload["report"])
        pending = interrupt_payload["skus_pending"]

        if not pending:
            decision_input = {"approved": True, "reasoning": "Nothing pending."}
        else:
            print("\nApprove this proposal? Options: [a]ll / [n]one / [s]elect specific SKUs")
            choice = input("> ").strip().lower()

            if choice == "a":
                decision_input = {"approved": True, "skus_approved": pending, "skus_rejected": [],
                                   "reasoning": "Reviewer approved all proposed orders."}
            elif choice == "n":
                decision_input = {"approved": False, "skus_approved": [], "skus_rejected": pending,
                                   "reasoning": "Reviewer rejected all proposed orders."}
            else:
                print(f"Pending SKUs: {pending}")
                raw = input("Enter comma-separated SKUs to APPROVE (rest will be rejected): ").strip()
                approved = [s.strip() for s in raw.split(",") if s.strip() in pending]
                rejected = [s for s in pending if s not in approved]
                decision_input = {"approved": len(approved) > 0, "skus_approved": approved,
                                   "skus_rejected": rejected,
                                   "reasoning": f"Reviewer selectively approved {len(approved)} of {len(pending)} SKUs."}

        _print_header("RESUMING GRAPH WITH HUMAN DECISION")
        for event in graph.stream(Command(resume=decision_input), config=config, stream_mode="updates"):
            for node_name, payload in event.items():
                log_lines = payload.get("audit_log", []) if isinstance(payload, dict) else []
                for line in log_lines:
                    print(line)

    final_state = graph.get_state(config).values
    _print_header("EXECUTION RESULTS")
    for sku, res in final_state.get("execution_results", {}).items():
        print(f"  {sku}: {res['status'].upper()} -- {res['detail']}")

    _print_header("FULL AUDIT TRAIL")
    for line in final_state.get("audit_log", []):
        print(" ", line)


if __name__ == "__main__":
    run()
