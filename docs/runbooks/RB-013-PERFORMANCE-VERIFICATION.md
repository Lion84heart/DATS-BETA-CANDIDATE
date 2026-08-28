# RB-013: Performance Verification

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Operator, Admin

---

## 1. Purpose

Measure and validate platform performance metrics (API latency, throughput, memory usage, dashboard load) against established baselines to detect degradation before it impacts trading operations.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| System running | DATS active and stable for at least 60 seconds | `curl -s http://localhost:8000/system/state` returns `HEALTHY` |
| Idle state | No active batch jobs or large data imports in progress | `ps aux` shows no heavy background tasks |
| Baseline known | Performance targets are documented and accessible | Baselines from platform spec are available |
| Measurement tools | `curl`, `time`, `python3`, `awk` available | `which curl && which python3 && which awk` |
| Load generator | `ab` (Apache Bench) or Python `httpx` available | `which ab` or `python -c "import httpx"` |

## 3. Procedure

### Step 1: Establish System State
```bash
curl -s http://localhost:8000/system/state | python -m json.tool
curl -s http://localhost:8000/diagnostics/performance | python -m json.tool
curl -s http://localhost:8000/diagnostics/runtime | python -m json.tool
```
**Expected outcome:** System state is `HEALTHY`. Current performance baseline captured before load test.

### Step 2: Measure API Latency (p95)

Run 100 sequential requests to key endpoints and compute p95 latency:

```bash
# Health endpoint latency
echo "=== Health Endpoint Latency ==="
for i in $(seq 1 100); do
    curl -s -o /dev/null -w "%{time_total}\n" http://localhost:8000/health/
done | awk '
    {a[NR]=$1; sum+=$1}
    END {
        asort(a);
        p95=int(NR*0.95);
        if(p95<1) p95=1;
        printf "Count: %d  Mean: %.4fs  p95: %.4fs  Min: %.4fs  Max: %.4fs\n", NR, sum/NR, a[p95], a[1], a[NR]
    }'

# Status endpoint latency
echo "=== Status Endpoint Latency ==="
for i in $(seq 1 100); do
    curl -s -o /dev/null -w "%{time_total}\n" http://localhost:8000/status/
done | awk '
    {a[NR]=$1; sum+=$1}
    END {
        asort(a);
        p95=int(NR*0.95);
        if(p95<1) p95=1;
        printf "Count: %d  Mean: %.4fs  p95: %.4fs  Min: %.4fs  Max: %.4fs\n", NR, sum/NR, a[p95], a[1], a[NR]
    }'

# Diagnostics runtime latency
echo "=== Diagnostics Runtime Latency ==="
for i in $(seq 1 100); do
    curl -s -o /dev/null -w "%{time_total}\n" http://localhost:8000/diagnostics/runtime
done | awk '
    {a[NR]=$1; sum+=$1}
    END {
        asort(a);
        p95=int(NR*0.95);
        if(p95<1) p95=1;
        printf "Count: %d  Mean: %.4fs  p95: %.4fs  Min: %.4fs  Max: %.4fs\n", NR, sum/NR, a[p95], a[1], a[NR]
    }'
```

**Expected outcome:** p95 latency for all endpoints is **< 0.050s (50ms)**. Baseline target is ~7.97ms.

### Step 3: Measure Throughput

Using `ab` (Apache Bench) if available:
```bash
# 1000 requests, 50 concurrent connections
ab -n 1000 -c 50 http://localhost:8000/health/ 2>&1 | tee /tmp/dats_throughput_ab.log
```

**Alternative using Python:**
```bash
cat > /tmp/dats_throughput.py << 'PYEOF'
import asyncio, time, httpx, statistics

BASE_URL = "http://localhost:8000"
TOTAL_REQUESTS = 1000
CONCURRENT = 50

async def worker(client, sem, latencies, errors):
    async with sem:
        start = time.perf_counter()
        try:
            resp = await client.get(f"{BASE_URL}/health/")
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
            if resp.status_code != 200:
                errors.append(resp.status_code)
        except Exception as e:
            errors.append(str(e))

async def main():
    sem = asyncio.Semaphore(CONCURRENT)
    latencies = []
    errors = []
    async with httpx.AsyncClient() as client:
        start = time.perf_counter()
        tasks = [worker(client, sem, latencies, errors) for _ in range(TOTAL_REQUESTS)]
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start

    throughput = TOTAL_REQUESTS / total_time
    mean_lat = statistics.mean(latencies) * 1000
    p95_lat = sorted(latencies)[int(len(latencies)*0.95)] * 1000
    max_lat = max(latencies) * 1000

    print(f"=== Throughput Results ===")
    print(f"Total requests: {TOTAL_REQUESTS}")
    print(f"Concurrent:     {CONCURRENT}")
    print(f"Total time:     {total_time:.2f}s")
    print(f"Throughput:     {throughput:.1f} req/sec")
    print(f"Mean latency:   {mean_lat:.2f}ms")
    print(f"p95 latency:    {p95_lat:.2f}ms")
    print(f"Max latency:    {max_lat:.2f}ms")
    print(f"Errors:         {len(errors)}")
    if errors:
        print(f"First 5 errors: {errors[:5]}")

asyncio.run(main())
PYEOF
cd /opt/DATS-BETA-CANDIDATE && source .venv/bin/activate && python /tmp/dats_throughput.py
```

**Expected outcome:** Throughput **> 500 req/sec**. Baseline is ~621 req/sec.

### Step 4: Measure Memory Usage

```bash
# Baseline memory
curl -s http://localhost:8000/diagnostics/performance | python -m json.tool

# Capture initial memory
INITIAL_MEM=$(curl -s http://localhost:8000/diagnostics/performance | python -c "import sys,json; d=json.load(sys.stdin); print(d['memory_mb'])")
echo "Initial memory: ${INITIAL_MEM}MB"
```

**Expected outcome:** Memory usage is **< 256 MB**. Baseline is 163.6 MB.

### Step 5: Measure Memory Leak Over 30 Requests

```bash
cat > /tmp/dats_memory_leak.py << 'PYEOF'
import requests, time, json

BASE = "http://localhost:8000"
ITERATIONS = 30

memories = []
for i in range(ITERATIONS):
    r = requests.get(f"{BASE}/health/")
    r.raise_for_status()
    perf = requests.get(f"{BASE}/diagnostics/performance").json()
    memories.append(perf["memory_mb"])
    time.sleep(0.1)

start_mem = memories[0]
end_mem = memories[-1]
leak = end_mem - start_mem
print(f"=== Memory Leak Test ===")
print(f"Iterations: {ITERATIONS}")
print(f"Start memory:  {start_mem:.1f}MB")
print(f"End memory:    {end_mem:.1f}MB")
print(f"Leak:          {leak:.1f}MB")
print(f"Per-request:   {leak/ITERATIONS:.3f}MB")
if leak < 5.0:
    print("PASS: Memory leak within acceptable threshold (< 5MB)")
else:
    print("FAIL: Memory leak exceeds threshold (>= 5MB)")
PYEOF
cd /opt/DATS-BETA-CANDIDATE && source .venv/bin/activate && python /tmp/dats_memory_leak.py
```

**Expected outcome:** Memory increase over 30 requests is **< 5 MB**. Baseline is 0.8 MB.

### Step 6: Measure Dashboard Load Time

```bash
echo "=== Dashboard Load Time ==="
for i in $(seq 1 20); do
    curl -s -o /dev/null -w "%{time_total}\n" http://localhost:8000/
done | awk '
    {a[NR]=$1; sum+=$1}
    END {
        asort(a);
        p95=int(NR*0.95);
        if(p95<1) p95=1;
        printf "Count: %d  Mean: %.4fs  p95: %.4fs  Min: %.4fs  Max: %.4fs\n", NR, sum/NR, a[p95], a[1], a[NR]
    }'
```

**Expected outcome:** Dashboard p95 load time **< 0.100s (100ms)**. Baseline is 1.6ms.

### Step 7: Measure Prometheus Metrics Endpoint

```bash
echo "=== Prometheus Metrics Endpoint ==="
for i in $(seq 1 20); do
    curl -s -o /dev/null -w "%{time_total}\n" http://localhost:8000/metrics/prometheus
done | awk '
    {a[NR]=$1; sum+=$1}
    END {
        asort(a);
        p95=int(NR*0.95);
        if(p95<1) p95=1;
        printf "Count: %d  Mean: %.4fs  p95: %.4fs  Min: %.4fs  Max: %.4fs\n", NR, sum/NR, a[p95], a[1], a[NR]
    }'

# Verify metrics content is valid
curl -s http://localhost:8000/metrics/prometheus | grep -E "^(# HELP|# TYPE|http_|process_)" | head -n 10
```

**Expected outcome:** p95 latency < 50ms. Metrics output contains standard Prometheus metric families.

### Step 8: Automated Performance Benchmark Script

Save and execute the following Python script for repeatable performance verification:

```bash
cat > /opt/DATS-BETA-CANDIDATE/scripts/performance_benchmark.py << 'PYEOF'
#!/usr/bin/env python3
"""
DATS — Automated Performance Verification Script
Version: 1.0
Date: 2026-08-08
"""
import asyncio, time, json, sys, statistics
import httpx

BASE_URL = "http://localhost:8000"

# Baseline targets
TARGETS = {
    "api_p95_ms": {"target": 50.0,  "baseline": 7.97,  "unit": "ms",  "operator": "<"},
    "dashboard_p95_ms": {"target": 100.0, "baseline": 1.6,  "unit": "ms",  "operator": "<"},
    "throughput_rps": {"target": 500.0, "baseline": 621.0, "unit": "req/sec", "operator": ">"},
    "memory_mb": {"target": 256.0, "baseline": 163.6, "unit": "MB",  "operator": "<"},
    "memory_leak_mb": {"target": 5.0,   "baseline": 0.8,   "unit": "MB",  "operator": "<"},
}

passed = 0
failed = 0
results = {}

def report(name: str, value: float, target: float, unit: str, op: str, baseline: float):
    global passed, failed
    ok = (value < target) if op == "<" else (value > target)
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results[name] = {
        "value": round(value, 3),
        "target": target,
        "baseline": baseline,
        "unit": unit,
        "status": status,
    }
    print(f"[{status}] {name}: {value:.2f} {unit} (target {op} {target} {unit}, baseline {baseline} {unit})")

async def measure_latency(client: httpx.AsyncClient, path: str, count: int):
    times = []
    for _ in range(count):
        start = time.perf_counter()
        r = await client.get(f"{BASE_URL}{path}")
        r.raise_for_status()
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95)]
    mean = statistics.mean(times)
    return {"p95_ms": p95, "mean_ms": mean, "min_ms": min(times), "max_ms": max(times)}

async def measure_throughput(client: httpx.AsyncClient, total: int, concurrent: int):
    sem = asyncio.Semaphore(concurrent)
    latencies = []
    errors = []

    async def worker():
        async with sem:
            start = time.perf_counter()
            try:
                r = await client.get(f"{BASE_URL}/health/")
                latencies.append((time.perf_counter() - start) * 1000)
                if r.status_code != 200:
                    errors.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

    t0 = time.perf_counter()
    await asyncio.gather(*[worker() for _ in range(total)])
    total_time = time.perf_counter() - t0
    rps = total / total_time
    return {"rps": rps, "errors": len(errors), "mean_ms": statistics.mean(latencies) if latencies else 0}

async def measure_memory():
    r = await client.get(f"{BASE_URL}/diagnostics/performance")
    return r.json()["memory_mb"]

async def measure_memory_leak(client: httpx.AsyncClient, iterations: int):
    memories = []
    for _ in range(iterations):
        r = await client.get(f"{BASE_URL}/health/")
        r.raise_for_status()
        perf = (await client.get(f"{BASE_URL}/diagnostics/performance")).json()
        memories.append(perf["memory_mb"])
        await asyncio.sleep(0.1)
    return memories[-1] - memories[0]

async def main():
    global client
    print("=" * 60)
    print("DATS — Performance Verification")
    print(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # 1. API Latency p95
        print("\n--- 1. API Latency (p95) ---")
        lat = await measure_latency(client, "/health/", 100)
        report("api_p95_ms", lat["p95_ms"], **{k: v for k, v in TARGETS["api_p95_ms"].items() if k != "baseline"})
        print(f"       mean={lat['mean_ms']:.2f}ms min={lat['min_ms']:.2f}ms max={lat['max_ms']:.2f}ms")

        # 2. Dashboard Load
        print("\n--- 2. Dashboard Load Time ---")
        lat = await measure_latency(client, "/", 20)
        report("dashboard_p95_ms", lat["p95_ms"], **{k: v for k, v in TARGETS["dashboard_p95_ms"].items() if k != "baseline"})

        # 3. Throughput
        print("\n--- 3. Throughput ---")
        thr = await measure_throughput(client, 1000, 50)
        report("throughput_rps", thr["rps"], **{k: v for k, v in TARGETS["throughput_rps"].items() if k != "baseline"})
        print(f"       errors={thr['errors']} mean_latency={thr['mean_ms']:.2f}ms")

        # 4. Memory Baseline
        print("\n--- 4. Memory Usage ---")
        mem = await measure_memory()
        report("memory_mb", mem, **{k: v for k, v in TARGETS["memory_mb"].items() if k != "baseline"})

        # 5. Memory Leak
        print("\n--- 5. Memory Leak (30 requests) ---")
        leak = await measure_memory_leak(client, 30)
        report("memory_leak_mb", leak, **{k: v for k, v in TARGETS["memory_leak_mb"].items() if k != "baseline"})

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    with open("/tmp/dats_performance_results.json", "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results, "summary": {"passed": passed, "failed": failed}}, f, indent=2)
    print("Detailed results saved to: /tmp/dats_performance_results.json")

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    asyncio.run(main())
PYEOF
chmod +x /opt/DATS-BETA-CANDIDATE/scripts/performance_benchmark.py
```

**Execute the script:**
```bash
cd /opt/DATS-BETA-CANDIDATE && source .venv/bin/activate && python /opt/DATS-BETA-CANDIDATE/scripts/performance_benchmark.py
```

**Expected outcome:** All 5 metrics show `[PASS]`. Results saved to `/tmp/dats_performance_results.json`.

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | API latency p95 | < 50ms (baseline ~7.97ms) | `curl` loop + `awk` p95 calculation |
| 2 | Dashboard load p95 | < 100ms (baseline ~1.6ms) | `curl` loop + `awk` p95 calculation |
| 3 | Throughput | > 500 req/sec (baseline ~621) | `ab -n 1000 -c 50` or Python script |
| 4 | Memory usage | < 256 MB (baseline ~163.6MB) | `GET /diagnostics/performance` |
| 5 | Memory leak | < 5 MB over 30 requests (baseline ~0.8MB) | Python script measuring `/diagnostics/performance` |
| 6 | Prometheus metrics latency | < 50ms p95 | `curl` loop on `/metrics/prometheus` |
| 7 | Automated benchmark | All 5 metrics PASS | `/opt/DATS-BETA-CANDIDATE/scripts/performance_benchmark.py` |

### Baseline Comparison Table

| Metric | Target | Baseline | Pass Criteria | Your Result | Status |
|--------|--------|----------|---------------|-------------|--------|
| API latency p95 | < 50ms | ~7.97ms | < 50ms | ___ ms | [ ] |
| Dashboard load p95 | < 100ms | ~1.6ms | < 100ms | ___ ms | [ ] |
| Throughput | > 500 req/sec | ~621 req/sec | > 500 req/sec | ___ req/sec | [ ] |
| Memory usage | < 256 MB | ~163.6 MB | < 256 MB | ___ MB | [ ] |
| Memory leak (30 req) | < 5 MB | ~0.8 MB | < 5 MB | ___ MB | [ ] |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| API latency above target | p95 > 50ms | Check CPU: `top -bn1`; check for background jobs; restart DATS; scale CPU if sustained |
| Dashboard load above target | p95 > 100ms | Check network latency to host; verify no proxy overhead; restart DATS; check disk I/O |
| Throughput below target | < 500 req/sec | Increase worker count in uvicorn config; verify no connection limit; restart DATS; check for resource contention |
| Memory usage above target | > 256 MB | Capture memory profile; check for large objects in logs; restart DATS; if leak confirmed, escalate to engineering |
| Memory leak above target | > 5MB over 30 requests | Document in incident log; restart DATS; run memory leak script again; if reproducible, escalate to engineering with results |
| Metrics endpoint slow | `/metrics/prometheus` > 50ms | Restart DATS; check if Prometheus middleware is generating excessive metrics; clear caches |
| All metrics degraded simultaneously | Multiple FAIL results | Likely system-level issue (CPU, memory, disk); check `top`, `free`, `df`; follow [RB-010: Failure Recovery](RB-010-FAILURE-RECOVERY.md) |
| Baseline no longer achievable | Consistently fails after recovery | Baseline may need re-evaluation; document new stable values; update runbook targets after engineering review |

## 6. Related Runbooks

- [RB-012: Health Verification](RB-012-HEALTH-VERIFICATION.md) — Verify system health before performance testing
- [RB-010: Failure Recovery](RB-010-FAILURE-RECOVERY.md) — When performance degradation is caused by system failure
- [RB-011: Incident Response](RB-011-INCIDENT-RESPONSE.md) — When performance issues constitute an incident (SEV-3/SEV-2)

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
