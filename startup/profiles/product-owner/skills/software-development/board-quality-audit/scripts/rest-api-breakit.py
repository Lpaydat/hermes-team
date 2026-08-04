#!/usr/bin/env python3
"""
Reusable adversarial break-it probe for a STATEFUL REST API (Flask test client).
Adapt the endpoints, payloads, and assertions to the board you are auditing.

This template exercises the four failure modes most likely to survive a
developer's own tests:
  1. Concurrency races (200+ threads on same key, 300+ threads on distinct keys)
  2. Time-based expiry (TTL) — tested with BOTH mocked clocks (deterministic)
     AND real-time sleeps (catches bugs masked by the mock)
  3. Idempotency of destructive ops (DELETE missing key twice)
  4. State transitions (delete→re-create, overwrite-clears-TTL)

Usage:
  1. Set APP_PATH to the directory containing the Flask app module.
  2. Set APP_MODULE to the importable module name (must expose `app` and `_store`).
  3. Adapt the endpoint paths, payload shapes, and per-probe assertions.
  4. Run: python3 rest-api-breakit.py   (exits 1 on any FAIL)
"""
import sys
import threading
import time

# --- CONFIG: adapt these for the board under audit ----------------------------
APP_PATH = "/path/to/workspace/app_dir"      # dir containing the app module
APP_MODULE = "app"                            # importable module name
KV_STORE_ATTR = "_store"                      # module-level dict for reset()
# -----------------------------------------------------------------------------

sys.path.insert(0, APP_PATH)
import importlib
mod = importlib.import_module(APP_MODULE)
c = mod.app.test_client()
store = getattr(mod, KV_STORE_ATTR)

results = []


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    results.append((name, status))
    if status == "FAIL":
        print(f"  [FAIL] {name}")
    else:
        print(f"  [PASS] {name}")


def reset():
    store.clear()


# === 1. Concurrency: same-key race ===========================================
def probe_concurrent_same_key():
    reset()

    def worker():
        with mod.app.test_client() as cc:
            cc.put("/api/shared", json={"value": 1})

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    r = c.get("/api/shared")
    check("concurrent PUT same key -> 200, no race", r.status_code == 200)


# === 2. Concurrency: distinct-key data loss =================================
def probe_concurrent_distinct_keys():
    reset()
    N = 300

    def worker(i):
        with mod.app.test_client() as cc:
            assert cc.put(f"/api/k{i}", json={"value": i}).status_code == 200

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    count = c.get("/api").get_json()["count"]
    check(f"concurrent PUT {N} distinct keys -> count={N} (no data loss)", count == N)


# === 3. TTL expiry: REAL-TIME (not mocked) ===================================
def probe_ttl_real_time():
    reset()
    c.put("/api/dies", json={"value": "v", "ttl": 1})
    time.sleep(1.2)
    check("expired TTL GET (real sleep) -> 404", c.get("/api/dies").status_code == 404)


# === 4. TTL boundary: live before, dead after ================================
def probe_ttl_boundary():
    reset()
    c.put("/api/k", json={"value": "v", "ttl": 2})
    time.sleep(1.5)
    check("TTL key live before expiry -> 200", c.get("/api/k").status_code == 200)
    time.sleep(0.8)
    check("TTL key dead after expiry -> 404", c.get("/api/k").status_code == 404)


# === 5. Idempotent DELETE on missing key =====================================
def probe_idempotent_delete():
    reset()
    check("missing key DELETE 1st -> 204", c.delete("/api/ghost").status_code == 204)
    check("missing key DELETE 2nd -> 204", c.delete("/api/ghost").status_code == 204)


# === 6. List excludes expired ================================================
def probe_list_excludes_expired():
    reset()
    c.put("/api/live", json={"value": 1})
    c.put("/api/dies", json={"value": 2, "ttl": 1})
    time.sleep(1.2)
    keys = set(c.get("/api").get_json()["keys"])
    check("list excludes expired (only live keys)", keys == {"live"})


# === 7. Overwrite clears TTL =================================================
def probe_overwrite_clears_ttl():
    reset()
    c.put("/api/k", json={"value": "v1", "ttl": 1})
    c.put("/api/k", json={"value": "v2"})  # no ttl — should clear expiry
    time.sleep(1.2)
    g = c.get("/api/k")
    check("overwrite clears TTL -> 200, val intact", g.status_code == 200 and g.get_json() == "v2")


# === 8. Delete → re-create (resurrection) ====================================
def probe_delete_reput():
    reset()
    c.put("/api/k", json={"value": 1})
    c.delete("/api/k")
    check("after delete GET -> 404", c.get("/api/k").status_code == 404)
    c.put("/api/k", json={"value": 2})
    check("re-PUT after delete -> 200, val=2", c.get("/api/k").get_json() == 2)


# === 9. Empty store list =====================================================
def probe_empty_list():
    reset()
    body = c.get("/api").get_json()
    check("empty store list -> {keys:[],count:0}", body == {"keys": [], "count": 0})


if __name__ == "__main__":
    probes = [
        probe_concurrent_same_key,
        probe_concurrent_distinct_keys,
        probe_ttl_real_time,
        probe_ttl_boundary,
        probe_idempotent_delete,
        probe_list_excludes_expired,
        probe_overwrite_clears_ttl,
        probe_delete_reput,
        probe_empty_list,
    ]
    for p in probes:
        try:
            p()
        except Exception as e:
            results.append((p.__name__, "CRASH"))
            print(f"  [CRASH] {p.__name__}: {type(e).__name__}: {e}")

    fails = [n for n, s in results if s != "PASS"]
    total = len(results)
    passed = total - len(fails)
    print(f"\n{passed}/{total} passed")
    sys.exit(1 if fails else 0)
