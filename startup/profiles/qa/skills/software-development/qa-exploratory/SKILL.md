---
name: qa-exploratory
description: "Use when probing beyond the spec for bugs the test plan didn't anticipate. Charter-driven creative exploration, graceful degradation testing (kill DB, inject latency, simulate partition), and recovery testing. Posts findings to the swarm blackboard. Loaded by the exploratory worker in a QA swarm."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, exploratory, charter, chaos, degradation, recovery, sbet]
    related_skills: [qa-protocol]
---

# QA Exploratory — find what the spec didn't anticipate

Claims, journeys, and security test what the spec says and the standard dimensions. You find what the spec _didn't anticipate_ — bugs in the gaps between features, in unexpected input combinations, in edge interactions.

This is QA's irreplaceable differentiator. Scripted automation is commodity dev work now. Intelligent, creative exploration is the surviving human-QA superpower.

## Read your assignment

Your card body contains:
- The exploration targets (1-2 high-risk areas from the orchestrator's plan)
- The container image tag and port (or workspace path)

## Session-Based Exploratory Testing (SBET)

For each exploration target, write a **charter** — a one-sentence mission bounding the probe:

- "Probe the file-upload feature for size, type, and encoding edge handling"
- "Probe the auth flow for token expiry, refresh, and concurrent session behavior"
- "Probe the payment flow for partial failure, timeout, and retry scenarios"

Spend a bounded effort per charter (10-15 minutes). Explore freely within the charter's scope. Log every unexpected behavior with evidence.

## Graceful degradation testing

Test that the artifact **fails gracefully** when things go wrong:

### Kill a dependency
```bash
# Find the DB process
DB_PID=$(pgrep -f "postgres\|mysql\|redis\|mongod" | head -1)

# Fire a request, kill DB mid-flight
curl -s http://localhost:<port>/api/items &
sleep 0.5
kill -9 $DB_PID

# Does the API return a meaningful error, or hang, or crash?
curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/api/items

# Restart and verify recovery
sudo systemctl start postgresql
sleep 2
curl -s http://localhost:<port>/api/items  # Should work again
```

### Inject latency
```bash
# Add 500ms latency to outbound network
sudo tc qdisc add dev eth0 root netem delay 500ms
time curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/api/items
# Does it timeout gracefully or hang?
sudo tc qdisc del dev eth0 root
```

### Simulate network partition
```bash
sudo iptables -A OUTPUT -d <dependency_ip> -j DROP
curl -s http://localhost:<port>/api/items
# Does the circuit breaker trip? Does it show a fallback?
sudo iptables -D OUTPUT -d <dependency_ip> -j DROP
```

## Recovery testing

Test that the system **self-heals** after failure:

```bash
# Kill the process mid-operation
kill -9 $(pgrep -f "node\|python\|go\|rust" | head -1)

# Restart it
# (restart command depends on the artifact — container restart, systemd, etc.)
podman restart <container-id>
# or: sudo systemctl restart <service>

# Verify state is intact
curl -s http://localhost:<port>/api/items
# Is data still there? Are sessions preserved? Are in-flight operations lost?
```

## What to explore

Think creatively about combinations the spec didn't consider:

- **Feature interactions:** does feature A break when feature B is active?
- **State transitions:** what happens if you go from state X to state Z (skipping Y)?
- **Input combinations:** what if field A has unicode AND field B is empty AND field C is max length?
- **Timing:** what if request B arrives before request A finishes?
- **Edge of the spec:** what does the spec say about X? Nothing? Test X.
- **Error messages:** are they informative? Do they leak information?
- **Rate of change:** what if you change a setting 100 times rapidly?

## Post findings to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-exploratory \
  --body '[swarm:blackboard] {"key": "exploratory_findings", "value": {"charter": "file upload edge handling", "findings": [{"type": "unexpected_crash", "severity": "P1", "evidence": "..."}], "degradation": {"db_kill": "graceful (500 error)", "latency": "timeout after 10s", "partition": "circuit breaker tripped"}}}'
```

## Complete with metadata

```python
kanban_complete(
    summary="Exploratory: 1 charter executed, 2 findings. Degradation: DB kill=graceful, latency=timeout, partition=circuit breaker. Recovery: state preserved after restart.",
    metadata={
        "charters_executed": 1,
        "findings": [{"severity": "P1", "type": "unexpected_crash", "evidence": "..."}],
        "degradation_results": {"db_kill": "graceful", "latency": "timeout", "partition": "circuit_breaker"},
        "recovery_result": "state_preserved"
    }
)
```
