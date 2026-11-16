"""Diagnostics agent: pick KQL for the CI type, query Log Analytics, extract signals."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Optional

from .connectors.base import LogAnalyticsClient
from .models import Incident, parse_ts

# KQL per resource family (by Azure naming prefix). {r} is the resource name.
KQL = {
    # isfuzzy: a Linux-only workspace has no Event table, a Windows-only one no Syslog. Linux names the memory
    # counter 'Available MBytes Memory'. Process names come from Syslog/Event (Linux Perf has no per-process data).
    "vm": ("union isfuzzy=true "
           "(Perf | where Computer startswith '{r}' and CounterName in ('% Processor Time','Available MBytes',"
           "'Available MBytes Memory','% Free Space') and InstanceName in ('total','_Total','/','C:','Memory') "
           "| summarize avg(CounterValue) by CounterName, InstanceName, bin(TimeGenerated, 5m)), "
           "(Heartbeat | where Computer startswith '{r}' | summarize LastHeartbeat=max(TimeGenerated)), "
           "(Syslog | where Computer startswith '{r}' and SeverityLevel in ('warning','err','crit','alert','emerg') "
           "| project TimeGenerated, Message=strcat(ProcessName, ': ', SyslogMessage) | take 50), "
           "(Event | where Computer startswith '{r}' and EventLevelName in ('Error','Warning') | take 50)"),
    "sql": ("AzureDiagnostics | where Resource =~ '{r}' and Category in ('Blocks','QueryStoreRuntimeStatistics',"
            "'Errors','Timeouts') | take 100"),
    "app": "AppServiceHTTPLogs | where _ResourceId contains '{r}' and ScStatus >= 500 | summarize count() by ScStatus, CsUriStem",
    "func": "FunctionAppLogs | where _ResourceId contains '{r}' and Level in ('Error','Warning') | take 100",
    "kv": "AzureDiagnostics | where Resource =~ '{r}' and ResultType != 'Success' | project TimeGenerated, OperationName, ResultSignature, identity_claim_oid_g",
    "st": "StorageBlobLogs | where AccountName =~ '{r}' and StatusText != 'Success' | summarize count() by StatusText",
    "aks": "KubePodInventory | where ClusterName =~ '{r}' and ContainerStatusReason != '' | summarize count() by ContainerStatusReason, Name",
    "adf": "ADFActivityRun | where _ResourceId contains '{r}' and Status == 'Failed' | take 50",
    "sb": "AzureMetrics | where Resource =~ '{r}' and MetricName in ('ActiveMessages','DeadletteredMessages')",
    "rsv": "AddonAzureBackupJobs | where ResourceId contains '{r}' and JobStatus == 'Failed' | take 50",
    "vpngw": "AzureDiagnostics | where Resource =~ '{r}' and Category == 'TunnelDiagnosticLog' | take 50",
    "azfw": "AzureDiagnostics | where Resource =~ '{r}' and Category startswith 'AzureFirewall' | where msg_s has 'Deny' | take 50",
    "redis": "AzureMetrics | where Resource =~ '{r}'",
}

_SIGNALS = [
    ("process", re.compile(r"\b([\w.-]+\.exe|sqlservr|java|python3)\b", re.I)),
    ("error_code", re.compile(r"\b(AADSTS\d+|[A-Z][a-z]+(?:[A-Z][a-z]+)+(?:Error|Failed\w*|Exception|BackOff|Forbidden)|"
                              r"ExtensionSnapshot\w+|UserError\w+|CrashLoopBackOff|ServerBusy\w*|NET::\w+)\b")),
    ("http_status", re.compile(r"\b(?:HTTP\s*)?([45]\d\d)\b")),
    ("update", re.compile(r"\b(KB\d{6,})\b")),
    ("percent", re.compile(r"(\d{2,3}(?:\.\d)?%)")),
    ("version", re.compile(r"\bv?(\d+\.\d+\.\d+)\b")),
]


def family(ci: Optional[str]) -> Optional[str]:
    if not ci:
        return None
    prefix = ci.split("-", 1)[0].lower()
    return prefix if prefix in KQL else None


class DiagnosticsAgent:
    name = "diagnostics"

    # 2 h before the incident (to 30 min after it is opened): long enough for a slowly building fault, short enough
    # that an unrelated earlier event on the same CI stays out. On the live demo a 24 h window carried a CPU fault's
    # Syslog line into a disk incident 1h43m later; the offline eval scores the same from 1 h to 24 h.
    def __init__(self, logs: LogAnalyticsClient, hours: int = 2):
        self.logs, self.hours = logs, hours

    def run(self, inc: Incident) -> dict[str, Any]:
        fam = family(inc.ci)
        if not fam:
            return {"ran": False, "reason": "no Azure resource on the incident", "queries": [], "signals": {}, "findings": []}
        kql = KQL[fam].format(r=inc.ci)
        try:
            rows = self.logs.query(kql, inc.ci, self.hours, end=parse_ts(inc.opened_at) + timedelta(minutes=30)
                                   if inc.opened_at else None)
        except Exception as e:  # telemetry is best-effort; triage continues without it
            return {"ran": False, "reason": f"query failed: {e}", "queries": [kql], "signals": {}, "findings": []}
        texts = [str(r.get("Message") or " ".join(f"{k}={v}" for k, v in r.items())) for r in rows]
        # Signals come only from log messages (Syslog, Event, alert text) and the description: numeric rows
        # such as Perf averages ("avg_CounterValue=526.9") would otherwise pass for HTTP status codes.
        messages = [str(r["Message"]) for r in rows if r.get("Message")]
        signals: dict[str, list[str]] = {}
        for name, rx in _SIGNALS:
            found = []
            for t in messages + [inc.description]:
                for m in rx.findall(t):
                    if m not in found:
                        found.append(m)
            if found:
                signals[name] = found[:5]
        return {"ran": True, "resource": inc.ci, "family": fam, "queries": [kql], "row_count": len(rows),
                "findings": texts[:8], "signals": signals}
