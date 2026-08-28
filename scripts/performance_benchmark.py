#!/usr/bin/env python3
"""
DATS — Automated Performance Verification Script
Version: 1.0
Date: 2026-08-08
"""
import time, json, sys, statistics
from fastapi.testclient import TestClient

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

def report(name, value, target, unit, op, baseline):
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

def measure_latency(client, path, count):
    times = []
    for _ in range(count):
        start = time.perf_counter()
        r = client.get(path)
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95)]
    mean = statistics.mean(times)
    return {"p95_ms": p95, "mean_ms": mean, "min_ms": min(times), "max_ms": max(times)}

def main():
    import sys
    sys.path.insert(0, "src")
    from api.main import app
    client = TestClient(app)

    print("=" * 60)
    print("DATS — Performance Verification")
    print(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print("=" * 60)

    # 1. API Latency p95
    print("\n--- 1. API Latency (p95) ---")
    lat = measure_latency(client, "/health/", 100)
    report("api_p95_ms", lat["p95_ms"], **{k: v for k, v in TARGETS["api_p95_ms"].items() if k != "baseline"})
    print(f"       mean={lat['mean_ms']:.2f}ms min={lat['min_ms']:.2f}ms max={lat['max_ms']:.2f}ms")

    # 2. Dashboard Load
    print("\n--- 2. Dashboard Load Time ---")
    lat = measure_latency(client, "/", 20)
    report("dashboard_p95_ms", lat["p95_ms"], **{k: v for k, v in TARGETS["dashboard_p95_ms"].items() if k != "baseline"})

    # 3. Throughput
    print("\n--- 3. Throughput ---")
    import concurrent.futures
    TOTAL = 1000
    CONCURRENT = 50
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT) as ex:
        list(ex.map(lambda _: client.get("/health/"), range(TOTAL)))
    total_time = time.perf_counter() - start
    rps = TOTAL / total_time
    report("throughput_rps", rps, **{k: v for k, v in TARGETS["throughput_rps"].items() if k != "baseline"})
    print(f"       Total time: {total_time:.2f}s")

    # 4. Memory
    print("\n--- 4. Memory Usage ---")
    print("       Memory tracking requires /diagnostics/performance endpoint")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    with open("/tmp/dats_performance_results.json", "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results, "summary": {"passed": passed, "failed": failed}}, f, indent=2)
    print("Detailed results saved to: /tmp/dats_performance_results.json")

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
