# WA Apple Health PDL Watch

Watches the Washington State Health Care Authority's **Apple Health (Medicaid)
Preferred Drug List** and tells you when anything changes in the rescue
glucagon class - Baqsimi, Gvoke, generic Glucagon Emergency Kit, Zegalogue.

It exists because of one finding: on the PDL effective **September 26-30, 2026**,
Baqsimi was the only rescue glucagon carrying a prior authorisation, flagged
`RAFORM` ("justification for use of the route of administration, strength or
dosage form" - i.e. the nasal spray), with **no published PA policy number**.
Every competitor in the class was preferred *and* PA-free.

The pre-release PDL for **October 1, 2026** removes that PA. This tool exists
so you find out when it actually happens, rather than assuming.

## What an alert looks like

An alert is a brief, not a diff. The subject line tells you which way it went
before you open it — `WA Apple Health PDL - Baqsimi good news`.

It is sent as **multipart/alternative**, so it reads properly either way:

| Client | What you get |
|---|---|
| Mail clients that render HTML | a real `<table>`, with a coloured GOOD/BAD badge and a highlighted verdict box |
| Everything else — plain-text panes, terminals, some corporate gateways | bullets and short before/after lines |

Both parts are generated from one interpretation in `brief.py`, so they can
never disagree about what changed or how good it is. If a client strips HTML
you still get the whole story, and if you forward the email the table usually
survives.

The plain-text part deliberately does **not** use a fixed-width table. A table
wide enough to hold these cells truncates mid-word at 80 columns and on a
phone, which is worse than no table. The HTML part is where the real table
lives.

Sections, in order:

| Section | Answers |
|---|---|
| **HEADLINE** | one sentence, plus FAVOURABLE / UNFAVOURABLE / NEUTRAL |
| **WHAT CHANGED, IN PLAIN TERMS** | bullets, one per field that moved |
| **BEFORE / AFTER** | every affected product, and its effect on Baqsimi |
| **WHY IT MATTERS** | why you should care, no jargon |
| **ONE PARAGRAPH, FOR FORWARDING** | paste it into an email to a colleague, unedited |
| **WHAT THIS DOES NOT PROVE** | the honest limits |
| **FIELD-BY-FIELD DETAIL** | the raw diff, for whoever asks |

Every product change carries a verdict — `GOOD`, `BAD`, `NEUTRAL` or `REVIEW` —
judged explicitly from Baqsimi's position by the rules in `brief.py`. `REVIEW`
means the tool refuses to guess, which is what happens when a product enters or
leaves the class: only a person can tell a new competitor from a new option for
patients.

Field codes never appear on their own. `PHARMACY PA STATUS: Y -> N` renders as
`PA required -> no PA`, and `RAFORM` as `route of administration`.

Send it to yourself:

```powershell
python demo_alert.py            # render it, and write demo_alert.html
python demo_alert.py --send     # and email it
```

Add `--plain-only` to `pdl_watch.py` if your mail gateway strips HTML.

## Why it is not a "check a webpage" script

Three things it does that a manual check would not:

- **It finds the files by reading HCA's page, not by hardcoding a URL.** HCA
  rotates the dated filenames every week. A hardcoded link silently goes stale
  and you stop watching without knowing.
- **It ignores the effective date.** HCA republishes weekly, so the date changes
  every single run. Only drug-level fields are diffed, so it only speaks when
  coverage actually moves.
- **It tracks the pre-release as well as the live list**, because that is where
  a change appears first and where you get warning.
- **It retries.** HCA serves a 12.5 MB spreadsheet and the link is often slow
  enough that a single attempt times out mid-file. A failed download is
  retried three times before it is believed, because a slow afternoon must
  never be mistaken for "HCA published nothing" — the one conclusion this tool
  must not draw by accident.

## Requirements

Python 3.9+. Nothing else - standard library only, no `pip install`.

## Use

```
python pdl_watch.py            # check; alerts if something changed
python pdl_watch.py --report   # print the current state of the class
python pdl_watch.py --save     # accept current state as the new baseline
python pdl_watch.py --popup    # also raise a Windows dialog on change
python pdl_watch.py --test-email   # send a test alert, no change needed
python test_watch.py           # 41 offline tests, no network
python test_email.py           # 13 tests: proves email really sends, via a local sink
python test_alert_e2e.py       # proves the alert path against the real live PDL
```

Or just double-click **`Run Check.bat`**.

Exit code is `1` when something changed, `0` when nothing did, `2` on a
network failure - so a scheduled task can act on it.

### See an alert without waiting

```powershell
python demo_alert.py            # render it
python demo_alert.py --send     # and email it to yourself
```

It runs the real diff, filter and render code over the **actual** live PDL and
**actual** pre-release PDL, so what you see is the real October 1 change and
not an illustration of one. Nothing is written to `baseline.json` or
`history.jsonl` - your watcher's state is untouched.

## Run it daily

Right-click **`Install Schedule.ps1`** and *Run as administrator*, or just run
it normally. Either way you get a working task; the difference is only *when*
it can run.

| Mode | When it runs | Needs admin |
|---|---|---|
| **S4U** | always - logged on, logged off, or asleep | yes |
| **Interactive** | daily at 08:20, plus 3 min after you log in | no |

The script tries S4U first and falls back to Interactive if elevation is
refused, so it never leaves you with no task at all.

**This gap is real, not theoretical.** On 30 September the task had not run
since 28 September: it sat in Interactive mode across two logged-off days and
missed both. The logon trigger covers a machine that was merely off, but not a
machine nobody signed into. If this is going to be your early-warning system,
install it as admin:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Install Schedule.ps1"
```

run from an elevated PowerShell window, then confirm:

```powershell
(Get-ScheduledTask -TaskName 'WA Apple Health PDL Watch').Principal.LogonType
```

You want `S4U`, not `Interactive`.

It runs without a desktop session, so it deliberately does **not** pop a
dialog - an invisible modal would hang the task forever. Instead it:

1. writes `ALERT.txt`
2. appends to `watch.log`, `sched.log` and `history.jsonl`
3. emails you, if you configure the mail settings below

To turn it off:

```powershell
Unregister-ScheduledTask -TaskName 'WA Apple Health PDL Watch' -Confirm:$false
```

### One gotcha worth knowing

The task launches `cmd.exe` rather than `python.exe` directly. That is not
decoration - pointing the action straight at `python.exe` fails with
`0xFFFFFFFF` and no output, because the console app gets no console to attach
to. The wrapper also gives you `sched.log` to read when a scheduled run
misbehaves. If you ever hand-edit the task, keep the wrapper.

Check on it with:

```powershell
Get-ScheduledTaskInfo -TaskName 'WA Apple Health PDL Watch'
```

`LastTaskResult` should be `0`. `267011` just means it has never run yet.

## Email alerts

You get an email when a **Baqsimi-relevant** change appears, and nothing when
only Zegalogue moves. Zegalogue is excluded on purpose - if the discontinued
dasiglucagon product changes you cannot act on it, and it would train you to
ignore alerts.

Watched: Baqsimi, Gvoke (all forms), generic Glucagon Emergency Kit, and any
product entering or leaving the class. The filter only decides what interrupts
you - the console, `watch.log` and `history.jsonl` always record everything.

To set it up, run **`Setup Email.ps1`**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Setup Email.ps1"
```

It prompts for your Google address and app password, saves them, and sends a
test message so you find out immediately if it works.

You need a **Google app password**, not your account password - Google rejects
the real one over SMTP:

1. Turn on [2-Step Verification](https://myaccount.google.com/security)
2. Create one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
   choosing *Other* and naming it `PDL Watch`

To verify at any time:

```powershell
python pdl_watch.py --test-email
```

Manual configuration, if you'd rather set it yourself:

| Variable | Google value |
|---|---|
| `PDL_SMTP_HOST` | `smtp.gmail.com` |
| `PDL_SMTP_PORT` | `587` |
| `PDL_SMTP_USER` | your address (used as both login and sender) |
| `PDL_SMTP_PASS` | the app password, spaces removed |
| `PDL_SMTP_TO` | who to notify, defaults to your own address |
| `PDL_SMTP_TLS` | `1`. Set `0` only for an internal relay or a local test |

To change what triggers an email, set `PDL_ALERT_SCOPE`:

```
PDL_ALERT_SCOPE=BAQSIMI,GVOKE     only these
PDL_ALERT_SCOPE=all               everything, including Zegalogue
```

### Restart? Not needed

Environment variables are only inherited by a process when it starts, so a
scheduled task registered *before* setup would otherwise sit there holding an
empty environment and silently never send email — the most confusing failure
this tool could have. So the watcher reads `HKCU\Environment` directly as a
fallback. Your normal environment still wins when it has a value; the registry
is only consulted when it does not.

Verified: the scheduled task sent a test email on a machine that had not been
restarted since setup.

### One thing worth knowing

**The app password is stored in plain text** in `HKCU\Environment`. It is
scoped to SMTP only and you can revoke it from the same Google page, which makes
it an acceptable trade for a local tool - but if it is not a trade you want,
skip email entirely. The watcher is fully functional without it; read
`ALERT.txt` and `history.jsonl` instead.

To clear it:

```powershell
'PDL_SMTP_HOST','PDL_SMTP_PORT','PDL_SMTP_USER','PDL_SMTP_PASS',`
 'PDL_SMTP_FROM','PDL_SMTP_TO','PDL_SMTP_TLS' | ForEach-Object {
  Remove-Item "HKCU:\Environment\$_" -ErrorAction SilentlyContinue }
```

## Files

| File | What it is |
|---|---|
| `pdl_watch.py` | the watcher: download, diff, alert |
| `brief.py` | turns a diff into something a human can read and forward |
| `test_brief.py` | 58 tests for the wording and the favourable/unfavourable judgement |
| `test_watch.py` | 52 offline tests, no network needed |
| `test_email.py` | runs a throwaway SMTP server on localhost and proves the alert actually sends. Blocks registry access so it can never mail your real account. |
| `test_alert_e2e.py` | hits the real PDL to prove the alert actually fires. Temporarily doctors the baseline, then restores it. |
| `demo_alert.py` | renders a real alert from the live and pre-release PDLs. `--send` emails it. Changes nothing. |
| `Setup Email.ps1` | configures Gmail alerts and sends a test message |
| `baseline.json` | last-seen state; the diff is against this |
| `history.jsonl` | every run appended - a growing timeline |
| `watch.log` | plain text log |
| `ALERT.txt` | written only when something changes |
| `sched.log` | output of the scheduled run - read this when checking the task worked |
| `Run Check.bat` | one-click manual run |
| `Install Schedule.ps1` | registers the daily task |

`ALERT.txt`, `baseline.json` and `history.jsonl` are yours - `history.jsonl` is
worth keeping as a record. It is a defensible timeline if you ever need to show
how long a PA was in place.

## What it does not cover

Being straight about the limits, because this is access data and an
over-confident read is worse than none:

- **It watches the state PDL only.** Managed care plans are required to use
  HCA's criteria, but they can and do layer their own utilisation management on
  top. Whatever is actually rejecting your prescriptions at the pharmacy is
  most likely an MCO-level edit this cannot see.
- **A published PDL is not a live claims system.** The list changing on Oct 1
  means the benefit design changed, not that every pharmacy stopped rejecting.
  Confirm with a live fill.
- **It tracks the rescue glucagon class only.** If you want a broader watch,
  widen `DRUG_CLASS` and `DRUG_RE` at the top of `pdl_watch.py`.
