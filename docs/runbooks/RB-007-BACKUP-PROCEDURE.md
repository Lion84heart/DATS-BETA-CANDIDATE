# RB-007: Backup Procedure

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** OPERATOR, ADMIN

---

## 1. Purpose

Create a verified backup archive of the DATS platform, including code, configuration, and data, with SHA-256 checksums for integrity validation.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Platform Running | FastAPI server responding on port 8000 | `curl -s http://localhost:8000/health` returns HTTP 200 |
| Disk Space Available | At least 500 MB free in target directory | `df -h /backup` shows `Avail >= 500M` |
| Backup Directory Exists | `/backup/` directory created and writable | `ls -ld /backup` shows `drwxrwxr-x` |
| Scripts Accessible | `scripts/create_backup.sh` exists and executable | `ls -l scripts/create_backup.sh` shows executable bit |
| System Quiescent | No active paper trading or batch operations | `GET /execution/paper/status` returns `stopped`; no active batch jobs |

## 3. Procedure

### Step 1: Verify System State

```bash
curl -s -X GET http://localhost:8000/health | jq .
df -h /backup
```

**Expected outcome:**
```json
{"status": "ok"}
```
```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   45G   55G  45% /
```

Ensure `Avail` is at least 500 MB.

### Step 2: Verify No Active Trading Sessions

```bash
curl -s -X GET http://localhost:8000/execution/paper/status \
  -H "Authorization: Bearer $TOKEN" | jq '.status'
```

**Expected outcome:**
```
"stopped"
```

If status is `running`, stop the session before proceeding:
```bash
curl -s -X POST http://localhost:8000/execution/paper/stop \
  -H "Authorization: Bearer $TOKEN"
```

### Step 3: Create ZIP Archive

```bash
cd /opt/DATS-BETA-CANDIDATE && \
zip -r /backup/DATS-BETA-CANDIDATE_backup_$(date +%Y%m%d_%H%M%S).zip \
  . -x "*.pyc" -x "__pycache__/*" -x ".git/*" -x "venv/*" -x "*.log"
```

**Expected outcome:**
```
  adding: app/ (stored 0%)
  adding: app/main.py (deflated 62%)
  adding: app/routers/ (stored 0%)
  adding: config/ (stored 0%)
  adding: data/ (stored 0%)
  adding: scripts/ (stored 0%)
  adding: tests/ (stored 0%)
  adding: requirements.txt (deflated 45%)
  adding: .env.example (deflated 30%)
```

Archive path example: `/backup/DATS-BETA-CANDIDATE_backup_20260808_093012.zip`

### Step 4: Create tar.gz Archive

```bash
cd /opt/DATS-BETA-CANDIDATE && \
tar -czf /backup/DATS-BETA-CANDIDATE_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
  --exclude='venv' --exclude='*.log' .
```

**Expected outcome:**
```
tar: .: file changed as we read it
```

If the warning appears, it is benign (logs written during archive creation). The archive is still valid.

Archive path example: `/backup/DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz`

### Step 5: Generate SHA-256 Checksums

```bash
cd /backup && \
sha256sum DATS-BETA-CANDIDATE_backup_20260808_093012.zip \
  > DATS-BETA-CANDIDATE_backup_20260808_093012.zip.sha256 && \
sha256sum DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz \
  > DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz.sha256
```

**Expected outcome:** Two `.sha256` files created, each containing a 64-character hex hash and filename.

Example content:
```
a1b2c3d4e5f6... (64 hex chars)  DATS-BETA-CANDIDATE_backup_20260808_093012.zip
f6e5d4c3b2a1... (64 hex chars)  DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz
```

### Step 6: Verify Checksums

```bash
cd /backup && \
sha256sum -c DATS-BETA-CANDIDATE_backup_20260808_093012.zip.sha256 && \
sha256sum -c DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz.sha256
```

**Expected outcome:**
```
DATS-BETA-CANDIDATE_backup_20260808_093012.zip: OK
DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz: OK
```

### Step 7: Generate Backup Manifest

```bash
cat > /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json << 'EOF'
{
  "backup_id": "BK-20260808-093015",
  "timestamp": "2026-08-08T09:30:15Z",
  "platform_version": "DATS Beta v1.0",
  "operator": "admin",
  "archives": [
    {
      "format": "zip",
      "filename": "DATS-BETA-CANDIDATE_backup_20260808_093012.zip",
      "sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
      "size_bytes": 52428800
    },
    {
      "format": "tar.gz",
      "filename": "DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz",
      "sha256": "f6e5d4c3b2a1987654321098765432109876fedcba0987654321fedcba098765",
      "size_bytes": 48828125
    }
  ],
  "exclusions": [
    "*.pyc",
    "__pycache__/*",
    ".git/*",
    "venv/*",
    "*.log"
  ],
  "test_status": "183/183 passing"
}
EOF
```

**Expected outcome:** File `/backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json` created with valid JSON.

### Step 8: Validate Manifest Integrity

```bash
python3 -m json.tool /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json > /dev/null && echo "Manifest valid JSON"
ls -lh /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json
```

**Expected outcome:**
```
Manifest valid JSON
-rw-r--r-- 1 admin admin 1.2K Aug  8 09:31 /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json
```

### Step 9: Verify Archive Contents

```bash
unzip -l /backup/DATS-BETA-CANDIDATE_backup_20260808_093012.zip | tail -5
tar -tzf /backup/DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz | wc -l
```

**Expected outcome:**
```
  1234 files
```
Both archives should report the same (or very similar) file count. Verify key files are present:

```bash
unzip -l /backup/DATS-BETA-CANDIDATE_backup_20260808_093012.zip | grep -E "(main\.py|requirements\.txt|\.env\.example)"
```

**Expected outcome:** Lines showing `app/main.py`, `requirements.txt`, and `.env.example` in the archive.

### Step 10: Store Manifest in Persistent Location

```bash
cp /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json \
   /data/backups/manifests/
cp /backup/*.sha256 /data/backups/manifests/
```

**Expected outcome:** Manifest and checksum files copied to `/data/backups/manifests/`.

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | ZIP archive created | File exists, size > 1 MB | `ls -lh /backup/*.zip` |
| 2 | tar.gz archive created | File exists, size > 1 MB | `ls -lh /backup/*.tar.gz` |
| 3 | SHA-256 checksum generated | 64-character hex hash in `.sha256` file | `cat /backup/*.sha256` |
| 4 | Checksum verifies | `sha256sum -c` returns `OK` for both | `sha256sum -c *.sha256` |
| 5 | Manifest valid JSON | `python3 -m json.tool` exits 0 | `python3 -m json.tool manifest.json` |
| 6 | Manifest contains all fields | `backup_id`, `timestamp`, `archives`, `sha256` present | `jq 'keys, .archives[].sha256' manifest.json` |
| 7 | Key files in archive | `main.py`, `requirements.txt` present in ZIP listing | `unzip -l` + `grep` |
| 8 | File counts match | ZIP and tar.gz report similar file counts | `unzip -l` and `tar -tzf` |
| 9 | Manifest stored persistently | Copy exists in `/data/backups/manifests/` | `ls /data/backups/manifests/` |
| 10 | Disk space after backup | At least 100 MB free remaining | `df -h /backup` |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Backup fails (ZIP error) | Step 3 returns `zip error: Nothing to do` | 1. Verify current directory: `pwd`<br>2. Ensure `/opt/DATS-BETA-CANDIDATE` exists and contains files<br>3. Check permissions: `ls -la /opt/DATS-BETA-CANDIDATE`<br>4. Retry from correct directory |
| Backup fails (tar error) | Step 4 returns `tar: Exiting with failure` | 1. Verify sufficient disk space: `df -h /backup`<br>2. Check for open files: `lsof +D /opt/DATS-BETA-CANDIDATE`<br>3. Retry with `--warning=no-file-changed` flag<br>4. If persistent, stop FastAPI server and retry |
| Disk full during backup | Step 3 or 4 fails with "No space left on device" | 1. Check disk: `df -h /backup`<br>2. Remove old backups: `find /backup -name "*.zip" -mtime +30 -delete`<br>3. Compress logs: `gzip /opt/DATS-BETA-CANDIDATE/logs/*.log`<br>4. Re-run backup after freeing space |
| Checksum mismatch | Step 6 returns `FAILED` | 1. Re-generate checksum: `sha256sum archive.zip > archive.zip.sha256`<br>2. If still mismatched, archive corrupted during write — delete and re-create<br>3. Check disk health: `smartctl -H /dev/sda` |
| Manifest generation fails | Step 7 produces invalid JSON | 1. Validate template syntax<br>2. Use `python3 -c "import json; json.load(open('manifest.json'))"`<br>3. Re-create manifest manually with correct field values |
| Missing key files in archive | Step 9 shows `main.py` absent | 1. Verify source file exists: `ls /opt/DATS-BETA-CANDIDATE/app/main.py`<br>2. Check exclusion patterns did not over-match<br>3. Re-create archive without overly broad `--exclude` patterns |

## 6. Related Runbooks

- [RB-005: Paper Trading Session](RB-005-PAPER-TRADING-SESSION.md)
- [RB-006: Decision Review Workflow](RB-006-DECISION-REVIEW-WORKFLOW.md)
- [RB-008: Restore Procedure](RB-008-RESTORE-PROCEDURE.md)

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
