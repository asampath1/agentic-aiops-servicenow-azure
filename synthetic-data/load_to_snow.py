#!/usr/bin/env python3
"""
Load data/load_plan.json into a ServiceNow instance via the REST Table API,
and remove it again with --cleanup.

Credentials come from environment variables (never hard-code them):
  SN_INSTANCE   e.g. dev123456            (or full https://dev123456.service-now.com)
  SN_USER       e.g. admin
  SN_PASSWORD   your PDI admin password

Usage:
  python3 load_to_snow.py --dry-run          # resolve every reference offline, call nothing
  python3 load_to_snow.py                    # load everything
  python3 load_to_snow.py --only users,groups,group_members
  python3 load_to_snow.py --cleanup          # delete everything recorded in data/manifest.json

How references work: a value "@user:synth.arjun.iyer" means "the sys_id of the record
created with that _key"; "@lookup:table:field=value" is queried once from the instance.
Created sys_ids are saved to data/manifest.json after every record, so a failed run can
be resumed (already-created keys are skipped) and cleanup knows exactly what to delete.
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:  # dry-run still works without requests
    requests = None


class Snow:
    def __init__(self, dry):
        self.dry = dry
        if dry:
            return
        inst = os.environ.get("SN_INSTANCE", "").strip()
        user, pw = os.environ.get("SN_USER"), os.environ.get("SN_PASSWORD")
        if not (inst and user and pw):
            sys.exit("Set SN_INSTANCE, SN_USER and SN_PASSWORD environment variables first.")
        if requests is None:
            sys.exit("pip install requests")
        self.base = inst if inst.startswith("http") else f"https://{inst}.service-now.com"
        self.s = requests.Session()
        self.s.auth = (user, pw)
        self.s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _req(self, method, url, **kw):
        for attempt in range(5):
            r = self.s.request(method, url, timeout=60, **kw)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            return r
        return r

    def query_one(self, table, field, value):
        if self.dry:
            return f"dry-{table}-{value}"[:32]
        r = self._req("GET", f"{self.base}/api/now/table/{table}",
                      params={"sysparm_query": f"{field}={value}", "sysparm_fields": "sys_id", "sysparm_limit": 1})
        r.raise_for_status()
        res = r.json()["result"]
        return res[0]["sys_id"] if res else None

    def insert(self, table, body):
        if self.dry:
            return uuid.uuid4().hex, None
        r = self._req("POST", f"{self.base}/api/now/table/{table}", json=body,
                      params={"sysparm_fields": "sys_id,number", "sysparm_input_display_value": "false"})
        if r.status_code >= 300:
            return None, f"{r.status_code} {r.text[:300]}"
        res = r.json()["result"]
        return res["sys_id"], res.get("number")

    def patch(self, table, sys_id, body):
        if self.dry:
            return None
        r = self._req("PATCH", f"{self.base}/api/now/table/{table}/{sys_id}", json=body)
        return None if r.status_code < 300 else f"{r.status_code} {r.text[:200]}"

    def delete(self, table, sys_id):
        if self.dry:
            return True
        r = self._req("DELETE", f"{self.base}/api/now/table/{table}/{sys_id}")
        return r.status_code in (200, 204, 404)


def load(args):
    data_dir = Path(args.data)
    plan = json.loads((data_dir / "load_plan.json").read_text())
    man_path = data_dir / ("manifest.dryrun.json" if args.dry_run else "manifest.json")
    manifest = json.loads(man_path.read_text()) if man_path.exists() and not args.dry_run else {"records": {}}
    created = manifest["records"]           # _key -> {table, sys_id, number}
    lookups = {}
    sn = Snow(args.dry_run)
    only = set(args.only.split(",")) if args.only else None
    errors = 0

    def resolve(v):
        if not (isinstance(v, str) and v.startswith("@")):
            return v
        if v.startswith("@lookup:"):
            if v not in lookups:
                _, table, cond = v.split(":", 2)
                field, value = cond.split("=", 1)
                lookups[v] = sn.query_one(table, field, value)
                if not lookups[v]:
                    print(f"  ! lookup not found: {table} {field}={value} (field left empty)")
            return lookups[v]
        key = v[1:]
        if key not in created:
            raise KeyError(f"unresolved reference {v}")
        return created[key]["sys_id"]

    for stage in plan["stages"]:
        if only and stage["stage"] not in only:
            continue
        recs = stage["records"]
        print(f"== {stage['stage']} ({len(recs)})")
        done = 0
        for rec in recs:
            key, table = rec["_key"], rec["_table"]
            if key in created:
                continue
            body = {k: resolve(v) for k, v in rec.items() if not k.startswith("_")}
            body = {k: v for k, v in body.items() if v not in (None, "")}
            sys_id, info = sn.insert(table, body)
            if not sys_id and rec.get("_retry_drop"):
                for f in rec["_retry_drop"]:
                    body.pop(f, None)
                sys_id, info = sn.insert(table, body)
            if not sys_id:
                errors += 1
                print(f"  x {key}: {info}")
                continue
            created[key] = {"table": table, "sys_id": sys_id, "number": info}
            if rec.get("_post_patch"):
                err = sn.patch(table, sys_id, rec["_post_patch"])
                if err:
                    print(f"  ~ {key}: timestamp patch failed ({err})")
            done += 1
            if not args.dry_run:
                man_path.write_text(json.dumps(manifest, indent=1))
            if done % 25 == 0:
                print(f"  ... {done}")
            if args.delay:
                time.sleep(args.delay)
        print(f"  created {done}")
    man_path.write_text(json.dumps(manifest, indent=1))
    # map eval keys -> real incident numbers for convenience
    gt_path = data_dir / "ground_truth.json"
    if gt_path.exists():
        gt = json.loads(gt_path.read_text())
        for g in gt:
            g["number"] = created.get(g["key"], {}).get("number")
            if g.get("related_change"):
                g["related_change_number"] = created.get(g["related_change"], {}).get("number")
            if g.get("related_problem"):
                g["related_problem_number"] = created.get(g["related_problem"], {}).get("number")
        (data_dir / ("ground_truth.loaded.dryrun.json" if args.dry_run else "ground_truth.loaded.json")).write_text(json.dumps(gt, indent=1))
    print(f"\nDone. {len(created)} records in manifest, {errors} errors. Manifest: {man_path}")
    return errors


def cleanup(args):
    data_dir = Path(args.data)
    man_path = data_dir / "manifest.json"
    if not man_path.exists():
        sys.exit("No data/manifest.json - nothing to clean up.")
    manifest = json.loads(man_path.read_text())
    sn = Snow(args.dry_run)
    # delete in reverse creation order (incidents first, users last)
    items = list(manifest["records"].items())[::-1]
    print(f"Deleting {len(items)} records ...")
    left = {}
    for i, (key, m) in enumerate(items, 1):
        if not sn.delete(m["table"], m["sys_id"]):
            left[key] = m
        if i % 50 == 0:
            print(f"  ... {i}")
    manifest["records"] = dict(reversed(list(left.items())))
    man_path.write_text(json.dumps(manifest, indent=1))
    print(f"Done. {len(left)} records could not be deleted (kept in manifest).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--dry-run", action="store_true", help="resolve references offline, no API calls")
    ap.add_argument("--only", help="comma-separated stages to load")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep between records")
    ap.add_argument("--cleanup", action="store_true", help="delete everything listed in the manifest")
    a = ap.parse_args()
    if a.cleanup:
        cleanup(a)
    else:
        sys.exit(1 if load(a) else 0)
