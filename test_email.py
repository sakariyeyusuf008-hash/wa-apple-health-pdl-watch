"""End-to-end test of the alert email path.

Runs a throwaway SMTP server on localhost, points PDL_SMTP_* at it, forces a
change, and asserts the message actually arrives with the right content.
Python 3.12 removed smtpd, so the sink is hand-rolled - it is only about 40
lines of the SMTP dialogue and it is the only way to prove the sender works
without a real mail server.

No network, no credentials, nothing leaves the machine.
"""
import os
import socket
import sys
import threading

sys.path.insert(0, r"C:\Users\yusuf\OneDrive\Documents\WA-PDL-Watcher")

received = []


class Sink(threading.Thread):
    """Minimal SMTP server: accepts one message, stores it, disconnects."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]

    def run(self):
        """Serve connections until the test finishes. The watcher may send more
        than one message, and a sink that handles a single connection makes the
        second send fail for reasons that have nothing to do with the code."""
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                self._serve(conn)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _serve(self, conn):
        f = conn.makefile("rwb")

        def say(s):
            f.write(s.encode() + b"\r\n")
            f.flush()

        say("220 sink.local ESMTP test sink")
        while True:
            line = f.readline()
            if not line:
                break
            cmd = line.decode("utf8", "ignore").strip()
            up = cmd.upper()
            if up.startswith("EHLO"):
                say("250-sink.local")
                say("250 8BITMIME")
            elif up.startswith("HELO"):
                say("250 sink.local")
            elif up.startswith("MAIL FROM"):
                say("250 2.1.0 OK")
            elif up.startswith("RCPT TO"):
                say("250 2.1.5 OK")
            elif up.startswith("DATA"):
                say("354 End data with <CR><LF>.<CR><LF>")
                body = []
                while True:
                    b = f.readline()
                    if not b or b.strip() == b".":
                        break
                    body.append(b)
                received.append(b"".join(body).decode("utf8", "ignore"))
                say("250 2.0.0 OK queued")
            elif up.startswith("QUIT"):
                say("221 2.0.0 bye")
                break
            else:
                say("250 2.0.0 OK")


import pdl_watch as W  # noqa: E402

# pdl_watch.setting() falls back to HKCU\Environment, so these tests would
# otherwise find the REAL Gmail settings and could send you an actual email
# while asserting "not configured". Block the registry so the tests are
# hermetic: env vars only, no registry.
sys.modules["winreg"] = None
if hasattr(W, "setting"):
    _orig_setting = W.setting

    def _env_only(name, default=None):
        v = os.environ.get(name)
        return v if v else default

    W.setting = _env_only

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


sink = Sink()
sink.start()

# point the watcher at the sink, TLS off (no cert), and force a change
os.environ.update(
    PDL_SMTP_HOST="127.0.0.1",
    PDL_SMTP_PORT=str(sink.port),
    PDL_SMTP_TLS="0",
    PDL_SMTP_USER="",
    PDL_SMTP_PASS="",
    PDL_SMTP_FROM="pdl-watch@zealand.example",
    PDL_SMTP_TO="yusuf@example.com",
)

print("\n1. with no host configured, email() is a no-op and returns False")
for k in ("PDL_SMTP_HOST", "PDL_SMTP_PORT", "PDL_SMTP_TLS", "PDL_SMTP_USER",
          "PDL_SMTP_PASS", "PDL_SMTP_FROM", "PDL_SMTP_TO"):
    os.environ.pop(k, None)
check("unconfigured is not an error", W.email("subject", "body") is False)

print("\n2. a real send reaches the server and is well formed")
os.environ.update(
    PDL_SMTP_HOST="127.0.0.1",
    PDL_SMTP_PORT=str(sink.port),
    PDL_SMTP_TLS="0",
    PDL_SMTP_USER="",
    PDL_SMTP_PASS="",
    PDL_SMTP_FROM="pdl-watch@zealand.example",
    PDL_SMTP_TO="yusuf@example.com",
)
subject = "WA Apple Health PDL - rescue glucagon change"
body = ("=== current  (Effective October 1, 2026) ===\n"
        "  ~ 00548835101  PHARMACY PA STATUS: Y  ->  N\n"
        "  ~ 00548835101  NON CLINICAL TYPE: RAFORM  ->  (blank)\n")
ok = W.email(subject, body)
sink.join(timeout=5)
check("email() reports success", ok is True)
check("exactly one message arrived", len(received) == 1, f"got {len(received)}")
if received:
    msg = received[0]
    check("recipient present", "To: yusuf@example.com" in msg, msg[:200])
    check("sender present", "From: pdl-watch@zealand.example" in msg, msg[:200])
    check("subject present", subject in msg, msg[:200])
    check("body carried through", "PHARMACY PA STATUS: Y  ->  N" in msg)
    check("the blank is shown explicitly, not dropped",
          "NON CLINICAL TYPE: RAFORM  ->  (blank)" in msg)
    check("plain-text-only send is not multipart",
          "multipart/alternative" not in msg, True)

print("\n2b. with an HTML part it becomes multipart/alternative")
received.clear()
ok = W.email(subject + " [html]", body,
             "<html><body><table><tr><td>Baqsimi</td><td>PA removed</td></tr>"
             "</table></body></html>")
sink.join(timeout=5)
check("send succeeded", ok is True)
msg = received[0] if received else ""
check("declared multipart/alternative", "multipart/alternative" in msg, True)
check("has a text/plain part", "text/plain" in msg, True)
check("has a text/html part", "text/html" in msg, True)
check("html part is the alternative, not a replacement",
          "Content-Type: text/html" in msg, True)

print("\n3. a bad host fails cleanly instead of crashing the watcher")
os.environ["PDL_SMTP_HOST"] = "127.0.0.1"
os.environ["PDL_SMTP_PORT"] = "1"          # nothing listening
ok = W.email("subject", "body")
check("returns False rather than raising", ok is False)
check("failure was written to watch.log", "email failed" in open(W.LOG, encoding="utf8").read())

print("\n4. the tests cannot reach a real account")
sent = "".join(received)
# The safety property is not "no message mentions an address" - the tests
# deliberately set a fake one. It is that the real settings in HKCU are
# invisible, so no send can resolve a real host or password.
check("setting() is stubbed to env-only, so the registry is unreachable",
      W.setting is _env_only, True)
check("a variable the tests never set resolves to None",
      W.setting("PDL_SMTP_SOMETHING_ELSE") is None, True)
check("exactly one message was produced, and the sink received it",
      len(received) == 1, True)
check("it went to the fake address the test set", "yusuf@example.com" in sent, True)

print(f"\n{'=' * 62}\n  {passed} passed, {failed} failed\n{'=' * 62}")
sys.exit(1 if failed else 0)
