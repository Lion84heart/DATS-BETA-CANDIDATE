# RB-011: Incident Response

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Operator, Admin, Engineering

---

## 1. Purpose

Systematically assess, contain, diagnose, resolve, and document platform incidents to restore service and prevent recurrence.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Monitoring access | Access to alerting system (Prometheus/Grafana) | Able to view active alerts |
| API access | Can reach localhost:8000 or remote endpoint | `curl http://localhost:8000/health/` works |
| Communication channel | Access to incident channel (e.g., Slack #incidents) | Able to post messages |
| Log access | Read access to `/opt/DATS-BETA-CANDIDATE/logs/` | `ls /opt/DATS-BETA-CANDIDATE/logs/dats.log` succeeds |
| Auth credentials | Valid login for role-based endpoints | Can obtain JWT via `/auth/login` |

## 3. Procedure

### Step 1: Detect and Acknowledge
```bash
# Check if the alert is genuine
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/
curl -s http://localhost:8000/system/state | python -m json.tool
```
**Expected outcome:** Confirm whether the system is truly impaired or if the alert is a false positive.

**Action:** Post initial acknowledgment to incident channel:
```
[INCIDENT ACK] DATS — <brief symptom> detected at <timestamp>. Investigating.
```

### Step 2: Assess Severity

Use the DATS-specific severity matrix below:

| Severity | Platform Indicator | Business Impact | Response Time |
|----------|-------------------|-----------------|---------------|
| SEV-1 | All endpoints return 000/5xx; no process on port 8000 | Platform completely unavailable; all trading halted | Immediate (< 5 min) |
| SEV-2 | `/health/` OK but `/system/state` not HEALTHY; order endpoints fail; paper trading broken | Core trading functionality impaired | < 15 min |
| SEV-3 | Single router down; dashboard load > 100ms; one WebSocket unresponsive; latency p95 > 50ms | Partial degradation; some features slow or unavailable | < 30 min |
| SEV-4 | Single non-critical endpoint error; `/metrics/prometheus` formatting issue; minor log warnings | Minor issue; no user-facing impact | < 60 min |

```bash
# Gather severity indicators
curl -s http://localhost:8000/health/ | python -m json.tool
curl -s http://localhost:8000/status/ | python -m json.tool
curl -s http://localhost:8000/system/state | python -m json.tool
curl -s http://localhost:8000/diagnostics/performance | python -m json.tool
```

**Expected outcome:** Clear classification of SEV-1 through SEV-4 based on objective endpoint results.

### Step 3: Contain Impact

**SEV-1 / SEV-2:**
- If platform is down or core trading broken, immediately notify stakeholders and consider failover:
  ```bash
  # Notify stakeholders (example using Slack webhook)
  curl -X POST -H "Content-type: application/json" \
    --data '{"text":"SEV-1/SEV-2: DATS platform impaired. Trading paused. Incident commander: <your_name>"}' \
    $SLACK_WEBHOOK_URL
  ```
- If a graceful shutdown is needed for safety:
  ```bash
  # ADMIN login required
  TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin&password=$ADMIN_PASSWORD" | jq -r '.access_token')
  curl -X POST http://localhost:8000/system/shutdown \
    -H "Authorization: Bearer $TOKEN"
  ```

**SEV-3 / SEV-4:**
- Monitor but do not disrupt service unless symptoms escalate.
- Document current state for trend analysis.

### Step 4: Diagnose

```bash
# Collect comprehensive diagnostics
curl -s http://localhost:8000/diagnostics/runtime > /tmp/dats_runtime_$(date +%Y%m%d_%H%M%S).json
curl -s http://localhost:8000/diagnostics/performance > /tmp/dats_perf_$(date +%Y%m%d_%H%M%S).json
curl -s http://localhost:8000/diagnostics/dependencies > /tmp/dats_deps_$(date +%Y%m%d_%H%M%S).json
curl -s http://localhost:8000/diagnostics/config > /tmp/dats_config_$(date +%Y%m%d_%H%M%S).json
curl -s http://localhost:8000/audit/history > /tmp/dats_audit_$(date +%Y%m%d_%H%M%S).json
```

```bash
# Collect logs
tail -n 200 /opt/DATS-BETA-CANDIDATE/logs/dats.log > /tmp/dats_log_tail_$(date +%Y%m%d_%H%M%S).log
sudo dmesg | tail -n 50 > /tmp/dmesg_tail_$(date +%Y%m%d_%H%M%S).log
```

```bash
# Check system resources
free -h > /tmp/memory_$(date +%Y%m%d_%H%M%S).txt
df -h > /tmp/disk_$(date +%Y%m%d_%H%M%S).txt
ps aux | grep uvicorn > /tmp/processes_$(date +%Y%m%d_%H%M%S).txt
```

**Expected outcome:** A diagnostic bundle saved to `/tmp/` with timestamped files for analysis.

### Step 5: Resolve

**If service down:** Follow [RB-010: Failure Recovery](RB-010-FAILURE-RECOVERY.md).

**If performance degraded:** Follow [RB-013: Performance Verification](RB-013-PERFORMANCE-VERIFICATION.md).

**If health check anomaly only:**
```bash
# Restart the service as a first-line recovery
sudo systemctl restart DATS-BETA-CANDIDATE
sleep 10
```

**Expected outcome:** Service recovers or root cause is identified and remediated.

### Step 6: Verify Resolution
```bash
curl -s http://localhost:8000/health/ | python -m json.tool
curl -s http://localhost:8000/status/ | python -m json.tool
curl -s http://localhost:8000/system/state | python -m json.tool
curl -s http://localhost:8000/diagnostics/performance | python -m json.tool
```

**Expected outcome:** All endpoints return expected values. Performance metrics within baselines.

**Run full test suite:**
```bash
cd /opt/DATS-BETA-CANDIDATE
source .venv/bin/activate
pytest tests/ -q --tb=short
```
**Expected outcome:** `183 passed`.

### Step 7: Document and Communicate

**Update incident channel:**
```
[INCIDENT RESOLVED] DATS — <severity> incident resolved at <timestamp>.
Root cause: <one-line summary>
Actions taken: <brief list>
Tests: 183/183 passing
```

**Post-incident checklist:**
- [ ] Save all diagnostic files from `/tmp/dats_*` to `/opt/DATS-BETA-CANDIDATE/incidents/<YYYY-MM-DD>/`
- [ ] Write a brief incident summary (max 500 words)
- [ ] Identify any configuration changes that preceded the incident
- [ ] Check if the incident is recurring (search past 30 days in logs)
- [ ] Create a follow-up ticket if root cause is not fully understood
- [ ] Update monitoring thresholds if alert was a false positive
- [ ] Review and update runbooks if recovery steps were ineffective

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Health endpoint | HTTP 200, `{"status": "ok"}` | `curl -s http://localhost:8000/health/` |
| 2 | System state | `{"status": "HEALTHY"}` | `curl -s http://localhost:8000/system/state` |
| 3 | Performance baseline | `memory_mb < 256`, `cpu_percent` reasonable | `curl -s http://localhost:8000/diagnostics/performance` |
| 4 | Config validation | `{"valid": true}` | `curl -s http://localhost:8000/config/validate` |
| 5 | Test suite | `183 passed` | `pytest tests/ -q` |
| 6 | Prometheus metrics | Valid Prometheus text format | `curl -s http://localhost:8000/metrics/prometheus | head -n 5` |
| 7 | No regression | All previously working features still functional | Re-run health verification from RB-012 |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Severity misclassified | Alert was SEV-4 but treated as SEV-1 | Reclassify, stand down unnecessary escalations, document reason |
| Resolution fails | Symptoms persist after recovery steps | Escalate to engineering with full diagnostic bundle; continue monitoring |
| False positive alert | All checks pass; no actual impairment | Acknowledge as false positive; tune alert threshold; document |
| Escalation needed | Root cause unknown; SEV-1/SEV-2 persists > 30 min | Engage engineering team; provide `/tmp/dats_*` diagnostic bundle |
| Recurring incident | Same symptoms within 24 hours | Escalate to engineering immediately; do not rely on restart loops |
| Data integrity concern | Database errors or audit log gaps | Restore from backup; follow RB-010 database recovery steps |

## 6. Related Runbooks

- [RB-010: Failure Recovery](RB-010-FAILURE-RECOVERY.md) — For service-down scenarios
- [RB-012: Health Verification](RB-012-HEALTH-VERIFICATION.md) — Post-incident health checks
- [RB-013: Performance Verification](RB-013-PERFORMANCE-VERIFICATION.md) — Performance validation after resolution

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
