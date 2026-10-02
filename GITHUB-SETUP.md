# Putting the watcher on GitHub Actions

Your laptop cannot email you when it is switched off. GitHub Actions can: a
scheduled job runs on GitHub's servers, checks the PDL, and emails you the
same alert. Free.

This folder is the repository. Push it and you are done.

## Before you start

Nothing here is secret. The repo contains public HCA drug-list data and the
Python that reads it. Your Gmail app password is **not** in the code — it goes
into GitHub Secrets, step 3 below, and is never committed.

Two things to check with your IT team if you want to, though there is nothing
in this code for them to worry about: the repo reads a public government
spreadsheet, and the only personal data is your email address in a secret.

**Make the repo public, not private.** GitHub silently disables scheduled
workflows in a private repository after 60 days without activity — and if
nothing changes for two months, nothing gets committed, so nothing counts as
activity. That failure is invisible until you need the alert. A public repo
does not have this problem, and there is nothing in here worth hiding.

---

## Route A - install Git, then push (recommended)

About five minutes, one download. Repeatable if you ever change the code.

**1. Install Git for Windows** — https://git-scm.com/download/win — accept the
defaults. Then **close and reopen PowerShell**.

**2. Create the repo on GitHub.** Go to https://github.com/new

- Repository name: `wa-apple-health-pdl-watch`
- Choose **Public**
- Do **not** tick "Add a README" (it creates a branch with a commit in it)
- Create it

**3. Add the secrets.** In the new repo: **Settings → Secrets and variables →
Actions → New repository secret**. Add these six:

| Secret | Value |
|---|---|
| `PDL_SMTP_HOST` | `smtp.gmail.com` |
| `PDL_SMTP_PORT` | `587` |
| `PDL_SMTP_USER` | your Google address |
| `PDL_SMTP_PASS` | your 16-character app password, no spaces |
| `PDL_SMTP_FROM` | your Google address |
| `PDL_SMTP_TO` | who should be notified |

If the form only shows a "New secret" button, that is fine.

**4. Push the code.** In PowerShell, from this folder:

```powershell
cd "C:\Users\yusuf\OneDrive\Documents\WA-PDL-Watcher"
git init
git add .
git commit -m "WA Apple Health PDL watcher"
git remote add origin https://github.com/YOUR-USERNAME/wa-apple-health-pdl-watch.git
git push -u origin main
```

Replace `YOUR-USERNAME`. Git will ask for your GitHub username and a personal
access token as the password — **not your GitHub password.** If it asks,
GitHub will show you where to create a token, or use one from
https://github.com/settings/tokens with the `repo` scope.

**5. Test it.** Go to the **Actions** tab, click **WA Apple Health PDL watch**,
then **Run workflow**. A green tick and "No changes in the rescue glucagon
class" means it works. The run page will show the full table of the class
without you opening the email.

---

## Route B - no Git, browser only

Slower, and GitHub's file uploader **refuses any file or folder whose name
starts with a dot** — which rules out `.github` and `.gitignore`. Create those
two through the web editor instead.

**1.** Create the repo at https://github.com/new, public, no README.

**2.** For each file below: **Add file → Create new file**, type the path in the
box, paste the contents, then **Commit changes**.

| Path | Where to get it |
|---|---|
| `.github/workflows/pdl-watch.yml` | this folder |
| `.gitignore` | this folder |
| `pdl_watch.py` | this folder |
| `brief.py` | this folder |

**3.** Add the six secrets as in Route A, step 3.

**4.** Now drag-upload the remaining files from this folder, which have no dots
in their names: `baseline.json`, `README.md`, `test_watch.py`, `test_brief.py`,
`test_email.py`, `Run Check.bat`, `Install Schedule.ps1`, `demo_alert.py`,
`test_alert_e2e.py`.

`baseline.json` is the important one. Without it the first run has nothing to
compare against and will report every product as new.

**5.** Run it once from the **Actions** tab.

---

## What happens each day

1. At 15:20 UTC — 07:20 Pacific in winter, 08:20 in summer — GitHub starts a job
2. It downloads HCA's live PDL and the pre-release
3. No change: nothing happens, job stays green
4. Change: you get the same brief by email, and the run page shows the full
   table. `baseline.json` is committed back so tomorrow compares against today

The run page is worth knowing about. Every run is kept for 90 days with a
`pdl-history` artifact, so if you ever need to show how long a restriction was
in place, there is a record.

## When it goes wrong

**The job stops running after a few weeks.** GitHub pauses scheduled workflows
in inactive repos, and emails you about it. Re-enabling is one click in the
Actions tab. It only really affects private repos — another reason Route A and
step 1 tell you to go public.

**Runs get delayed.** Free accounts queue workflows during busy periods, so
15:20 UTC can land up to about 15 minutes late. Irrelevant for a daily check
against a list that republishes weekly.

**You want to check now.** Actions tab → the workflow → **Run workflow**.

**You want the old one to stop.** On your laptop:

```powershell
Unregister-ScheduledTask -TaskName 'WA Apple Health PDL Watch' -Confirm:$false
```

Running both means duplicate emails on the day something changes. Keeping the
laptop one is still fine as a belt-and-braces check — it just means you may get
two copies of the same alert.
