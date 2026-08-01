"""Probe: does a card_completed trigger fire on cards created by a workflow with explicit edges?

Approach C composes goal workflows via card handoffs: construction.json (multi-agent,
explicit edges) completes its verifier node card with verdict=PASS -> qa-loop.json
(card_completed trigger on verifier/PASS) should start. But runtime.py:1783-1800
blocks cross-workflow triggers when the card's parent workflow has explicit edges.

This probe runs both cases: edges declared vs implicit depends_on only.
"""
import sys
sys.path.insert(0, "/home/lpaydat/.hermes-teams/startup/scripts")
sys.path.insert(0, "/home/lpaydat/.hermes-teams/startup/scripts/workflow_engine")
from test_composition import FakeWorld, get_instance_count


def make_construction(use_edges: bool) -> dict:
    t = {
        "id": "construction",
        "name": "Construction",
        "nodes": [
            {"id": "dev", "profile": "developer", "skill": "developer-loop",
             "body_template": "build it for ${trigger.bead_id}"},
            {"id": "verify", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "review", "depends_on": ["dev"]},
        ],
    }
    if use_edges:
        t["edges"] = [{"from": "dev", "to": "verify"}]
    return t


def qa_loop() -> dict:
    return {
        "id": "qa-loop",
        "name": "QA Re-test",
        "trigger": {"source": "card_completed",
                    "condition": {"assignee": "verifier", "status": "done",
                                  "metadata.verdict": "PASS"}},
        "nodes": [{"id": "qa_retest", "profile": "qa", "skill": "live-testing",
                   "body_template": "re-test ${trigger.card_id}"}],
    }


def run_case(use_edges: bool):
    world = FakeWorld()
    try:
        world.add_template(make_construction(use_edges))
        world.add_template(qa_loop())
        world.start("construction", context={"bead_id": "b1"})
        world.tick()  # dispatch dev

        dev = world.find_card_by_assignee("developer")
        assert dev, "dev card not created"
        world.complete_card(dev, metadata={"branch": "feat/x"})
        world.tick()  # dev DONE -> verify dispatched

        ver = world.find_card_by_assignee("verifier")
        assert ver, "verifier card not created"
        # Record the idempotency key the engine gave the verifier card
        import sqlite3
        conn = sqlite3.connect(str(world.board_db))
        idem = conn.execute("SELECT idempotency_key FROM tasks WHERE id = ?",
                            (ver,)).fetchone()[0]
        conn.close()

        world.complete_card(ver, metadata={"verdict": "PASS", "merged": True})
        actions = world.tick()  # verify DONE -> triggers checked same tick

        started = [a for a in actions if "STARTED" in a and "qa-loop" in a]
        qa_instances = get_instance_count(world.state_db_path, "qa-loop")
        print(f"edges={use_edges} | verifier card idem_key={idem}")
        print(f"  qa-loop instances: {qa_instances} | trigger actions: {started}")
        print(f"  actions: {[a[:90] for a in actions]}")
        return qa_instances
    finally:
        world.cleanup()


if __name__ == "__main__":
    print("=== CASE 1: construction WITH explicit edges (Approach C shape) ===")
    with_edges = run_case(True)
    print("\n=== CASE 2: construction WITHOUT edges (implicit depends_on, Approach B shape) ===")
    without_edges = run_case(False)
    print(f"\nRESULT: QA triggered with edges={with_edges > 0}, without edges={without_edges > 0}")
