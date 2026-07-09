---
name: qa-exploratory
description: "Use when probing beyond the spec for bugs the test plan didn't anticipate. Charter-driven exploration, graceful degradation (kill DB, inject latency, partition), and recovery testing. Posts findings to the swarm blackboard."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, exploratory, charter, chaos, degradation, recovery]
    related_skills: [qa-protocol]
---

# QA Exploratory — find what the spec didn't anticipate

A **charter** is a one-sentence mission that bounds exploration: "Probe the file-upload feature for size, type, and encoding edge handling." You explore freely within the charter's scope, logging every unexpected behavior with evidence.

## Read your assignment

Your card body contains the exploration targets (1–2 high-risk areas) and the container image tag and port or workspace path.

## Charter-driven exploration

For each target, write a charter and spend a bounded effort (10–15 minutes) probing:

- "Probe the file-upload feature for size, type, and encoding edge handling"
- "Probe the auth flow for token expiry, refresh, and concurrent session behavior"
- "Probe the payment flow for partial failure, timeout, and retry scenarios"

Think creatively about combinations the spec didn't consider:
- **Feature interactions:** does feature A break when feature B is active?
- **State transitions:** what happens if you go from state X to state Z (skipping Y)?
- **Input combinations:** field A has unicode AND field B is empty AND field C is max length?
- **Timing:** request B arrives before request A finishes?
- **Edge of the spec:** what does the spec say about X? Nothing? Test X.

## Graceful degradation

Test that the artifact fails gracefully when things go wrong:

### Kill a dependency
```bash
DB_PID=$(pgrep -f "postgres\|mysql\|redis\|mongod" | head -1)
curl -s http://localhost:<port>/api/items & sleep 0.5 && kill -9 $DB_PID
curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/api/items
# Meaningful error, hang, or crash?
sudo systemctl start postgresql; sleep 2
curl -s http://localhost:<port>/api/items  # Should work again
```

### Inject latency
```bash
sudo tc qdisc add dev eth0 root netem delay 500ms
time curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/api/items
sudo tc qdisc del dev eth0 root
```

### Simulate partition
```bash
sudo iptables -A OUTPUT -d <dependency_ip> -j DROP
curl -s http://localhost:<port>/api/items
sudo iptables -D OUTPUT -d <dependency_ip> -j DROP
```

## Recovery

Test that the system self-heals:
```bash
kill -9 $(pgrep -f "node\|python\|go\|rust" | head -1)
podman restart <container-id>
curl -s http://localhost:<port>/api/items
# Data still there? Sessions preserved? In-flight operations lost?
```

## Post findings to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-exploratory \
  --body '[swarm:blackboard] {"key": "exploratory_findings", "value": {"charter": "file upload edge handling", "findings": [{"type": "unexpected_crash", "severity": "P1", "evidence": "..."}], "degradation": {"db_kill": "graceful", "latency": "timeout", "partition": "circuit_breaker"}, "recovery": "state_preserved"}}'
```

Complete with `kanban_complete(metadata={charters_executed: N, findings: [...], degradation_results: {...}, recovery_result: "..."})`.
