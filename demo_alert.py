"""Show what an alert actually looks like, using the real watcher code.

It takes the live PDL and the pre-release PDL - the two files HCA publishes
today - and runs the genuine diff / filter / render path over them. The
transition between those two files IS the October 1 change, so this is not a
made-up scenario: it is the real one, computed the way a real alert would be.

Nothing is written to baseline.json or history.jsonl. Your watcher's state is
untouched.

    python demo_alert.py            # show it, do not send
    python demo_alert.py --send     # also email it to the configured address
"""

import json
import os
import sys
import datetime as dt

import pdl_watch as W
import brief


def banner(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    print("Fetching the live PDL and the pre-release from HCA...")
    found = W.collect()
    if "current" not in found or "prerelease" not in found:
        print("Could not retrieve both lists right now. Try again shortly.")
        return 2

    cur, pre = found["current"], found["prerelease"]

    banner("WHAT YOU GET WHEN THE ALERT FIRES")
    print("The watcher compares what it recorded last time against what it just")
    print("downloaded. Simulating the October 1 transition, live file -> pre-release:\n")
    print(f"  live PDL       : {cur['effective']}")
    print(f"  pre-release PDL: {pre['effective']}")

    changes = W.diff(cur, pre)
    if not changes:
        print("\n  (no differences right now - the two files currently agree)")
        return 0

    keep = W.relevant(changes)
    baq = [c for c in keep if brief.classify(c[2]) == "baqsimi"]
    v = brief.verdict_for(baq) if baq else "NEUTRAL"
    m = brief.model(cur, pre, keep, W.format_changes)

    banner("THE EMAIL")
    subject = f"WA Apple Health PDL - Baqsimi {v.lower()}"
    print(f"  Subject: {subject}")
    print(f"  From:    {W.setting('PDL_SMTP_FROM')}")
    print(f"  To:      {W.setting('PDL_SMTP_TO')}")
    print(f"  Parts:   text/plain (bullets) + text/html (table)")
    print()
    banner("THE PLAIN-TEXT VERSION  (what non-HTML clients see)")
    print(brief.build_text(m))

    banner("THE HTML VERSION  (what mail clients show - this is a real table)")
    print("  rendered to a file so you can open it in a browser:")
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_alert.html")
    with open(html_path, "w", encoding="utf8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'>"
                "<title>WA PDL alert - demo</title></head><body>"
                + brief.build_html(m) + "</body></html>")
    print(f"    {html_path}")

    banner("HOW THE FILTER APPLIED")
    print(f"  {len(changes)} field changes found in total")
    print(f"  {len(keep)} passed the Baqsimi-relevant filter and were included")
    print(f"  {len(changes) - len(keep)} were filtered out")
    print(f"  scope: {W.scope() or 'everything in the class'}")
    print(f"  verdict on the Baqsimi rows: {v}")

    if "--send" in sys.argv:
        banner("SENDING IT FOR REAL")
        ok = W.email(subject, brief.build_text(m), brief.build_html(m))
        print("sent" if ok else "FAILED - see watch.log")
        if not ok:
            return 2
    else:
        print("\n(run with --send to email this to yourself)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
