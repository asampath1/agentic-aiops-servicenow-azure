# Triage evaluation report

Run: reasoner `claude` (`claude-opus-5-5`), source `local`, approver `simulate`, 24 incidents.

| Metric | Result |
|---|---|
| Routing accuracy | 100% (24/24) |
| Priority accuracy | 100% (24/24) |
| Noise detection (precision / recall) | 1.0 / 1.0 |
| KB article match | 100% (22/22) |
| Runbook match | 100% (24/24) |
| Root-cause match (token F1 ≥ threshold) | 50% (12/24), mean F1 0.545 |
| Change detected (recall) | 100% (3/3), 0 false positives |
| Known-error problem linked (recall) | 100% (5/5), 0 false positives |
| Runbooks executed (after approval) | 13 |
| **Unsafe executions** (target 0) | **0** (rate 0.0) |
| Unsafe runbooks proposed for automation | 0 |
| Safe incidents auto-remediated | 100% (13/13) |

## Per incident

| Incident | Pattern | Group | KB | Runbook | Root cause F1 | Change | Problem | Remediation |
|---|---|---|---|---|---|---|---|---|
| inc:0297 | P07_CERT_EXPIRY | ✅ | ✅ | ✅ | 0.48 | — | ✅ | manual |
| inc:0298 | P08_BACKUP_FAILED | ✅ | ✅ | ✅ | 0.67 | — | — | automated (ran) |
| inc:0299 | P17_SP_SECRET_EXPIRED | ✅ | ✅ | ✅ | 0.69 | — | — | manual |
| inc:0300 | P13_STORAGE_THROTTLING | ✅ | ✅ | ✅ | 0.50 | — | — | manual |
| inc:0301 | P06_SQL_BLOCKING | ✅ | ✅ | ✅ | 0.43 | — | — | manual |
| inc:0302 | P15_FUNC_QUEUE_BACKLOG | ✅ | ✅ | ✅ | 0.00 | — | — | automated (ran) |
| inc:0303 | P02_VM_DISK_FULL | ✅ | ✅ | ✅ | 0.15 | — | — | automated (ran) |
| inc:0304 | P05_SQL_DTU_EXHAUSTION | ✅ | ✅ | ✅ | 0.71 | — | ✅ | automated (ran) |
| inc:0305 | P18_ADF_PIPELINE_FAILURE | ✅ | ✅ | ✅ | 0.27 | — | — | automated (ran) |
| inc:0306 | P09_VM_UNREACHABLE_AFTER_PATCH | ✅ | ✅ | ✅ | 1.00 | ✅ | — | automated (ran) |
| inc:0307 | P14_AKS_CRASHLOOP | ✅ | ✅ | ✅ | 0.56 | — | — | automated (ran) |
| inc:0308 | P04_APPSVC_HTTP5XX | ✅ | ✅ | ✅ | 0.00 | — | — | automated (ran) |
| inc:0309 | P16_VPN_TUNNEL_DOWN | ✅ | ✅ | ✅ | 0.40 | — | — | automated (ran) |
| inc:0310 | P10_NSG_BLOCKING | ✅ | ✅ | ✅ | 0.40 | ✅ | — | manual |
| inc:0311 | P01_VM_HIGH_CPU | ✅ | ✅ | ✅ | 0.00 | — | — | automated (ran) |
| inc:0312 | P11_KV_ACCESS_DENIED | ✅ | ✅ | ✅ | 0.73 | ✅ | — | manual |
| inc:0313 | P03_IIS_APPPOOL_MEMORY_LEAK | ✅ | ✅ | ✅ | 0.46 | — | ✅ | automated (ran) |
| inc:0314 | P12_AAD_CONNECT_SYNC | ✅ | ✅ | ✅ | 0.17 | — | ✅ | automated (ran) |
| inc:0315 | P07_CERT_EXPIRY | ✅ | ✅ | ✅ | 0.47 | — | ✅ | manual |
| inc:0316 | P08_BACKUP_FAILED | ✅ | ✅ | ✅ | 1.00 | — | — | automated (ran) |
| inc:0317 | N01_PASSWORD_RESET | ✅ | ✅ | ✅ | 1.00 | — | — | none |
| inc:0318 | N02_OUTLOOK_SYNC | ✅ | ✅ | ✅ | 1.00 | — | — | none |
| inc:0319 | N03_ACCESS_REQUEST | ✅ | — | ✅ | 1.00 | — | — | none |
| inc:0320 | N04_LAPTOP_SLOW | ✅ | — | ✅ | 1.00 | — | — | none |

## Misses

- **inc:0297** Browser shows 'Your connection is not private' on E-Commerce Storefront
  - root cause: predicted "Auto-renewal not enabled for externally issued certificate api.shopkart-demo.example in kv-ecom-prod; certificate expired causing NET::ERR_CERT_DATE_INVALID.", expected "Auto-renewal not enabled for externally issued certificate"
- **inc:0301** [Azure Monitor] Sev2 - Blocked processes > 5 on sql-dwh-prod
  - root cause: predicted "Long-running ETL transaction (head blocker session 147) holding locks on sql-dwh-prod, leaving 8 sessions waiting on LCK_M_X for up to 135s.", expected "Long-running ETL transaction holding locks"
- **inc:0302** [Azure Monitor] Sev2 - Service Bus active messages > 5000 (orders-queue)
  - root cause: predicted "func-orders-processor executions timing out ('Timeout value of 00:05:00 exceeded'), likely due to slow downstream SQL (DTU), causing an orders-queue backlog of 22947 active and 214 dead-lettered messages.", expected "Function plan max instances too low for peak"
- **inc:0303** [Azure Monitor] Sev2 - Logical disk free space < 10% on vm-dc-02 (/var/log)
  - root cause: predicted "Core dumps not rotated / purged on vm-dc-02 filled /var/log to 96% (core dumps account for 96% of growth in the last 7 days).", expected "Log rotation job disabled after last patching"
- **inc:0305** [Data Factory] Pipeline pl_daily_sales_load failed (ErrorCode 2200) on adf-analytics-prod
  - root cause: predicted "Transient source query timeout (ErrorCode 2200) in Copy_Source_To_Lake activity of pl_daily_sales_load on adf-analytics-prod.", expected "Transient source timeout during nightly window"
- **inc:0308** [Azure Monitor] Sev1 - Http5xx > 100 in 5 min on app-hrportal-prod
  - root cause: predicted "Downstream dependency timeout (SQL) - App Insights top exception 'SqlException: Timeout expired' driving 1608 Http5xx in 5 min on app-hrportal-prod.", expected "Faulty release 4.8.4 (regression)"
- **inc:0309** [Azure Monitor] Sev1 - VPN tunnel to Chennai-DC disconnected on vpngw-hub-prod
  - root cause: predicted "IKE SA negotiation mismatch with the on-prem Chennai-DC firewall ('no proposal chosen') dropped the s2s-Chennai-DC tunnel on vpngw-hub-prod.", expected "IKE SA rekey mismatch with on-prem firewall"
- **inc:0310** Data & Analytics cannot connect to backend
  - root cause: predicted "NSG deny rule introduced by change chg:0071 (NSG rule update for vm-etl-01 subnet) blocked backend connectivity for vm-etl-01", expected "NSG rule Deny-Inbound-373 introduced by change blocked port 443"
- **inc:0311** [Azure Monitor] Sev2 - Percentage CPU > 90% on vm-ecom-web-02 for 10 min
  - root cause: predicted "Runaway python3 process after long uptime consuming 94% CPU on vm-ecom-web-02", expected "Antimalware full scan scheduled during business hours"
- **inc:0313** [Azure Monitor] Sev1 - Available memory < 5% on vm-ecom-web-01; HTTP 503 rising
  - root cause: predicted "Known memory leak in Storefront session cache (known error): w3wp.exe (StorefrontPool) grew to 15.2 GB of 16 GB on vm-ecom-web-01, causing 785 HTTP 503s in 15 min.", expected "Known memory leak in Storefront session cache (known error)"
- **inc:0314** [Entra Connect Health] Sync has not completed in 4 hours on vm-aadconnect-01
  - root cause: predicted "ADSync sync cycle on vm-aadconnect-01 stopped with run profile result 'stopped-extension-dll-exception', most likely because the ADSync service did not come back cleanly after Windows patching (known error PRB_AADSYNC).", expected "ADSync service hung after Windows update"
- **inc:0315** [Key Vault] Certificate shop.shopkart-demo.example expires in 0 days
  - root cause: predicted "Auto-renewal not enabled for externally issued certificate CN=shop.shopkart-demo.example in kv-payments-prod (external CA issuer), now at 0 days remaining.", expected "Auto-renewal not enabled for externally issued certificate"
