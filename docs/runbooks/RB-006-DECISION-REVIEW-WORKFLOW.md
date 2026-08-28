# RB-006: Decision Review Workflow

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** ANALYST, OPERATOR, ADMIN

---

## 1. Purpose

Review AI-generated trading decisions, mark them as reviewed, and export reviewed decisions for compliance and audit purposes.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Platform Running | FastAPI server listening on port 8000 | `curl -s http://localhost:8000/health` returns HTTP 200 |
| Authenticated User | Valid JWT with ANALYST, OPERATOR, or ADMIN role | POST /auth/login returns matching `role` |
| Decisions in Pipeline | At least one unreviewed decision exists | GET /decisions/summary/pipeline returns `total_decisions >= 1` |
| Export Directory Writable | `/data/exports/` exists and is writable | `ls -ld /data/exports/` shows `drwxrwxr-x` |

## 3. Procedure

### Step 1: Authenticate and Obtain JWT Token

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "analyst", "password": "analyst_pass"}' | jq .
```

**Expected outcome:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "ANALYST"
}
```

Store the token:
```bash
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Step 2: Verify Pipeline Summary

```bash
curl -s -X GET http://localhost:8000/decisions/summary/pipeline \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "total_decisions": 47,
  "latest_id": "DEC-20260808-047"
}
```

If `total_decisions` is 0, the pipeline is empty. Do not proceed; see Recovery Procedure "No decisions found."

### Step 3: List Recent Decisions

```bash
curl -s -X GET "http://localhost:8000/decisions/?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "decisions": [
    {
      "id": "DEC-20260808-047",
      "symbol": "AAPL",
      "action": "BUY",
      "confidence": 0.87,
      "reviewed": false,
      "reviewed_by": null,
      "timestamp": "2026-08-08T09:14:22Z"
    },
    {
      "id": "DEC-20260808-046",
      "symbol": "MSFT",
      "action": "HOLD",
      "confidence": 0.62,
      "reviewed": false,
      "reviewed_by": null,
      "timestamp": "2026-08-08T09:12:05Z"
    }
  ],
  "total": 47
}
```

### Step 4: Retrieve a Specific Decision for Review

Select the most recent unreviewed decision (e.g., `DEC-20260808-047`) and fetch its details:

```bash
curl -s -X GET http://localhost:8000/decisions/DEC-20260808-047 \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "id": "DEC-20260808-047",
  "symbol": "AAPL",
  "action": "BUY",
  "confidence": 0.87,
  "rationale": "Bullish crossover on 20/50 EMA with volume confirmation",
  "reviewed": false,
  "reviewed_by": null,
  "timestamp": "2026-08-08T09:14:22Z"
}
```

### Step 5: Mark Decision as Reviewed

```bash
curl -s -X POST http://localhost:8000/decisions/DEC-20260808-047/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq .
```

**Expected outcome:**
```json
{
  "id": "DEC-20260808-047",
  "reviewed": true,
  "reviewed_by": "analyst",
  "reviewed_at": "2026-08-08T09:20:33Z"
}
```

### Step 6: Verify Review Status Updated

```bash
curl -s -X GET http://localhost:8000/decisions/DEC-20260808-047 \
  -H "Authorization: Bearer $TOKEN" | jq '.reviewed, .reviewed_by'
```

**Expected outcome:**
```
true
"analyst"
```

### Step 7: Batch Review Remaining Unreviewed Decisions (Optional)

If multiple decisions require review, iterate over IDs:

```bash
for id in DEC-20260808-046 DEC-20260808-045; do
  curl -s -X POST "http://localhost:8000/decisions/${id}/review" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" | jq -c '{id, reviewed, reviewed_by}'
done
```

**Expected outcome:**
```
{"id":"DEC-20260808-046","reviewed":true,"reviewed_by":"analyst"}
{"id":"DEC-20260808-045","reviewed":true,"reviewed_by":"analyst"}
```

### Step 8: Export Reviewed Decisions to CSV

```bash
curl -s -X GET "http://localhost:8000/decisions/export/csv" \
  -H "Authorization: Bearer $TOKEN" \
  -o /data/exports/decisions_20260808.csv
```

**Expected outcome:** File `/data/exports/decisions_20260808.csv` created with non-zero size.

Verify file:
```bash
ls -lh /data/exports/decisions_20260808.csv
head -5 /data/exports/decisions_20260808.csv
```

**Expected output:**
```
-rw-r--r-- 1 analyst analyst 12K Aug  8 09:25 /data/exports/decisions_20260808.csv
id,symbol,action,confidence,reviewed,reviewed_by,timestamp
DEC-20260808-047,AAPL,BUY,0.87,true,analyst,2026-08-08T09:14:22Z
DEC-20260808-046,MSFT,HOLD,0.62,true,analyst,2026-08-08T09:12:05Z
DEC-20260808-045,GOOGL,SELL,0.74,true,analyst,2026-08-08T09:08:17Z
```

### Step 9: Verify Export Contains Reviewed Decisions

```bash
grep -c "true" /data/exports/decisions_20260808.csv
grep -c "false" /data/exports/decisions_20260808.csv
```

**Expected outcome:**
- Count of `true` >= number of decisions reviewed in this session.
- Count of `false` may be 0 or reflect older unreviewed decisions not in this export scope.

### Step 10: Audit Trail Verification

```bash
curl -s -X GET "http://localhost:8000/audit/history?limit=20" \
  -H "Authorization: Bearer $TOKEN" | jq '.entries[] | select(.action | contains("review"))'
```

**Expected outcome:**
```json
{
  "timestamp": "2026-08-08T09:20:33Z",
  "user": "analyst",
  "action": "decision_reviewed",
  "resource_id": "DEC-20260808-047",
  "details": "Marked as reviewed by analyst"
}
```

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Login successful | HTTP 200, `role: ANALYST` or higher | `curl POST /auth/login` |
| 2 | Pipeline not empty | `total_decisions >= 1` | `curl GET /decisions/summary/pipeline` |
| 3 | Unreviewed decisions exist | At least one entry with `reviewed: false` | `curl GET /decisions/?limit=10` |
| 4 | Decision details retrievable | HTTP 200, full decision object | `curl GET /decisions/{id}` |
| 5 | Review operation succeeds | HTTP 200, `reviewed: true`, `reviewed_by` populated | `curl POST /decisions/{id}/review` |
| 6 | Review status persists | Re-fetch shows `reviewed: true` | `curl GET /decisions/{id}` |
| 7 | Export file created | File exists, size > 0, CSV headers present | `ls -lh`, `head` on exported file |
| 8 | Export contains reviewed data | Rows with `reviewed=true` and correct `reviewed_by` | `grep` on CSV file |
| 9 | Audit trail logged | Entries with `action: decision_reviewed` | `curl GET /audit/history` |
| 10 | No duplicate reviews | Same ID returns already-reviewed state on retry | Re-run Step 5, verify `reviewed_at` unchanged |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| No decisions found | Step 2 returns `total_decisions: 0` | 1. Verify pipeline feed is connected<br>2. Wait 5 minutes for new decisions<br>3. Check AI model service logs<br>4. If expected decisions missing, escalate to Admin |
| Review fails (403 Forbidden) | Step 5 returns HTTP 403 | 1. Verify token has not expired: `curl GET /decisions/?limit=1`<br>2. Re-authenticate with ANALYST or higher role<br>3. Check RBAC config in `.env` |
| Review fails (404 Not Found) | Step 5 returns HTTP 404 | 1. Verify decision ID spelling and case<br>2. Re-list decisions: `GET /decisions/?limit=10`<br>3. Decision may have been purged — select next available ID |
| Export empty | Step 8 produces 0-byte file | 1. Verify `GET /decisions/?limit=1` returns data<br>2. Check export endpoint permissions<br>3. Retry with explicit query params: `GET /decisions/export/csv?reviewed=true`<br>4. Verify disk space: `df -h /data/exports` |
| Export missing reviewed decisions | Step 9 shows `true` count < expected | 1. Verify decisions were actually reviewed: `GET /decisions/{id}`<br>2. Check export query includes all time ranges<br>3. Regenerate export after confirming reviews |
| Audit trail missing | Step 10 returns no review entries | 1. Check audit service is running<br>2. Verify `AUDIT_LOG_ENABLED=true` in `.env`<br>3. Check log file: `tail -n 50 logs/audit.log`<br>4. If audit service down, restart before continuing |

## 6. Related Runbooks

- [RB-005: Paper Trading Session](RB-005-PAPER-TRADING-SESSION.md)
- [RB-007: Backup Procedure](RB-007-BACKUP-PROCEDURE.md)
- [RB-008: Restore Procedure](RB-008-RESTORE-PROCEDURE.md)

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
