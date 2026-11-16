#!/usr/bin/env python3
"""Add the close-code choice the live loop uses when it auto-resolves an incident.

    python3 infra/servicenow/add_close_code.py            # dry run: show what exists / would be added
    python3 infra/servicenow/add_close_code.py --apply    # add the choice (idempotent)

Uses SN_INSTANCE / SN_USER / SN_PASSWORD. Adds a sys_choice row (a new value for the existing close-code field),
not a new incident State: filter auto-fixed incidents with State = Resolved AND Close code = Auto-remediated (AIOps).
Releases differ in which field is the close code (label "Close code" or "Resolution code"); every such field gets
the choice, and the script prints the field name(s) the Logic App must set (its closeCodeField parameter).
"""
import argparse
import os
import sys

import requests

VALUE = LABEL = "Auto-remediated (AIOps)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually insert the choice (default: dry run)")
    a = ap.parse_args()
    inst = os.environ["SN_INSTANCE"]
    base = inst if inst.startswith("http") else f"https://{inst}.service-now.com"
    s = requests.Session()
    s.auth = (os.environ["SN_USER"], os.environ["SN_PASSWORD"])
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def get(table, query, fields):
        r = s.get(f"{base}/api/now/table/{table}", params={"sysparm_query": query, "sysparm_fields": fields,
                                                            "sysparm_limit": 100}, timeout=60)
        r.raise_for_status()
        return r.json()["result"]

    fields = {"close_code"}
    for d in get("sys_dictionary", "name=incident^column_labelINResolution code,Close code", "element,column_label"):
        fields.add(d["element"])
    print("close-code field(s) on incident:", ", ".join(sorted(fields)))

    for f in sorted(fields):
        if get("sys_choice", f"name=incident^element={f}^value={VALUE}", "sys_id"):
            print(f"  incident.{f}: '{VALUE}' already present")
            continue
        if not a.apply:
            print(f"  incident.{f}: would add '{VALUE}' (run with --apply)")
            continue
        r = s.post(f"{base}/api/now/table/sys_choice", timeout=60, json={
            "name": "incident", "element": f, "value": VALUE, "label": LABEL, "language": "en",
            "sequence": "900", "inactive": "false"})
        print(f"  incident.{f}: {'added' if r.status_code < 300 else f'FAILED {r.status_code} {r.text[:200]}'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
