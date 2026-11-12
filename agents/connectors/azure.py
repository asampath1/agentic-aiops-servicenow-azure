"""Live Azure connectors: Log Analytics (query) and Azure Automation (runbook jobs).

Both authenticate with ``azure-identity``'s ``DefaultAzureCredential`` (az login, managed
identity, or AZURE_CLIENT_ID/SECRET/TENANT_ID). Install the extras only when going live::

    pip install azure-identity azure-monitor-query requests

Environment:
  LOG_ANALYTICS_WORKSPACE_ID            workspace (customer) id GUID
  AZURE_SUBSCRIPTION_ID, AUTOMATION_RESOURCE_GROUP, AUTOMATION_ACCOUNT

Not exercised in CI (no subscription there). The offline mocks implement the same interfaces.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .base import AutomationClient, LogAnalyticsClient


class AzureLogAnalytics(LogAnalyticsClient):
    def __init__(self, workspace_id: str | None = None, credential=None):
        from azure.identity import DefaultAzureCredential
        from azure.monitor.query import LogsQueryClient

        self.workspace_id = workspace_id or os.environ["LOG_ANALYTICS_WORKSPACE_ID"]
        self.client = LogsQueryClient(credential or DefaultAzureCredential())

    def query(self, kql: str, resource: Optional[str], hours: int = 24,
              end: Optional[datetime] = None) -> list[dict[str, Any]]:
        from azure.monitor.query import LogsQueryStatus

        span = (end.replace(tzinfo=end.tzinfo or timezone.utc) - timedelta(hours=hours),
                end.replace(tzinfo=end.tzinfo or timezone.utc)) if end else timedelta(hours=hours)
        resp = self.client.query_workspace(self.workspace_id, kql, timespan=span)
        tables = resp.tables if resp.status == LogsQueryStatus.SUCCESS else (resp.partial_data or [])
        rows = []
        for t in tables:
            for row in t.rows:
                rows.append(dict(zip(t.columns, row)))
        return rows


class AzureAutomation(AutomationClient):
    """Starts runbook jobs through the ARM REST API (Microsoft.Automation/automationAccounts/jobs)."""

    API = "2023-11-01"

    def __init__(self, subscription_id: str | None = None, resource_group: str | None = None,
                 account: str | None = None, credential=None):
        import requests
        from azure.identity import DefaultAzureCredential

        self.sub = subscription_id or os.environ["AZURE_SUBSCRIPTION_ID"]
        self.rg = resource_group or os.environ["AUTOMATION_RESOURCE_GROUP"]
        self.account = account or os.environ["AUTOMATION_ACCOUNT"]
        self.cred = credential or DefaultAzureCredential()
        self.http = requests.Session()

    def start_runbook(self, runbook: str, parameters: dict[str, Any]) -> dict[str, Any]:
        token = self.cred.get_token("https://management.azure.com/.default").token
        job_name = str(uuid.uuid4())
        url = (f"https://management.azure.com/subscriptions/{self.sub}/resourceGroups/{self.rg}/providers/"
               f"Microsoft.Automation/automationAccounts/{self.account}/jobs/{job_name}?api-version={self.API}")
        body = {"properties": {"runbook": {"name": runbook},
                               "parameters": {k: str(v) for k, v in parameters.items()}}}
        r = self.http.put(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        r.raise_for_status()
        props = r.json().get("properties", {})
        return {"job_id": job_name, "runbook": runbook, "parameters": parameters,
                "status": props.get("status", "New"), "simulated": False}
