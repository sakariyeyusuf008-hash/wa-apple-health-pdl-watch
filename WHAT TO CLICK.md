# What to click

You have already done the hard part. This is everything that is left, in
order, and most of it is optional.

Your repo: **github.com/sakariyeyusuf008-hash/wa-apple-health-pdl-watch**

---

## Do nothing, and it still works

That is the short answer. You do not have to set anything up.

The job runs by itself every morning at about 7am Pacific. If HCA changes
anything about Baqsimi, it posts the finding to an issue in your repo, and
GitHub emails you to say so.

**Next run: tomorrow morning.** Nothing else to do.

---

## Optional 1 - check it works today

Two clicks, takes about 3 minutes:

1. Open **github.com/sakariyeyusuf008-hash/wa-apple-health-pdl-watch/actions**
2. Click **WA Apple Health PDL Watch** on the left
3. Click the green **Run workflow** button on the right
4. Wait for a green tick

**A green tick means it works.** You will see the words
`No changes in the rescue glucagon class` — that is correct, not an error. It
means it checked and nothing had moved, which is true: HCA has not published
the change yet.

You will also get an email from GitHub the first time you watch notifications
(see below).

---

## Optional 2 - make sure GitHub emails you

GitHub does not email you about an issue unless you are watching the repo.

1. Open your repo
2. Click **Watch** at the top right
3. Choose **Custom**
4. Tick **Issues** only, then **Apply**

**Untick "Releases" and "Discussions"** while you are there — you only want
issues, and you do not want a daily build notification.

Now GitHub will email you when the watcher posts something.

---

## Optional 3 - get it in your own inbox instead

Only if you want the alert as a proper email from your own address rather than
a GitHub notification. Most people do not bother.

If you do, you need two things typed into GitHub:

1. Open **github.com/sakariyeyusuf008-hash/wa-apple-health-pdl-watch/settings/secrets/actions**
2. Click **New repository secret**
3. Type this in the first box:

   ```
   PDL_SMTP_USER
   ```

4. Type `yusufsakariye0@gmail.com` in the second box
5. Click **Add secret**
6. Click **New repository secret** again
7. Type this in the first box:

   ```
   PDL_SMTP_PASS
   ```

8. Type your 16-character Google app password in the second box — the one that
   looks like `abcd efgh ijkl mnop`, with the spaces removed
9. Click **Add secret**

Two boxes, twice. That is all — the sender and recipient both default to your
Google address, so you do not need to set those separately.

**Where the app password comes from:** https://myaccount.google.com/apppasswords
You need 2-Step Verification turned on first.

---

## What happens if something goes wrong

**You never get an email.** Almost always you did not tick Issues in
Optional 2. Go and check.

**The Actions page shows a red cross.** Click the run to see what went wrong.
The most common cause is the download timing out, which is not serious — wait
for tomorrow and try again.

**The job seems to have stopped.** GitHub pauses scheduled jobs on repos that
sit idle. You get an email about it. One click re-enables it.

**You want to check right now, not tomorrow.** Actions tab, then Run workflow.
It takes 3 minutes because the file it downloads is 12.5 MB.
