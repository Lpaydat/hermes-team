Gateway-less profile: sessions spawn per kanban card (`hermes -p architect` via the gateway-hosted dispatcher) and per intercom spawn-send (offline spawner). No systemd unit exists for this profile by design — promotion to a full gateway is deferred until standing T3 cadence demands it.
§
Intercom addressing: sessions spawned by the offline spawner can register under a degraded team identity, so bare profile names may route to the wrong team. Always use the qualified form `startup/<profile>` when sending or replying over intercom.
§
Boundary: I own decisions that outlive a slice (boundaries, contracts, data models, stack, cross-cutting patterns); tech-lead owns slice construction. Conflicts resolve to the ADR; changing an ADR requires an architecture ticket — never a dev-loop card.
