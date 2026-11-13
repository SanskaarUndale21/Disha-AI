"""Call every API operation with NO credentials and report which ones answer 2xx.
Reads and public report-filing are expected to be open; any other write that succeeds is a finding."""
import re
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SKIP = re.compile(r"/ws/|/openapi|/docs|/redoc")
spec = httpx.get(BASE + "/openapi.json").json()
rows = []
for path, ops in spec["paths"].items():
    if SKIP.search(path):
        continue
    for method, op in ops.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        url = BASE + re.sub(r"\{[^}]+\}", "1", path)
        try:
            if method == "get":
                r = httpx.get(url, timeout=30)
            else:
                r = httpx.request(method.upper(), url, json={}, timeout=30)
        except Exception as e:
            rows.append((method.upper(), path, "ERR", str(e)[:60]))
            continue
        rows.append((method.upper(), path, r.status_code, ""))
open_writes = [r for r in rows if r[0] != "GET" and isinstance(r[2], int) and r[2] < 400]
print("operations:", len(rows))
print("5xx errors:", [r[:3] for r in rows if isinstance(r[2], int) and r[2] >= 500])
print("WRITES THAT ANSWERED 2xx/3xx WITHOUT SIGN-IN (review each):")
for r in open_writes:
    print("  ", r[0], r[1], r[2])
print("open GETs (public data check):")
for r in rows:
    if r[0] == "GET" and r[2] == 200:
        print("  ", r[1])
