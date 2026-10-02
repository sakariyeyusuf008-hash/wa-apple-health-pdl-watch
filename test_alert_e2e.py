"""End-to-end test of the alert path against the real live PDL.

Doctors the baseline so the real live file looks like it has changed, runs the
real script, confirms it alerts, then restores the true baseline.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = r"C:\Users\yusuf\OneDrive\Documents\WA-PDL-Watcher"
SNAP = os.path.join(HERE, "baseline.json")
ALERT = os.path.join(HERE, "ALERT.txt")
PY = r"C:\Users\yusuf\AppData\Local\Programs\Python\Python312\python.exe"

backup = SNAP + ".bak"
shutil.copy(SNAP, backup)

try:
    # Pretend we last saw Baqsimi with no PA. The live file says PA=Y, so this
    # should register as a change going the other way.
    with open(SNAP, encoding="utf8") as f:
        base = json.load(f)
    for ndc, rec in base["current"]["drugs"].items():
        if rec["LABEL NAME"].upper() == "BAQSIMI":
            rec["PHARMACY PA STATUS"] = "N"
            rec["NON CLINICAL TYPE"] = ""
    with open(SNAP, "w", encoding="utf8") as f:
        json.dump(base, f, indent=2, sort_keys=True)

    if os.path.exists(ALERT):
        os.remove(ALERT)

    print("Running the real script against the real live PDL...")
    r = subprocess.run([PY, os.path.join(HERE, "pdl_watch.py"), "--quiet"],
                       capture_output=True, text=True, timeout=900)

    print(r.stdout[-2500:])
    if r.stderr.strip():
        print("STDERR:", r.stderr[-1000:])

    print(f"\nexit code: {r.returncode}  (expected 1)")
    ok = r.returncode == 1
    print(f"{'PASS' if ok else 'FAIL'}  exit code signals a change")

    exists = os.path.exists(ALERT)
    print(f"{'PASS' if exists else 'FAIL'}  ALERT.txt was written")
    if exists:
        body = open(ALERT, encoding="utf8").read()
        print("\n--- ALERT.txt ---")
        print(body)
        hit = "00548835101" in body and "PHARMACY PA STATUS" in body
        print(f"{'PASS' if hit else 'FAIL'}  alert names the NDC and the field that moved")

    # the script rewrites the baseline on a change; confirm it now matches live
    with open(SNAP, encoding="utf8") as f:
        now = json.load(f)
    baq = [d for d in now["current"]["drugs"].values() if d["LABEL NAME"].upper() == "BAQSIMI"]
    pa = [d for d in baq if d["PHARMACY PA STATUS"] == "Y"]
    print(f"{'PASS' if pa else 'FAIL'}  baseline re-synced to the live state ({len(pa)} Baqsimi NDCs with PA)")

    sys.exit(0 if (ok and exists) else 1)
finally:
    shutil.copy(backup, SNAP)
    os.remove(backup)
    print("\nTrue baseline restored.")
