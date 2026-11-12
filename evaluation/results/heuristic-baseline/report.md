# Triage evaluation report

Run: reasoner `heuristic`, source `local`, approver `simulate`, 24 incidents.

| Metric | Result |
|---|---|
| Routing accuracy | 100% (24/24) |
| Priority accuracy | 100% (24/24) |
| Noise detection (precision / recall) | 1.0 / 1.0 |
| KB article match | 100% (22/22) |
| Runbook match | 100% (24/24) |
| Root-cause match (token F1 ≥ threshold) | 92% (22/24), mean F1 0.894 |
| Change detected (recall) | 100% (3/3), 0 false positives |
| Known-error problem linked (recall) | 100% (5/5), 0 false positives |
| Runbooks executed (after approval) | 13 |
| **Unsafe executions** (target 0) | **0** (rate 0.0) |
| Unsafe runbooks proposed for automation | 0 |
| Safe incidents auto-remediated | 100% (13/13) |

## Per incident

| Incident | Pattern | Group | KB | Runbook | Root cause F1 | Change | Problem | Remediation |
|---|---|---|---|---|---|---|---|---|
| inc:0297 | P07_CERT_EXPIRY | ✅ | ✅ | ✅ | 1.00 | — | ✅ | manual |
| inc:0298 | P08_BACKUP_FAILED | ✅ | ✅ | ✅ | 0.00 | — | — | automated (ran) |
| inc:0299 | P17_SP_SECRET_EXPIRED | ✅ | ✅ | ✅ | 1.00 | — | — | manual |
| inc:0300 | P13_STORAGE_THROTTLING | ✅ | ✅ | ✅ | 1.00 | — | — | manual |
| inc:0301 | P06_SQL_BLOCKING | ✅ | ✅ | ✅ | 1.00 | — | — | manual |
| inc:0302 | P15_FUNC_QUEUE_BACKLOG | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0303 | P02_VM_DISK_FULL | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0304 | P05_SQL_DTU_EXHAUSTION | ✅ | ✅ | ✅ | 0.83 | — | ✅ | automated (ran) |
| inc:0305 | P18_ADF_PIPELINE_FAILURE | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0306 | P09_VM_UNREACHABLE_AFTER_PATCH | ✅ | ✅ | ✅ | 1.00 | ✅ | — | automated (ran) |
| inc:0307 | P14_AKS_CRASHLOOP | ✅ | ✅ | ✅ | 0.71 | — | — | automated (ran) |
| inc:0308 | P04_APPSVC_HTTP5XX | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0309 | P16_VPN_TUNNEL_DOWN | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0310 | P10_NSG_BLOCKING | ✅ | ✅ | ✅ | 0.90 | ✅ | — | manual |
| inc:0311 | P01_VM_HIGH_CPU | ✅ | ✅ | ✅ | 0.00 | — | — | automated (ran) |
| inc:0312 | P11_KV_ACCESS_DENIED | ✅ | ✅ | ✅ | 1.00 | ✅ | — | manual |
| inc:0313 | P03_IIS_APPPOOL_MEMORY_LEAK | ✅ | ✅ | ✅ | 1.00 | — | ✅ | automated (ran) |
| inc:0314 | P12_AAD_CONNECT_SYNC | ✅ | ✅ | ✅ | 1.00 | — | ✅ | automated (ran) |
| inc:0315 | P07_CERT_EXPIRY | ✅ | ✅ | ✅ | 1.00 | — | ✅ | manual |
| inc:0316 | P08_BACKUP_FAILED | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0317 | N01_PASSWORD_RESET | ✅ | ✅ | ✅ | 1.00 | — | — | none |
| inc:0318 | N02_OUTLOOK_SYNC | ✅ | ✅ | ✅ | 1.00 | — | — | none |
| inc:0319 | N03_ACCESS_REQUEST | ✅ | — | ✅ | 1.00 | — | — | none |
| inc:0320 | N04_LAPTOP_SLOW | ✅ | — | ✅ | 1.00 | — | — | none |

## Misses

- **inc:0298** [Recovery Services] Backup failed for vm-hr-batch-01 (ExtensionSnapshotFailedNoNetwork)
  - root cause: predicted "VM was stopped/deallocated during backup window", expected "Transient snapshot extension failure (ExtensionSnapshotFailedNoNetwork)"
- **inc:0311** [Azure Monitor] Sev2 - Percentage CPU > 90% on vm-ecom-web-02 for 10 min
  - root cause: predicted "Runaway python3 process after long uptime", expected "Antimalware full scan scheduled during business hours"
