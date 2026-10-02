"""Watch the Washington Apple Health Preferred Drug List for changes to rescue glucagon.

Tracks Baqsimi and every competitor in the class (Gvoke, generic Glucagon
Emergency Kit, Zegalogue) and tells you when HCA changes a coverage, preferred
or prior-authorization field.

No dependencies - standard library only, same as the Territory Planner.

    python pdl_watch.py              check, alert if changed
    python pdl_watch.py --report     print current state, no alerting
    python pdl_watch.py --save       accept current state as the new baseline
    python pdl_watch.py --popup      also show a Windows dialog on change

Exit code 1 if something changed, 0 otherwise.
"""

import argparse
import datetime as dt
import io
import json
import os
import re
import smtplib
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from email.message import EmailMessage

import brief

PDL_PAGE = ("https://www.hca.wa.gov/billers-providers-partners/"
            "program-information-providers/apple-health-preferred-drug-list-pdl")
FALLBACK_LIVE = "https://www.hca.wa.gov/assets/billers-and-providers/apple-health-preferred-drug-list.xlsx"

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(HERE, "baseline.json")
HISTORY = os.path.join(HERE, "history.jsonl")
LOG = os.path.join(HERE, "watch.log")
ALERT = os.path.join(HERE, "ALERT.txt")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

DRUG_CLASS = "ANTIDIABETICS : DIABETIC OTHER"
DRUG_RE = re.compile(r"GLUCAGON|BAQSIMI|GVOKE|ZEGALOGUE|DASIGLUCAGON", re.I)

# What is worth being woken up for. Zegalogue is excluded on purpose: if the
# discontinued dasiglucagon product moves, there is nothing to do about it and
# it would train you to ignore the alerts.
#
# Override with PDL_ALERT_SCOPE as a comma-separated list of substrings matched
# against the label name, or "all" for everything. Default: everything except
# Zegalogue.
DEFAULT_SCOPE = ("BAQSIMI", "GLUCAGON", "GVOKE")
NOISE = ("ZEGALOGUE",)

# Only these fields can change in a way that matters. Blanks are meaningful -
# a cleared NON CLINICAL TYPE is a real change, so "" is stored and compared.
FIELDS = [
    "LABEL NAME", "STRENGTH", "DOSE FORM",
    "PHARMACY PREFERRED STATUS", "NUMBER OF PREFERRED", "PHARMACY PA STATUS",
    "NON CLINICAL TYPE", "PA POLICY NUMBER",
    "AHPDL INCLUSION", "MCO CARVE OUT", "COVERAGE TYPE",
]

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

def get(url, timeout=300, label=None, attempts=3):
    """Download with retries.

    HCA serves a 12.5 MB spreadsheet and the link is often slow enough that a
    single attempt times out mid-file. Without retries a slow afternoon reads
    as "HCA published nothing", which is the one conclusion this tool must
    never draw by accident.
    """
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return _download(url, timeout, label)
        except Exception as e:
            last = e
            if attempt < attempts:
                wait = 5 * attempt
                quiet_log(f"{label or url}: attempt {attempt} failed "
                          f"({type(e).__name__}: {e}); retrying in {wait}s")
                if TTY[0] and QUIET[0] is False:
                    sys.stderr.write(f"\n  {label}: attempt {attempt} failed "
                                     f"({type(e).__name__}); retrying in {wait}s\n")
                    sys.stderr.flush()
                time.sleep(wait)
    raise last


def _download(url, timeout, label=None):
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        total = int(r.headers.get("Content-Length") or 0)
        chunks, got = [], 0
        while True:
            b = r.read(262144)
            if not b:
                break
            chunks.append(b)
            got += len(b)
            if label and QUIET[0] is False and TTY[0]:
                pct = f"{got * 100 // total}%" if total else f"{got // 1048576} MB"
                sys.stderr.write(f"\r  {label}: {pct}  ({time.time() - t0:5.1f}s)")
                sys.stderr.flush()
        if label and QUIET[0] is False and TTY[0]:
            sys.stderr.write("\r" + " " * 60 + "\r")
            sys.stderr.flush()
    data = b"".join(chunks)
    if not data:
        raise ValueError("server returned an empty file")
    if QUIET[0]:
        quiet_log(f"downloaded {label or url} ({len(data)} bytes) "
                  f"in {time.time() - t0:.1f}s")
    return data


def anchors(html):
    out = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", html, re.S | re.I):
        attrs, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        h = re.search(r'href\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
        if h:
            out.append((h.group(1), re.sub(r"\s+", " ", text).strip()))
    return out


def discover():
    """Find the current and pre-release PDL links straight from HCA's page.

    HCA rotates the dated filenames weekly, so hardcoding them breaks. The
    live one keeps a stable name, but we read the page anyway so that if HCA
    ever renames even that, this still finds it.
    """
    html = None
    for attempt in range(1, 4):
        try:
            html = get(PDL_PAGE, timeout=60, attempts=1).decode("utf8", "ignore")
            break
        except Exception as e:
            quiet_log(f"PDL page attempt {attempt} failed: {type(e).__name__}: {e}")
            time.sleep(4 * attempt)
    if html is None:
        log("could not read the PDL page at all; falling back to the known live URL")
        return {"current": FALLBACK_LIVE, "prerelease": None, "dated": []}

    found = {"current": None, "prerelease": None, "dated": []}
    for href, text in anchors(html):
        if not href.lower().endswith(".xlsx"):
            continue
        url = urllib.parse.urljoin(PDL_PAGE, href)
        if "pre-release" in text.lower() or "-pr-" in href.lower():
            found["prerelease"] = url
        elif re.search(r"\d{1,2}/\d{1,2}/\d{4}", text):
            found["dated"].append((text, url))
        elif "preferred-drug-list" in href.lower() and not found["current"]:
            found["current"] = url

    if not found["current"]:
        found["current"] = FALLBACK_LIVE
        log("live PDL link not found on the page; using the known URL")
    return found


# --------------------------------------------------------------------------
# parse
# --------------------------------------------------------------------------

def colidx(ref):
    n = 0
    for ch in re.match(r"([A-Z]+)", ref).group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def parse(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = ["".join(t.text or "" for t in si.iter(NS + "t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(NS + "si")]

    rows = []
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(NS + "row"):
        cells = {}
        for c in r.findall(NS + "c"):
            t, v, isel = c.get("t"), c.find(NS + "v"), c.find(NS + "is")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif isel is not None:
                val = "".join(x.text or "" for x in isel.iter(NS + "t"))
            elif v is not None:
                val = v.text
            else:
                val = ""
            cells[colidx(c.get("r"))] = (val or "").strip()
        if cells:
            rows.append(cells)
    if len(rows) < 4:
        raise ValueError("file too short to be a PDL")
    if rows[0].get(0) != "Apple Health (Medicaid) Preferred Drug List":
        raise ValueError("not a PDL file (unexpected title)")

    hdr = next((c for c in rows if c.get(0) == "PRODUCT IDENTIFIER"), None)
    if hdr is None:
        raise ValueError("no header row")

    drugs = {}
    for c in rows:
        if c.get(2) != DRUG_CLASS:
            continue
        label = c.get(3, "")
        if label.upper().startswith("DILUENT"):
            continue
        if not DRUG_RE.search(label + " " + c.get(4, "")):
            continue
        ndc = c.get(0)
        rec = {h: c.get(i, "") for i, h in hdr.items()}
        drugs[ndc] = {f: rec.get(f, "") for f in FIELDS}
        drugs[ndc]["NDC"] = ndc
    return {"effective": rows[2].get(0, "?"), "drugs": drugs}


def quiet_log(msg):
    """Progress for --quiet runs, which still need to say something in sched.log."""
    try:
        with open(LOG, "a", encoding="utf8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except OSError:
        pass


QUIET = [False]
CI = [False]
# Progress only animates on a real terminal. Piped to a file or captured by a
# scheduler, the carriage returns turn into one line per percent, which is
# unreadable and bloats sched.log.
TTY = [False]


def job_summary(body, title="Baqsimi coverage change"):
    """Append to a CI job summary, if the runner offers one.

    GitHub Actions exposes $GITHUB_STEP_SUMMARY. Writing there means the alert
    is readable in the browser without opening the logs or the email, which is
    the difference between noticing this and not noticing it.
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    try:
        with open(path, "a", encoding="utf8") as f:
            f.write(f"### {title}\n\n```\n{body}\n```\n")
        return True
    except OSError as e:
        log(f"could not write the job summary: {e}")
        return False


ISSUE_TITLE = "Baqsimi coverage change detected"


def github_issue(subject, body):
    """Post the alert as a comment on one long-lived GitHub issue.

    This needs no secrets at all. A GitHub Actions job already holds a
    GITHUB_TOKEN with issues:write, so there is nothing to configure, nothing
    to leak, and no app password sitting in a third party's secret store. GitHub
    emails you when the issue is touched, which is the notification.

    One issue is reused and commented on rather than a new one each time, so the
    history reads as a timeline of changes instead of a pile of duplicates.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    if not token or not repo:
        return False

    def call(method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"{api}{path}", data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}",
                                              "Accept": "application/vnd.github+json",
                                              "User-Agent": UA,
                                              "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        return json.loads(raw) if raw else {}

    try:
        # find the rolling issue, if it is already open
        found = call("GET", f"/repos/{repo}/issues?state=open&per_page=100")
        existing = next((i for i in found if i.get("title") == ISSUE_TITLE
                         and "pull_request" not in i), None)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        comment = f"### {subject}\n\n{stamp}\n\n{body}"
        if existing:
            call("POST", f"/repos/{repo}/issues/{existing['number']}/comments",
                 {"body": comment})
            quiet_log(f"commented on issue #{existing['number']}")
        else:
            call("POST", f"/repos/{repo}/issues",
                 {"title": ISSUE_TITLE, "body": comment})
            quiet_log("opened the rolling coverage issue")
        return True
    except Exception as e:
        log(f"could not post the GitHub issue: {type(e).__name__}: {e}")
        return False


def collect():
    links = discover()
    out = {}
    for slot in ("current", "prerelease"):
        if not links[slot]:
            continue
        try:
            if not QUIET[0]:
                print(f"  fetching the {slot} list ({links[slot].rsplit('/', 1)[-1]})...")
            out[slot] = parse(get(links[slot], label=slot))
        except Exception as e:
            log(f"failed to retrieve {slot} ({links[slot]}): {type(e).__name__}: {e}")
            if QUIET[0] is False:
                print(f"  WARNING: could not get the {slot} list - "
                      f"{type(e).__name__}: {e}")
    return out


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------

def diff(old, new):
    """Return [(kind, ndc, label, field, before, after)] for every field that moved.

    The label travels with the change so the alert filter can decide whether
    the change is worth interrupting you for.
    """
    changes = []
    ondc, nndc = set(old.get("drugs", {})), set(new.get("drugs", {}))
    for ndc in sorted(nndc - ondc):
        changes.append(("ADDED", ndc, new["drugs"][ndc].get("LABEL NAME", "?"), "", "", ""))
    for ndc in sorted(ondc - nndc):
        changes.append(("REMOVED", ndc, old["drugs"][ndc].get("LABEL NAME", "?"), "", "", ""))
    for ndc in sorted(ondc & nndc):
        a, b = old["drugs"][ndc], new["drugs"][ndc]
        label = a.get("LABEL NAME", "?")
        for f in FIELDS:
            if a.get(f, "") != b.get(f, ""):
                changes.append(("CHANGED", ndc, label, f,
                                a.get(f, "") or "(blank)", b.get(f, "") or "(blank)"))
    return changes


def scope():
    raw = setting("PDL_ALERT_SCOPE")
    if not raw:
        return DEFAULT_SCOPE
    if raw.strip().lower() == "all":
        return None
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip())


def relevant(changes):
    """Keep only the changes worth an email / a dialog.

    Never hides anything from the console, watch.log or history.jsonl - those
    record every change in the class. This only decides what interrupts you.
    """
    want = scope()
    if want is None:
        return list(changes)
    keep = []
    for c in changes:
        kind, label = c[0], c[2].upper()
        # anything entering or leaving the class is worth knowing about
        if kind in ("ADDED", "REMOVED"):
            keep.append(c)
        elif any(w in label for w in want):
            keep.append(c)
    return keep


def format_changes(changes):
    """Render changes grouped by product, with NDC lists collapsed.

    One step-therapy change on a generic with 10 NDCs is 10 identical lines if
    you print a line per NDC. Nobody reads 28 lines of an email, so field
    changes are folded together and the NDCs are listed once per product.
    """
    products = {}          # (kind, label) -> [ndcs in order]
    product_order = []
    fields = {}            # (kind, label, field, before, after) -> set(ndcs)
    field_order = []

    for kind, ndc, label, field, before, after in changes:
        pkey = (kind, label)
        if pkey not in products:
            products[pkey] = []
            product_order.append(pkey)
        if ndc not in products[pkey]:
            products[pkey].append(ndc)

        fkey = (kind, label, field, before, after)
        if fkey not in fields:
            fields[fkey] = []
            field_order.append(fkey)
        if ndc not in fields[fkey]:
            fields[fkey].append(ndc)

    lines = []
    for pkey in product_order:
        kind, label = pkey
        ndcs = products[pkey]
        head = ", ".join(ndcs[:3]) + (f" +{len(ndcs) - 3} more" if len(ndcs) > 3 else "")
        marker = "~" if kind == "CHANGED" else kind[0]
        lines.append(f"  {marker} {label}")
        lines.append(f"      NDCs ({len(ndcs)}): {head}")
        for fkey in field_order:
            if fkey[0] != pkey[0] or fkey[1] != pkey[1]:
                continue
            _, _, field, before, after = fkey
            if field:
                affected = len(fields[fkey])
                tail = f"  [{affected} NDC(s)]" if affected < len(ndcs) else ""
                lines.append(f"      {field}: {before}  ->  {after}{tail}")
            else:
                lines.append(f"      {kind.lower()} from the PDL")
    return "\n".join(lines)


def fingerprint(snap):
    return json.dumps(snap, sort_keys=True)


# --------------------------------------------------------------------------
# notify
# --------------------------------------------------------------------------

def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def popup(title, body):
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          f"[System.Windows.Forms.MessageBox]::Show(@'{body}@','{title}')")
    os.system(f'powershell -NoProfile -Command "{ps}"')


def setting(name, default=None):
    """Read a setting, falling back to the Windows user environment block.

    Environment variables are only inherited by a process when it starts, so a
    scheduled task registered before Setup Email.ps1 ran would be holding an
    empty environment and would silently never send email - the single most
    confusing failure this tool could have. Reading HKCU\\Environment as a
    fallback means it does not matter: the settings are found either way.

    An empty value is treated as absent, so a blank variable cannot mask a real
    one in the registry.
    """
    v = os.environ.get(name)
    if v:
        return v
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
                v, _ = winreg.QueryValueEx(k, name)
            if v:
                return v
        except (FileNotFoundError, OSError, ImportError):
            pass
    return default


def email(subject, text, html_body=None):
    """Send the alert. Returns True only if the server accepted it.

    Silently does nothing when PDL_SMTP_HOST is unset, so an unconfigured
    watcher is not an error.

    With an HTML part this becomes multipart/alternative: mail clients show
    the table, everything else shows the bullet version. Both parts carry the
    same content, so neither can be the only one that works.
    """
    host = setting("PDL_SMTP_HOST")
    if not host:
        return False
    try:
        port = int(setting("PDL_SMTP_PORT", "587"))
        msg = EmailMessage()
        sender = setting("PDL_SMTP_FROM") or setting("PDL_SMTP_USER") or "pdl-watch@localhost"
        msg["From"] = sender
        # Nobody has ever wanted an alert sent to a different person than it
        # came from, so the recipient defaults to the sender.
        msg["To"] = setting("PDL_SMTP_TO") or sender
        msg["Subject"] = subject
        msg.set_content(text)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(host, port, timeout=30) as s:
            # STARTTLS is on by default. Set PDL_SMTP_TLS=0 only for an internal
            # relay on a trusted network, or to test against a local sink.
            if setting("PDL_SMTP_TLS", "1") != "0":
                s.starttls()
            user = setting("PDL_SMTP_USER")
            if user:
                s.login(user, setting("PDL_SMTP_PASS", ""))
            s.send_message(msg)
        return True
    except Exception as e:
        log(f"email failed: {type(e).__name__}: {e}")
        return False


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

COLS = [("NDC", 13), ("PRODUCT", 27), ("FORM", 11), ("PREF", 5),
        ("PA", 4), ("STEP", 5), ("TYPE", 9), ("POLICY", 6)]


def print_state(slot, snap):
    print(f"\n  {slot.upper()}  --  {snap['effective']}")
    print("  " + "".join(h.ljust(w) for h, w in COLS))
    print("  " + "-" * (sum(w for _, w in COLS) + 2))
    baq = [d for d in snap["drugs"].values() if d["LABEL NAME"].upper() == "BAQSIMI"]
    others = [d for d in snap["drugs"].values() if d["LABEL NAME"].upper() != "BAQSIMI"]
    for d in sorted(baq + others, key=lambda x: x["LABEL NAME"]):
        mark = ">> " if d["LABEL NAME"].upper() == "BAQSIMI" else "   "
        vals = [d["NDC"], d["LABEL NAME"][:25], d["DOSE FORM"][:9],
                d["PHARMACY PREFERRED STATUS"] or "-",
                d["PHARMACY PA STATUS"] or "-",
                d["NUMBER OF PREFERRED"] or "-",
                d["NON CLINICAL TYPE"] or "-",
                d["PA POLICY NUMBER"] or "-"]
        print("  " + mark + "".join(v.ljust(w) for v, (_, w) in zip(vals, COLS)))
    pa = [d for d in baq if d["PHARMACY PA STATUS"] == "Y"]
    print(f"\n  Baqsimi PA status: {'PRIOR AUTH REQUIRED' if pa else 'no PA required'}"
          f"   ({len(baq)} Baqsimi NDCs)")


def append_history(event, found, changes):
    with open(HISTORY, "a", encoding="utf8") as f:
        f.write(json.dumps({
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "effective": {k: v["effective"] for k, v in found.items()},
            "changes": {k: [list(c) for c in v] for k, v in changes.items()},
        }) + "\n")


def send_test_email():
    """Send a real alert email so the config can be verified without waiting
    for an actual PDL change."""
    if not setting("PDL_SMTP_HOST"):
        print("Not configured. Set PDL_SMTP_HOST (and the rest) first, "
              "or run Setup Email.ps1")
        return 2
    body = ("This is a test from the WA Apple Health PDL watcher.\n\n"
            "If you are reading this, email works. You will only get a real\n"
            "alert when a Baqsimi-relevant coverage change appears in the\n"
            "rescue glucagon class.\n\n"
            f"Watching scope: {scope() or 'all products in the class'}\n"
            "Tracked       : Baqsimi, Gvoke (all forms), generic Glucagon\n"
            "                Emergency Kit. Zegalogue changes are logged but\n"
            "                will not email you.\n"
            f"Sent          : {dt.datetime.now():%Y-%m-%d %H:%M}\n"
            f"Log           : {LOG}")
    ok = email("WA Apple Health PDL Watch - test alert (not a real change)", body)
    if ok:
        print(f"Test email sent to {setting('PDL_SMTP_TO') or '(no PDL_SMTP_TO)'}")
        return 0
    print("Test email FAILED. Details in watch.log:")
    try:
        print("  " + open(LOG, encoding="utf8").read().strip().splitlines()[-1])
    except Exception:
        pass
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print state, no alerting")
    ap.add_argument("--save", action="store_true", help="set current state as baseline")
    ap.add_argument("--popup", action="store_true", help="Windows dialog on change")
    ap.add_argument("--test-email", action="store_true",
                    help="send a test alert now, without needing a real change")
    ap.add_argument("--plain-only", action="store_true",
                    help="send bullets only, no HTML table part")
    ap.add_argument("--ci", action="store_true",
                    help="running unattended: exit 0 on a detected change and "
                         "write a job summary if the CI provides one")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    CI[0] = a.ci
    QUIET[0] = a.quiet
    TTY[0] = sys.stderr.isatty()
    if a.test_email:
        return send_test_email()

    if not a.quiet:
        print(f"Reading HCA's PDL page and downloading the current + pre-release lists...")
    found = collect()
    if not found:
        print("Could not retrieve any PDL. Check the network and try again.")
        return 2

    for slot in ("current", "prerelease"):
        if slot in found and not a.quiet:
            print_state(slot, found[slot])

    if a.report:
        return 0

    if a.save or not os.path.exists(SNAPSHOT):
        with open(SNAPSHOT, "w", encoding="utf8") as f:
            json.dump(found, f, indent=2, sort_keys=True)
        print(f"\nBaseline written: {SNAPSHOT}")
        with open(HISTORY, "a", encoding="utf8") as f:
            f.write(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"),
                                "event": "baseline saved",
                                "effective": {k: v["effective"] for k, v in found.items()}}) + "\n")
        return 0

    with open(SNAPSHOT, encoding="utf8") as f:
        baseline = json.load(f)

    changed_slots = {}
    for slot, snap in found.items():
        if slot not in baseline:
            changed_slots[slot] = [("NEW SLOT", slot, slot,
                                    "first time this list has been tracked", "")]
            continue
        ch = diff(baseline[slot], snap)
        if ch:
            changed_slots[slot] = ch

    if not changed_slots:
        print("\nNo changes in the rescue glucagon class.")
        append_history("no change", found, {})
        return 0

    all_lines = []
    for slot, changes in changed_slots.items():
        all_lines.append(f"=== {slot}  ({found[slot]['effective']}) ===")
        all_lines.append(format_changes(changes))
    everything = "\n".join(all_lines)

    print("\n" + "!" * 78)
    print("CHANGE DETECTED IN THE RESCUE GLUCAGON CLASS")
    print("!" * 78)
    print(everything)

    append_history("CHANGE", found, changed_slots)
    log("CHANGE DETECTED\n" + everything)

    # new baseline, so the next run is quiet
    with open(SNAPSHOT, "w", encoding="utf8") as f:
        json.dump(found, f, indent=2, sort_keys=True)

    # Notifications are filtered. Everything above, in history and in the log,
    # is complete - the filter only decides what is allowed to interrupt you.
    notify_slots = {s: relevant(c) for s, c in changed_slots.items()}
    notify_slots = {s: c for s, c in notify_slots.items() if c}
    subject = "WA Apple Health PDL - Baqsimi coverage change"
    if not notify_slots:
        print("\nNo Baqsimi-relevant change. Nothing emailed or alerted - "
              "logged in history.jsonl only.")
        return 0

    # The brief explains the change; the raw diff is kept inside it at the
    # bottom so nothing is lost. The subject says which way it went, because
    # that is the only thing read before opening.
    all_notify = [c for changes in notify_slots.values() for c in changes]
    baq_notify = [c for c in all_notify if brief.classify(c[2]) == "baqsimi"]
    if baq_notify:
        v = brief.verdict_for(baq_notify)
        tag = {"FAVOURABLE": "good news", "UNFAVOURABLE": "bad news",
               "NEUTRAL": "no change", "REVIEW": "needs review"}[v]
        subject = f"WA Apple Health PDL - Baqsimi {tag}"
    else:
        subject = "WA Apple Health PDL - rescue glucagon class change"

    briefs = []
    for slot, changes in notify_slots.items():
        m = brief.model(baseline.get(slot, {"drugs": {}}), found[slot],
                        changes, format_changes)
        briefs.append(m)
    text = "\n".join(brief.build_text(m) for m in briefs)
    html_body = "\n".join(brief.build_html(m) for m in briefs)

    with open(ALERT, "w", encoding="utf8") as f:
        f.write(f"PDL change detected {dt.datetime.now():%Y-%m-%d %H:%M}\n\n{text}\n")

    sent = email(subject, text, None if a.plain_only else html_body)
    posted = github_issue(subject, text)
    job_summary(text)
    if not setting("PDL_SMTP_USER"):
        print("\nEmail: not configured - see GITHUB-SETUP.md if you want it")
    else:
        print(f"\nEmail: {'sent' if sent else 'NOT sent (see watch.log)'}")
    if posted:
        print("GitHub: posted to the rolling coverage issue (GitHub will notify you)")
    if a.popup:
        popup("WA PDL change", text[:1800])
    # A change we were built to detect is a successful run, not a broken one.
    # Returning 1 in CI would paint every good catch red and train you to
    # ignore red. A failure to retrieve the list still returns 2 above.
    return 0 if CI[0] else 1


if __name__ == "__main__":
    sys.exit(main())
