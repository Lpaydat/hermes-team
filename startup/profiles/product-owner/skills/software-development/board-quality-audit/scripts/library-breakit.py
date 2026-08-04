#!/usr/bin/env python3
"""
Reusable adversarial break-it probe for a LIBRARY / CODEC spec (pure functions,
no server). This is the library-spec equivalent of rest-api-breakit.py.

Designed for specs where the SUT (system under test) implements something that
also exists in the stdlib (base64, json, csv, urllib, hashlib, etc.). The stdlib
serves as a READ-ONLY ORACLE — imported by THIS probe, never by the SUT.

It exercises the five failure modes most likely to survive a developer's own
tests:
  1. Edge-length matrix (empty, 1, 2, 3, partial groups, all byte values)
  2. Round-trip property across a dense length range vs the oracle
  3. Invalid-input rejection (bad length, invalid chars, malformed padding)
  4. Large-data stress (10MB — catches O(n^2) blowups and OOM)
  5. Forbidden-import purity check (spec says "no stdlib X" — verify it)

Usage:
  1. Set SUT_PATH to the dir containing the SUT package.
  2. Set SUT_IMPORTS to the public functions to test.
  3. Set ORACLE to the stdlib reference (or None if no oracle exists).
  4. Adapt the INVALID_INPUTS list to the spec's documented error cases.
  5. Adapt the FORBIDDEN_IMPORTS list to the spec's purity constraint.
  6. Run: python3 library-breakit.py   (exits 1 on any FAIL)

For streaming codecs (encode_stream/reader+writer), see probe_streaming() and
adapt CHUNK_SIZES.
"""
import importlib
import inspect
import os
import sys

# --- CONFIG: adapt these for the board under audit ---------------------------
SUT_PATH = "/tmp/hermes-verify-b64"             # dir containing the SUT package
SUT_MODULE = "b64"                              # importable package name
# Map role -> function name in the SUT:
SUT = {
    "encode": "encode",          # data -> encoded-str
    "decode": "decode",          # encoded-str -> data
    "encode_urlsafe": "encode_urlsafe",   # optional: set None if N/A
    "decode_urlsafe": "decode_urlsafe",   # optional: set None if N/A
    "encode_stream": "encode_stream",     # optional: set None if N/A
}
# Stdlib oracle (set to None if the spec has no stdlib equivalent):
import base64 as _b64
ORACLE = {
    "encode": _b64.b64encode,            # data -> bytes (decode to str for cmp)
    "decode": _b64.b64decode,            # str/bytes -> data
    "encode_urlsafe": _b64.urlsafe_b64encode,
}
# Inputs that MUST raise ValueError (adapt to the spec's error contract):
INVALID_INPUTS = [
    "Zm9vY",      # length not a multiple of 4
    "Zg=",        # wrong padding count (needs ==)
    "Zm9====",    # too much padding
    "====",       # all padding
    "Zm=v",       # '=' in non-padding position
    "Zm9v!",      # invalid character
    "Zm9v ",      # space (invalid char)
    "Zm\t9v",     # embedded control char
    "=Zm9",       # leading pad
]
# Forbidden imports (spec purity constraint — SUT must not use these):
FORBIDDEN_IMPORTS = ["base64"]
# Streaming chunk sizes to stress carry-over logic:
CHUNK_SIZES = [1, 2, 3, 4, 5, 3071, 3072, 3073, 99999]
# -----------------------------------------------------------------------------

sys.path.insert(0, SUT_PATH)
mod = importlib.import_module(SUT_MODULE)

def _get(role):
    name = SUT.get(role)
    return getattr(mod, name) if name else None

enc = _get("encode")
dec = _get("decode")
enc_u = _get("encode_urlsafe")
dec_u = _get("decode_urlsafe")
enc_s = _get("encode_stream")

results = []

def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((name, status))
    tag = f"  [{status}] {name}"
    if detail and status == "FAIL":
        tag += f"  ::  {detail}"
    print(tag)

# === 1. Edge-length matrix (empty, single, pair, group) =====================
def probe_edge_lengths():
    for d in [b"", b"a", b"ab", b"abc", b"\x00", b"\x00\x00",
              b"\xff", b"\xff\xff\xff"]:
        mine = enc(d)
        if ORACLE:
            ok = mine == ORACLE["encode"](d).decode()
            check(f"encode({d!r}) matches oracle", ok,
                  f"mine={mine!r} oracle={ORACLE['encode'](d).decode()!r}")
        check(f"decode(encode({d!r})) round-trips", dec(mine) == d)

# === 2. Dense round-trip vs oracle (all lengths 0..300) =====================
def probe_roundtrip_dense():
    import random
    rng = random.Random(42)
    fail_n, fail_rt = None, None
    for n in range(0, 301):
        data = bytes(rng.randint(0, 255) for _ in range(n))
        if ORACLE and enc(data) != ORACLE["encode"](data).decode():
            fail_n = n
        if dec(enc(data)) != data:
            fail_rt = n
    check("encode matches oracle for lengths 0..300", fail_n is None,
          f"first mismatch at n={fail_n}")
    check("round-trip for lengths 0..300", fail_rt is None,
          f"first failure at n={fail_rt}")

# === 3. Full byte range (every value 0..255 as single byte + in groups) =====
def probe_full_byte_range():
    bad = []
    for b in range(256):
        d = bytes([b])
        if dec(enc(d)) != d:
            bad.append(b)
    check("round-trip every single byte value 0..255", not bad,
          f"failed bytes: {bad[:10]}{'...' if len(bad)>10 else ''}")

# === 4. Invalid-input rejection (must raise ValueError) =====================
def probe_invalid_inputs():
    not_raised = []
    for s in INVALID_INPUTS:
        try:
            dec(s)
            not_raised.append(s)
        except ValueError:
            pass  # expected
        except Exception as e:
            # wrong exception type — still note it (yellow flag, not a hard fail)
            results.append((f"invalid {s!r} raises", "FAIL"))
            print(f"  [FAIL] invalid {s!r} raised {type(e).__name__}, not ValueError")
    check(f"all {len(INVALID_INPUTS)} invalid inputs raise ValueError",
          not not_raised, f"did NOT raise: {not_raised}")

# === 5. Large-data stress (10MB — OOM / O(n^2) / correctness) ===============
def probe_large_data():
    data = os.urandom(10_000_000)
    ok_enc = enc(data) == ORACLE["encode"](data).decode() if ORACLE else True
    check("10MB encode matches oracle", ok_enc)
    check("10MB round-trip", dec(enc(data)) == data)

# === 6. URL-safe variant (if present) — no '+' or '/' ever emitted ==========
def probe_urlsafe():
    if not enc_u:
        results.append(("urlsafe (N/A — no encode_urlsafe)", "SKIP"))
        print("  [SKIP] urlsafe — no encode_urlsafe in SUT")
        return
    leaked = None
    for n in range(1, 257):
        data = bytes(range(min(n, 256))) * (n // 256 + 1)
        data = data[:n]
        u = enc_u(data)
        if "+" in u or "/" in u:
            leaked = n
            break
        if ORACLE and u != ORACLE["encode_urlsafe"](data).decode():
            leaked = f"oracle-mismatch@{n}"
            break
    check("urlsafe never emits '+'/'/' for lengths 1..256", leaked is None,
          f"first leak at n={leaked}")
    if dec_u:
        d = bytes(range(256))
        check("urlsafe round-trip (all bytes)",
              dec_u(enc_u(d)) == d)

# === 7. Streaming (if present) — byte-identical to encode at all chunk sizes =
def probe_streaming():
    import io
    if not enc_s:
        results.append(("streaming (N/A — no encode_stream)", "SKIP"))
        print("  [SKIP] streaming — no encode_stream in SUT")
        return
    fail = None
    for cs in CHUNK_SIZES:
        data = os.urandom(9999)
        class _R:
            def __init__(s, b): s.b, s.i = b, 0
            def read(s, n):
                n = min(n, cs); c = s.b[s.i:s.i+n]; s.i += len(c); return c
        w = io.StringIO()
        enc_s(_R(data), w)
        expected = ORACLE["encode"](data).decode() if ORACLE else enc(data)
        if w.getvalue() != expected:
            fail = cs; break
    check(f"streaming byte-identical to encode at chunk sizes {CHUNK_SIZES}",
          fail is None, f"first mismatch at chunk_size={fail}")
    # empty stream
    w = io.StringIO(); enc_s(io.BytesIO(b""), w)
    check("empty stream -> ''", w.getvalue() == "")

# === 8. Purity: forbidden imports absent from SUT source =====================
def probe_purity():
    src = inspect.getsource(mod)
    leaks = []
    for imp in FORBIDDEN_IMPORTS:
        if f"import {imp}" in src or f"from {imp}" in src:
            leaks.append(imp)
    check(f"no forbidden imports ({FORBIDDEN_IMPORTS}) in SUT source",
          not leaks, f"leaked: {leaks}")
    # cross-check on disk too (catches dynamic exec the source-scan misses)
    import subprocess
    for imp in FORBIDDEN_IMPORTS:
        r = subprocess.run(["grep", "-rln", f"import {imp}", SUT_PATH],
                           capture_output=True, text=True)
        # ignore THIS probe file itself and __pycache__
        hits = [h for h in r.stdout.strip().splitlines()
                if "library-breakit" not in h and "__pycache__" not in h]
        if hits:
            check(f"on-disk grep: no 'import {imp}' in SUT dir", False,
                  f"hits: {hits[:3]}")
            return
    check(f"on-disk grep: no forbidden imports in SUT dir", True)


if __name__ == "__main__":
    probes = [
        probe_edge_lengths,
        probe_roundtrip_dense,
        probe_full_byte_range,
        probe_invalid_inputs,
        probe_large_data,
        probe_urlsafe,
        probe_streaming,
        probe_purity,
    ]
    for p in probes:
        print(f"\n=== {p.__name__} ===")
        try:
            p()
        except Exception as e:
            results.append((p.__name__, "CRASH"))
            print(f"  [CRASH] {p.__name__}: {type(e).__name__}: {e}")

    fails = [n for n, s in results if s == "FAIL"]
    crashes = [n for n, s in results if s == "CRASH"]
    passed = sum(1 for _, s in results if s == "PASS")
    total = len(results)
    print(f"\n{passed}/{total} passed" +
          (f", {len(fails)} FAIL" if fails else "") +
          (f", {len(crashes)} CRASH" if crashes else ""))
    sys.exit(1 if (fails or crashes) else 0)
