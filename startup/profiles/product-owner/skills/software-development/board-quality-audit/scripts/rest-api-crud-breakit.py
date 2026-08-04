#!/usr/bin/env python3
"""
Reusable adversarial break-it probe for a CRUD RESOURCE REST API (Flask).

Unlike rest-api-breakit.py (which targets stateful KV stores with TTL/PUT
semantics), this script targets resource-oriented APIs: POST create, GET list
(with filtering/sorting), GET single, DELETE, and aggregation/summary endpoints.
Think: Expense Tracker, Todo List, Inventory Manager — any spec that defines a
resource with validation rules, query-param filters, and computed aggregates.

The probes cover the failure modes most likely to survive both dev and verify:
  1. Input validation (negative/zero/NaN/Infinity/boolean/non-numeric amount,
     invalid date format AND invalid calendar date, missing fields, empty body,
     malformed JSON, type mismatches)
  2. Filtering correctness (category match/no-match, date range inclusive,
     boundary dates start==end, reversed range start>end, start-only, end-only)
  3. Sorting (default direction, explicit sort, invalid sort value)
  4. Aggregation/summary (empty database, float precision, by_category, avg)
  5. CRUD lifecycle (create→read→list→summary→delete→verify-gone, id reuse)
  6. Production mode (real HTTP server, no test_client, no TESTING flag)

Usage:
  1. Set APP_PATH to the directory containing the Flask app module.
  2. Set APP_MODULE to the importable module name (must expose `app` and
     `reset_storage`).
  3. Adapt the endpoint paths, payload shapes, and assertions.
  4. Run: python3 rest-api-crud-breakit.py   (exits 1 on any FAIL)

See also: scripts/rest-api-breakit.py for KV-store/TTL APIs.
"""
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.request

# --- CONFIG: adapt these for the board under audit ----------------------------
APP_PATH = "/path/to/workspace/app_dir"      # dir containing the app module
APP_MODULE = "app"                            # importable module name
RESET_FUNC = "reset_storage"                   # function to clear in-memory state
# For production-mode testing:
PROD_HOST = "127.0.0.1"
PROD_PORT = 18999
# -----------------------------------------------------------------------------


def _load_client():
    sys.path.insert(0, APP_PATH)
    import importlib
    mod = importlib.import_module(APP_MODULE)
    return mod


def _reset(mod):
    getattr(mod, RESET_FUNC)()


def _http_req(host, port, method, path, data=None):
    """Real HTTP request (no test_client). Returns (status, body_str)."""
    url = f"http://{host}:{port}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


results = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((name, status))
    tag = f"  [{status}] {name}"
    if detail and not cond:
        tag += f" — {detail}"
    print(tag)


def valid(**ov):
    """A valid payload for the Expense Tracker. Adapt fields per spec."""
    p = {"amount": 10, "category": "food", "description": "lunch", "date": "2024-01-01"}
    p.update(ov)
    return p


# === 1. Input validation probes ==============================================

def probe_input_validation(mod):
    c = mod.app.test_client()
    _reset(mod)

    # Negative amount -> 400
    r = c.post("/api/expenses", json=valid(amount=-5))
    check("negative amount -> 400", r.status_code == 400)

    # Zero amount -> 400 (zero is not positive)
    r = c.post("/api/expenses", json=valid(amount=0))
    check("zero amount -> 400", r.status_code == 400)

    # NaN amount -> 400 (NaN bypasses `<= 0` check in Python)
    r = c.post("/api/expenses", json=valid(amount=float("nan")))
    check("NaN amount -> 400", r.status_code == 400, str(r.get_json()))

    # Infinity amount -> 400
    r = c.post("/api/expenses", json=valid(amount=float("inf")))
    check("Infinity amount -> 400", r.status_code == 400)

    # Boolean amount -> 400 (bool is subclass of int)
    r = c.post("/api/expenses", json=valid(amount=True))
    check("boolean amount -> 400", r.status_code == 400)

    # Non-numeric string amount -> 400
    r = c.post("/api/expenses", json=valid(amount="abc"))
    check("string amount -> 400", r.status_code == 400)

    # List amount -> 400
    r = c.post("/api/expenses", json=valid(amount=[10]))
    check("list amount -> 400", r.status_code == 400)

    # Invalid date format -> 400
    for d in ["2024/01/01", "01-01-2024", "2024-1-1", "notadate", "20240101"]:
        r = c.post("/api/expenses", json=valid(date=d))
        check(f"invalid date format {d!r} -> 400", r.status_code == 400)

    # Invalid CALENDAR date -> 400 (format is valid YYYY-MM-DD but not real)
    for d in ["2024-02-30", "2024-13-01", "2024-01-00", "2023-02-29"]:
        r = c.post("/api/expenses", json=valid(date=d))
        check(f"invalid calendar date {d!r} -> 400", r.status_code == 400)

    # Feb 29 on LEAP year -> 201 (should be accepted)
    r = c.post("/api/expenses", json=valid(date="2024-02-29"))
    check("Feb 29 leap year -> 201", r.status_code == 201)

    # Missing each required field -> 400
    for field in ("amount", "category", "description", "date"):
        p = valid()
        del p[field]
        r = c.post("/api/expenses", json=p)
        check(f"missing {field} -> 400", r.status_code == 400)

    # Empty body -> 400
    r = c.post("/api/expenses", json={})
    check("empty JSON body -> 400", r.status_code == 400)

    # Malformed JSON -> 400
    r = c.post("/api/expenses", data="not json", content_type="application/json")
    check("malformed JSON body -> 400", r.status_code == 400)

    # Empty category -> 400
    r = c.post("/api/expenses", json=valid(category=""))
    check("empty category -> 400", r.status_code == 400)

    # Category as int -> 400
    r = c.post("/api/expenses", json=valid(category=5))
    check("category as int -> 400", r.status_code == 400)

    # Date as int -> 400
    r = c.post("/api/expenses", json=valid(date=20240101))
    check("date as int -> 400", r.status_code == 400)


# === 2. Filtering probes =====================================================

def probe_filtering(mod):
    c = mod.app.test_client()
    _reset(mod)

    def post(**ov):
        r = c.post("/api/expenses", json=valid(**ov))
        assert r.status_code == 201, r.get_json()
        return r.get_json()

    # Category filter: match + no-match
    food = post(category="food")
    travel = post(category="travel", amount=5)
    r = c.get("/api/expenses?category=food")
    ids = {e["id"] for e in r.get_json()}
    check("category filter returns only matches", ids == {food["id"]})

    r = c.get("/api/expenses?category=nonexistent")
    check("category filter no-match -> empty array", r.get_json() == [])

    # Date range inclusive
    _reset(mod)
    in_range = post(date="2024-06-15")
    too_old = post(date="2023-12-31")
    too_new = post(date="2025-01-01")
    r = c.get("/api/expenses?start=2024-01-01&end=2024-12-31")
    ids = {e["id"] for e in r.get_json()}
    check("date range inclusive (only in-range)", ids == {in_range["id"]})

    # Boundary dates: start and end themselves are included
    _reset(mod)
    on_start = post(date="2024-01-01")
    on_end = post(date="2024-12-31")
    r = c.get("/api/expenses?start=2024-01-01&end=2024-12-31")
    ids = {e["id"] for e in r.get_json()}
    check("boundary dates included", ids == {on_start["id"], on_end["id"]})

    # Same start==end returns exactly that day
    _reset(mod)
    post(date="2024-06-15")
    post(date="2024-06-16")
    r = c.get("/api/expenses?start=2024-06-15&end=2024-06-15")
    check("same start/end returns exactly 1 day", len(r.get_json()) == 1)

    # Reversed range (start > end) -> empty, not error
    _reset(mod)
    post(date="2024-06-15")
    r = c.get("/api/expenses?start=2024-12-31&end=2024-01-01")
    check("reversed date range -> 200 empty", r.status_code == 200 and r.get_json() == [])

    # Start-only and end-only both filter
    _reset(mod)
    post(date="2023-01-01")
    post(date="2024-06-15")
    r = c.get("/api/expenses?start=2024-01-01")
    check("start-only filters", len(r.get_json()) == 1)

    _reset(mod)
    post(date="2024-06-15")
    post(date="2025-01-01")
    r = c.get("/api/expenses?end=2024-12-31")
    check("end-only filters", len(r.get_json()) == 1)

    # Invalid date format in filter params -> 400
    for param in ("start", "end"):
        r = c.get(f"/api/expenses?{param}=2024/01/01")
        check(f"invalid {param} date format -> 400", r.status_code == 400)
        r = c.get(f"/api/expenses?{param}=2024-02-30")
        check(f"invalid {param} calendar date -> 400", r.status_code == 400)


# === 3. Sorting probes =======================================================

def probe_sorting(mod):
    c = mod.app.test_client()
    _reset(mod)

    def post(**ov):
        r = c.post("/api/expenses", json=valid(**ov))
        assert r.status_code == 201
        return r.get_json()

    # Default sort is date DESCENDING
    post(date="2024-01-01")
    post(date="2023-05-01")
    post(date="2024-06-15")
    dates = [e["date"] for e in c.get("/api/expenses").get_json()]
    check("default sort = date desc", dates == ["2024-06-15", "2024-01-01", "2023-05-01"])

    # Explicit sort=date also descending
    _reset(mod)
    post(date="2024-01-01")
    post(date="2024-06-15")
    dates = [e["date"] for e in c.get("/api/expenses?sort=date").get_json()]
    check("sort=date -> desc", dates == ["2024-06-15", "2024-01-01"])

    # sort=amount is ascending
    _reset(mod)
    post(amount=50)
    post(amount=10)
    post(amount=30)
    amounts = [e["amount"] for e in c.get("/api/expenses?sort=amount").get_json()]
    check("sort=amount -> asc", amounts == [10, 30, 50])

    # Invalid sort value -> 400
    for s in ["name", "asc", ""]:
        r = c.get(f"/api/expenses?sort={s}")
        check(f"invalid sort={s!r} -> 400", r.status_code == 400)

    # Combined filter + sort
    _reset(mod)
    food_a = post(category="food", amount=100, date="2024-03-01")
    post(category="travel", amount=50, date="2024-04-01")
    post(category="food", amount=20, date="2025-01-01")
    food_b = post(category="food", amount=5, date="2024-02-15")
    r = c.get("/api/expenses?category=food&start=2024-01-01&end=2024-12-31&sort=amount")
    ids = [e["id"] for e in r.get_json()]
    check("combined filter+sort", ids == [food_b["id"], food_a["id"]])


# === 4. Summary / aggregation probes ========================================

def probe_summary(mod):
    c = mod.app.test_client()
    _reset(mod)

    def post(**ov):
        r = c.post("/api/expenses", json=valid(**ov))
        assert r.status_code == 201
        return r.get_json()

    # Empty database summary
    r = c.get("/api/summary")
    check("empty summary -> zeros",
          r.get_json() == {"total": 0, "by_category": {}, "count": 0, "avg_amount": 0})

    # With data
    post(amount=100, category="food")
    post(amount=50, category="transport")
    body = c.get("/api/summary").get_json()
    check("summary total", body["total"] == 150)
    check("summary by_category", body["by_category"] == {"food": 100, "transport": 50})
    check("summary count", body["count"] == 2)
    check("summary avg", abs(body["avg_amount"] - 75) < 0.001)

    # Summary respects deletions
    _reset(mod)
    a = post(amount=100, category="food")
    post(amount=50, date="2024-02-02")
    c.delete(f"/api/expenses/{a['id']}")
    body = c.get("/api/summary").get_json()
    check("summary after delete", body["count"] == 1 and body["total"] == 50)

    # Summary date range
    _reset(mod)
    post(amount=10, date="2023-12-31")
    post(amount=20, date="2024-06-15")
    post(amount=30, date="2025-01-01")
    body = c.get("/api/summary?start=2024-01-01&end=2024-12-31").get_json()
    check("summary date range", body["count"] == 1 and body["total"] == 20)

    # Invalid date in summary range -> 400
    r = c.get("/api/summary?start=2024-02-30")
    check("summary invalid calendar date -> 400", r.status_code == 400)


# === 5. CRUD lifecycle + id reuse ============================================

def probe_crud_lifecycle(mod):
    c = mod.app.test_client()
    _reset(mod)

    def post(**ov):
        r = c.post("/api/expenses", json=valid(**ov))
        assert r.status_code == 201
        return r.get_json()

    # Full cycle: create → read → list → summary → delete → gone
    created = post(amount=42, category="test", description="cycle", date="2024-06-15")
    check("GET single after POST", c.get(f"/api/expenses/{created['id']}").get_json() == created)
    check("list shows 1 item", len(c.get("/api/expenses").get_json()) == 1)
    check("summary reflects item", c.get("/api/summary").get_json()["total"] == 42)
    check("DELETE -> 204", c.delete(f"/api/expenses/{created['id']}").status_code == 204)
    check("GET after delete -> 404", c.get(f"/api/expenses/{created['id']}").status_code == 404)
    check("list empty after delete", c.get("/api/expenses").get_json() == [])
    check("summary empty after delete", c.get("/api/summary").get_json()["count"] == 0)

    # Double delete: first 204, second 404
    _reset(mod)
    item = post()
    check("double delete 1st -> 204", c.delete(f"/api/expenses/{item['id']}").status_code == 204)
    check("double delete 2nd -> 404", c.delete(f"/api/expenses/{item['id']}").status_code == 404)

    # IDs not reused after delete
    _reset(mod)
    first = post()
    second = post()
    c.delete(f"/api/expenses/{first['id']}")
    third = post()
    check("id not reused after delete", third["id"] > second["id"])

    # Non-int / negative / zero id paths
    check("GET /api/expenses/abc -> 404", c.get("/api/expenses/abc").status_code == 404)
    check("GET /api/expenses/0 -> 404", c.get("/api/expenses/0").status_code == 404)
    check("DELETE /api/expenses/abc -> 404", c.delete("/api/expenses/abc").status_code == 404)

    # Unknown method / route
    check("PUT -> 405", c.put("/api/expenses/1").status_code == 405)
    check("unknown route -> 404", c.get("/api/unknown").status_code == 404)


# === 6. Delimiter injection in string fields ================================

def probe_delimiter_injection(mod):
    """Inject control chars / delimiters into string fields. For in-memory
    stores with no SQL backend, the expectation is verbatim storage (no
    corruption, no truncation). For SQL-backed stores, assert no injection."""
    c = mod.app.test_client()
    _reset(mod)

    # Null byte in category
    r = c.post("/api/expenses", json=valid(category="fo\x00od"))
    check("null byte in category stored", r.status_code == 201 and r.get_json()["category"] == "fo\x00od")

    # Tab in category
    r = c.post("/api/expenses", json=valid(category="foo\tbar"))
    check("tab in category stored", r.status_code == 201 and r.get_json()["category"] == "foo\tbar")

    # Newline in description
    r = c.post("/api/expenses", json=valid(description="a\nb\tc"))
    check("newline+tab in description stored", r.status_code == 201)

    # SQL-like string (for SQL-backed stores, this should be safe; for
    # in-memory, it's just a string)
    r = c.post("/api/expenses", json=valid(category="food'; DROP TABLE--"))
    check("SQL-like string stored verbatim", r.status_code == 201)

    # Unicode
    r = c.post("/api/expenses", json=valid(category="食物", description="タクシー🚖"))
    check("unicode stored verbatim", r.status_code == 201 and r.get_json()["category"] == "食物")


# === 7. Concurrency ==========================================================

def probe_concurrency(mod):
    """Fire N concurrent POSTs, verify all succeed with unique sequential ids."""
    c = mod.app.test_client()
    _reset(mod)
    N = 50
    statuses = []

    def worker(i):
        cc = mod.app.test_client()
        r = cc.post("/api/expenses", json=valid(amount=i + 1, description=f"exp{i}"))
        statuses.append(r.status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    success = sum(1 for s in statuses if s == 201)
    check(f"concurrent {N} POSTs all 201", success == N, f"only {success}/{N} succeeded")

    ids = sorted(e["id"] for e in c.get("/api/expenses").get_json())
    check(f"concurrent ids sequential 1..{N}", ids == list(range(1, N + 1)))


# === 8. Production mode (real HTTP, no test_client) ==========================

def probe_production_mode(mod):
    """Spin up a real Flask server (debug=False, no TESTING flag) and hit it
    over actual HTTP. Catches bugs masked by test_client / conftest fixtures."""
    _reset(mod)

    def run_server():
        mod.app.run(host=PROD_HOST, port=PROD_PORT, debug=False, use_reloader=False)

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(2)  # wait for server bind

    try:
        # POST
        s, b = _http_req(PROD_HOST, PROD_PORT, "POST", "/api/expenses",
                         {"amount": 42, "category": "food", "description": "prod", "date": "2024-06-15"})
        check("prod POST -> 201", s == 201, f"got {s}")

        # GET single
        s, b = _http_req(PROD_HOST, PROD_PORT, "GET", "/api/expenses/1")
        check("prod GET single -> 200", s == 200)

        # GET list
        s, b = _http_req(PROD_HOST, PROD_PORT, "GET", "/api/expenses")
        check("prod GET list -> 200", s == 200)

        # Summary
        s, b = _http_req(PROD_HOST, PROD_PORT, "GET", "/api/summary")
        check("prod GET summary -> 200", s == 200)

        # DELETE
        s, b = _http_req(PROD_HOST, PROD_PORT, "DELETE", "/api/expenses/1")
        check("prod DELETE -> 204", s == 204)

        # GET after delete
        s, b = _http_req(PROD_HOST, PROD_PORT, "GET", "/api/expenses/1")
        check("prod GET after delete -> 404", s == 404)
    finally:
        pass  # daemon thread dies with process


if __name__ == "__main__":
    mod = _load_client()
    probes = [
        probe_input_validation,
        probe_filtering,
        probe_sorting,
        probe_summary,
        probe_crud_lifecycle,
        probe_delimiter_injection,
        probe_concurrency,
        probe_production_mode,
    ]
    for p in probes:
        print(f"\n--- {p.__name__} ---")
        try:
            p(mod)
        except Exception as e:
            results.append((p.__name__, "CRASH"))
            print(f"  [CRASH] {p.__name__}: {type(e).__name__}: {e}")

    fails = [n for n, s in results if s != "PASS"]
    total = len(results)
    passed = total - len(fails)
    print(f"\n{'='*60}")
    print(f"{passed}/{total} passed")
    if fails:
        print(f"FAILURES: {fails}")
    sys.exit(1 if fails else 0)
