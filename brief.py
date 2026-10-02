"""Turn a field-level PDL diff into something a human can read and forward.

pdl_watch.py knows *what* changed. This module knows *what it means*, and
renders it two ways from one shared interpretation:

  build_text()  bullets and a narrow fixed-width table, for clients that show
                plain text, and for terminals
  build_html()  a real <table>, for mail clients - this is what most people
                will actually read

Both are sent as multipart/alternative, so the same alert works either way.
Keeping one model and two renderers means the two can never disagree about
what the change was or how good it is.

Judgements are labelled as judgements. Nothing here is inferred silently.
"""

import html
import textwrap

BAQSIMI = "BAQSIMI"
W = 78

SHORT = {
    "PHARMACY PREFERRED STATUS": {"P": "preferred", "N": "non-pref", "X": "-"},
    "PHARMACY PA STATUS": {"Y": "PA REQUIRED", "N": "no PA", "C": "PA per policy"},
    "NUMBER OF PREFERRED": {"": "no step", "1": "1-step", "2": "2-step",
                            "3": "3-step", "4": "4-step"},
    "NON CLINICAL TYPE": {"": "none", "RAFORM": "route flag",
                          "MEDNEC": "med necessity", "PRFGEN": "generic pref",
                          "PRFBRN": "brand pref", "NOTYPE": "has policy"},
}
FLAG_WORDS = {"RAFORM": "route of administration", "MEDNEC": "medical necessity"}


def rule(ch="-", width=W):
    return ch * width


# --------------------------------------------------------------------------
# field -> plain English
# --------------------------------------------------------------------------

def plain(field, value):
    v = (value or "").strip()
    if field == "PHARMACY PREFERRED STATUS":
        return {"P": "preferred", "N": "not preferred", "X": "n/a"}.get(v, v or "not listed")
    if field == "NUMBER OF PREFERRED":
        if not v:
            return "no step therapy"
        if v == "1":
            return "1 preferred product first"
        return f"{v} preferred products first"
    if field == "PHARMACY PA STATUS":
        return {"Y": "prior auth required", "N": "no prior auth",
                "C": "prior auth per policy"}.get(v, v or "not listed")
    if field == "NON CLINICAL TYPE":
        return {
            "": "no extra flag",
            "RAFORM": "justify the route of administration",
            "MEDNEC": "documented medical necessity",
            "PRFGEN": "generic-preference justification",
            "PRFBRN": "brand-preference justification",
            "NOTYPE": "has a clinical policy",
        }.get(v, v)
    if field == "COVERAGE TYPE":
        return {"CP": "pharmacy benefit", "CM": "medical benefit",
                "CA": "pharmacy and medical", "NC": "not covered"}.get(v, v)
    if field == "MCO CARVE OUT":
        return {"N": "managed care", "Y": "fee for service"}.get(v, v)
    if field == "AHPDL INCLUSION":
        return {"Y": "on the state list", "N": "not on the state list"}.get(v, v)
    return v or "not set"


def short(field, value):
    """A very short label, for table cells that must stay narrow."""
    v = (value or "").strip()
    return SHORT.get(field, {}).get(v, v or "-")


def flag_words(value):
    v = (value or "").strip()
    return FLAG_WORDS.get(v, v)


def cells(rec):
    """The three facts that decide whether a patient gets the drug, short form."""
    return {
        "preferred": short("PHARMACY PREFERRED STATUS", rec.get("PHARMACY PREFERRED STATUS")),
        "pa": short("PHARMACY PA STATUS", rec.get("PHARMACY PA STATUS")),
        "flag": short("NON CLINICAL TYPE", rec.get("NON CLINICAL TYPE")),
        "step": short("NUMBER OF PREFERRED", rec.get("NUMBER OF PREFERRED")),
    }


PA_LABEL = {"PA REQUIRED": "PA required", "no PA": "no PA",
            "PA per policy": "PA per policy", "-": "-"}


def summary(rec):
    """One-line status, for a table cell or a bullet."""
    c = cells(rec)
    bits = [c["preferred"], PA_LABEL.get(c["pa"], c["pa"])]
    if c["step"] not in ("-", "no step"):
        bits.append(c["step"])
    if c["flag"] not in ("-", "none"):
        bits.append(c["flag"])
    return ", ".join(bits)


# --------------------------------------------------------------------------
# who is this product
# --------------------------------------------------------------------------

def classify(label):
    u = label.upper()
    if BAQSIMI in u:
        return "baqsimi"
    if "GVOKE" in u:
        return "brand_rival"
    if "ZEGALOGUE" in u:
        return "discontinued_rival"
    if "GLUCAGON" in u or "DASIGLUCAGON" in u:
        return "generic"
    return "other"


# --------------------------------------------------------------------------
# does it help or hurt Baqsimi?  (explicit rules, stated out loud)
# --------------------------------------------------------------------------

def score_change(kind, cat, field, before, after):
    """+1 helps Baqsimi, -1 hurts, 0 neutral, None = needs a human.

    The rule throughout: anything that makes Baqsimi easier or a competitor
    harder is good. Baqsimi is the one product whose direction is inverted.
    """
    if kind in ("ADDED", "REMOVED"):
        return None
    f, b, a = field, (before or "").strip(), (after or "").strip()
    if b == a:
        return 0

    def step(v):
        return int(v) if v.isdigit() else 0

    if f == "PHARMACY PA STATUS":
        pa_removed = (b == "Y" and a == "N")
        pa_added = (b == "N" and a == "Y")
        if not (pa_removed or pa_added):
            return 0
        # Losing a PA makes a product easier to get. That helps Baqsimi when it
        # is Baqsimi losing it, and hurts Baqsimi when anyone else loses it,
        # because the cheap unrestricted option is available again.
        if cat == "baqsimi":
            return 1 if pa_removed else -1
        return -1 if pa_removed else 1

    if f == "PHARMACY PREFERRED STATUS":
        lost = (b == "P" and a == "N")
        gained = (b == "N" and a == "P")
        if not (lost or gained):
            return 0
        # Same inversion: Baqsimi losing preferred status hurts Baqsimi, while
        # a competitor losing it helps.
        if cat == "baqsimi":
            return 1 if gained else -1
        return 1 if lost else -1

    if f == "NUMBER OF PREFERRED":
        delta = step(a) - step(b)
        if delta == 0:
            return 0
        return -delta if cat == "baqsimi" else delta

    if f == "NON CLINICAL TYPE":
        if b and not a:                       # flag cleared
            return 1 if cat == "baqsimi" else 0
        if a and not b:                       # flag imposed
            return -1 if cat == "baqsimi" else 0
        return 0
    return 0


VERDICT = {
    "FAVOURABLE": ("GOOD", "Favourable to Baqsimi"),
    "UNFAVOURABLE": ("BAD", "Unfavourable to Baqsimi"),
    "NEUTRAL": ("NEUTRAL", "No commercial effect"),
    "REVIEW": ("REVIEW", "Needs a human decision"),
}
BADGE = {"FAVOURABLE": "good", "UNFAVOURABLE": "bad",
         "NEUTRAL": "neutral", "REVIEW": "review"}


def verdict_for(changes):
    """Roll changes up into FAVOURABLE / UNFAVOURABLE / NEUTRAL / REVIEW.

    Takes only the changes: kind and product label are read off them, so a
    caller cannot score Baqsimi's PA against Gvoke's label by mistake.
    """
    total, needs_review = 0, False
    for c in changes:
        s = score_change(c[0], classify(c[2]), c[3], c[4], c[5])
        if s is None:
            needs_review = True
        else:
            total += s
    if needs_review:
        return "REVIEW"
    if total > 0:
        return "FAVOURABLE"
    if total < 0:
        return "UNFAVOURABLE"
    return "NEUTRAL"


# --------------------------------------------------------------------------
# the shared model, built once
# --------------------------------------------------------------------------

def _rows(rec):
    return [d for d in rec.get("drugs", {}).values()]


def _label_rows(rec, label):
    return [d for d in rec.get("drugs", {}).values() if d["LABEL NAME"] == label]


def baqsimi_headline(old, new):
    baq_o = [d for d in _rows(old) if BAQSIMI in d["LABEL NAME"].upper()]
    baq_n = [d for d in _rows(new) if BAQSIMI in d["LABEL NAME"].upper()]
    if not baq_o and not baq_n:
        return "Baqsimi is not listed in this drug class."
    if baq_o and not baq_n:
        return "Baqsimi has been REMOVED from the list."
    if not baq_o and baq_n:
        return "Baqsimi has been ADDED to the list."

    o, n = baq_o[0], baq_n[0]
    out = []
    if o.get("PHARMACY PA STATUS") == "Y" and n.get("PHARMACY PA STATUS") == "N":
        out.append("Baqsimi no longer requires prior authorisation.")
    elif o.get("PHARMACY PA STATUS") == "N" and n.get("PHARMACY PA STATUS") == "Y":
        out.append("Baqsimi now REQUIRES prior authorisation.")
    if o.get("NON CLINICAL TYPE") and not n.get("NON CLINICAL TYPE"):
        out.append(f'The "justify the {flag_words(o["NON CLINICAL TYPE"])}" '
                   "flag has been cleared.")
    elif not o.get("NON CLINICAL TYPE") and n.get("NON CLINICAL TYPE"):
        out.append(f'Baqsimi now carries a "{flag_words(n["NON CLINICAL TYPE"])}" flag.')
    if o.get("PHARMACY PREFERRED STATUS") == "P" and n.get("PHARMACY PREFERRED STATUS") == "N":
        out.append("Baqsimi has lost preferred status.")
    os_, ns_ = (o.get("NUMBER OF PREFERRED") or ""), (n.get("NUMBER OF PREFERRED") or "")
    if not os_ and ns_:
        out.append(f"Baqsimi now needs {plain('NUMBER OF PREFERRED', ns_)}.")
    if not out:
        out.append("Baqsimi's listing has not materially changed.")
    return " ".join(out)


def _bullets(old, new, changes):
    """The key facts, as short bullets."""
    out = []
    baq_o = [d for d in _rows(old) if BAQSIMI in d["LABEL NAME"].upper()]
    baq_n = [d for d in _rows(new) if BAQSIMI in d["LABEL NAME"].upper()]
    if baq_o and baq_n:
        o, n = baq_o[0], baq_n[0]
        for field, name in (("PHARMACY PA STATUS", "Prior authorisation"),
                            ("PHARMACY PREFERRED STATUS", "Preferred status"),
                            ("NUMBER OF PREFERRED", "Step therapy"),
                            ("NON CLINICAL TYPE", "Extra flag")):
            b, a = o.get(field, ""), n.get(field, "")
            if b == a:
                continue
            if field == "NON CLINICAL TYPE":
                out.append((name, f"{flag_words(b) or 'none'} -> {flag_words(a) or 'none'}",
                            verdict_for([("CHANGED", "1", BAQSIMI, field, b, a)])))
            else:
                out.append((name, f"{plain(field, b)} -> {plain(field, a)}",
                            verdict_for([("CHANGED", "1", BAQSIMI, field, b, a)])))
    return out


def _why(old, new, changes):
    paras = []
    baq_o = [d for d in _rows(old) if BAQSIMI in d["LABEL NAME"].upper()]
    baq_n = [d for d in _rows(new) if BAQSIMI in d["LABEL NAME"].upper()]
    if baq_o and baq_n and baq_o[0].get("PHARMACY PA STATUS") == "Y" \
            and baq_n[0].get("PHARMACY PA STATUS") == "N":
        paras.append(
            "Until now, Baqsimi was the only rescue glucagon in Washington that "
            "required prior authorisation. Gvoke and the generic were both "
            "preferred with no prior auth, so every PA on Baqsimi was a "
            "Baqsimi-specific restriction, not a rule about the drug class. From "
            "this date no rescue glucagon requires prior auth."
        )
    if baq_o and baq_n and baq_o[0].get("NON CLINICAL TYPE") == "RAFORM" \
            and not baq_n[0].get("NON CLINICAL TYPE"):
        paras.append(
            "The restriction on Baqsimi was a route-of-administration "
            "justification. It applied only to the nasal spray, and HCA never "
            "published a policy saying what would satisfy it, so a prescriber had "
            "no criteria to submit against. That is now cleared."
        )
    for label in sorted({c[2] for c in changes}):
        cat = classify(label)
        if cat == "baqsimi":
            continue
        cl = [c for c in changes if c[2] == label]
        if cat == "generic" and any(c[3] == "NUMBER OF PREFERRED"
                                    and not c[4].strip() and c[5].strip() for c in cl):
            n = [c[5] for c in cl if c[3] == "NUMBER OF PREFERRED" and c[5].strip()][0]
            paras.append(
                f"The generic rescue glucagon has moved behind {n} preferred "
                "products. A prescription for generic glucagon now has to fail on "
                "preferred options before it will cover, which shifts volume "
                "toward Baqsimi and Gvoke."
            )
        elif cat == "brand_rival":
            paras.append("Gvoke's listing has changed. It is the product Baqsimi "
                         "competes with most directly on access.")
    return paras or ["No change affects access to rescue glucagon."]


def _forwardable(old, new, changes):
    bits = []
    h = baqsimi_headline(old, new)
    bits.append(h if "not materially changed" not in h
                else "The rescue glucagon listings did not change in a way that "
                     "affects Baqsimi.")
    generic_step = [c for c in changes if classify(c[2]) == "generic"
                    and c[3] == "NUMBER OF PREFERRED" and c[5].strip()]
    if generic_step:
        bits.append(f"Separately, the generic glucagon is now non-preferred with "
                    f"{generic_step[0][5]} preferred products required first.")
    baq = [c for c in changes if classify(c[2]) == "baqsimi"]
    if baq:
        bits.append(f"Net effect on Baqsimi: {verdict_for(baq).lower()}.")
    bits.append(f"Source: Washington HCA Apple Health PDL, {new.get('effective','?')}.")
    bits.append("This is the benefit design; a live fill still needs confirming.")
    return " ".join(bits)


CAVEAT = ("This is the state benefit design. Managed care plans must use the "
          "state's criteria but can add their own utilisation management on top, "
          "and nothing here proves the claims system or a pharmacy has stopped "
          "rejecting. Confirm with a live fill before treating it as done.")


def model(old, new, changes, raw_renderer):
    """One interpretation, used by both renderers."""
    by_label = {}
    for c in changes:
        by_label.setdefault(c[2], []).append(c)

    products = []
    baq = [d for d in _rows(new) if BAQSIMI in d["LABEL NAME"].upper()]
    baq_old = [d for d in _rows(old) if BAQSIMI in d["LABEL NAME"].upper()]
    baq_ch = [c for c in changes if classify(c[2]) == "baqsimi"]

    for label, cl in by_label.items():
        cat = classify(label)
        kind = cl[0][0]
        ndcs = sorted({c[1] for c in cl})
        old_rows = _label_rows(old, label)
        new_rows = _label_rows(new, label)
        products.append({
            "label": label,
            "cat": cat,
            "kind": kind,
            "ndcs": ndcs,
            "before": summary(old_rows[0]) if old_rows else "not listed",
            "after": summary(new_rows[0]) if new_rows else "removed",
            "verdict": verdict_for(cl),
            "is_baqsimi": cat == "baqsimi",
        })

    products.sort(key=lambda p: (not p["is_baqsimi"], p["label"]))

    baq_product = next((p for p in products if p["is_baqsimi"]), None)
    baq_verdict = verdict_for(baq_ch) if baq_ch else None

    return {
        "effective": new.get("effective", "?"),
        "headline": baqsimi_headline(old, new),
        "bullets": _bullets(old, new, changes),
        "baq_before": summary(baq_old[0]) if baq_old else "not listed",
        "baq_after": summary(baq[0]) if baq else "not listed",
        "baq_verdict": baq_verdict,
        "products": products,
        "why": _why(old, new, changes),
        "forwardable": _forwardable(old, new, changes),
        "caveat": CAVEAT,
        "raw": raw_renderer(changes),
        "n_baq_ndcs": len(baq),
    }


# --------------------------------------------------------------------------
# renderer 1: plain text - bullets and a narrow table
# --------------------------------------------------------------------------

def _pad(s, n):
    s = (s or "")[:n]
    return s.ljust(n)


def _text_before_after(products):
    """Bullets, not a fixed-width table.

    A table wide enough to hold these cells does not survive an 80-column
    terminal, a phone, or Gmail's plain-text pane - it truncates mid-word,
    which is worse than having no table at all. The HTML part is where the
    real table lives. Here, keep it readable at any width.
    """
    out = []
    for p in products:
        name = p["label"].title()
        if len(p["ndcs"]) > 1:
            name += f" ({len(p['ndcs'])} NDCs)"
        if p["kind"] == "ADDED":
            name = "NEW - " + name
        elif p["kind"] == "REMOVED":
            name = "REMOVED - " + name

        vtxt = VERDICT[p["verdict"]][1]
        head = f"  * {name}"
        if len(head) + len(vtxt) + 3 <= W:
            out.append(f"{head} - {vtxt}")
        else:
            out.append(head)
            out.append(f"      {vtxt}")

        if p["kind"] not in ("ADDED", "REMOVED"):
            out.append(f"      before: {p['before']}")
            out.append(f"      after:  {p['after']}")
    return out


def build_text(m):
    L = ["", "BAQSIMI - WASHINGTON APPLE HEALTH (MEDICAID) DRUG LIST",
         f"List effective: {m['effective']}", rule("="), ""]

    L.append(f"HEADLINE: {VERDICT[m['baq_verdict']][1]}" if m["baq_verdict"]
             else "HEADLINE: rescue glucagon class change")
    L.append("")
    for line in textwrap.wrap(m["headline"], W):
        L.append("  " + line)
    L.append("")

    if m["bullets"]:
        L.append("WHAT CHANGED, IN PLAIN TERMS")
        L.append("")
        for name, change, _ in m["bullets"]:
            L.append(f"  * {name}")
            L.append(f"      {change}")
        L.append("")

    if m["products"]:
        L.append("BEFORE / AFTER")
        L.append("")
        L.extend(_text_before_after(m["products"]))
        L.append("")

    L.append("WHY IT MATTERS")
    L.append("")
    for para in m["why"]:
        for line in textwrap.wrap(para, W - 2):
            L.append("  " + line)
        L.append("")

    L.append("ONE PARAGRAPH, FOR FORWARDING")
    L.append(rule())
    for line in textwrap.wrap(m["forwardable"], W):
        L.append(line)
    L.append(rule())
    L.append("")

    L.append("WHAT THIS DOES NOT PROVE")
    L.append("")
    for line in textwrap.wrap(m["caveat"], W - 2):
        L.append("  " + line)
    L.append("")

    L.append("FIELD-BY-FIELD DETAIL (also in ALERT.txt)")
    L.append(rule())
    L.append(m["raw"])
    L.append(rule())
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# renderer 2: html - a real table
# --------------------------------------------------------------------------

CSS = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;margin:0;padding:16px;background:#fff}
.wrap{max-width:760px}
h1{font-size:17px;margin:0 0 2px}
.sub{color:#666;font-size:12px;margin:0 0 16px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:#666;margin:22px 0 8px;border-bottom:1px solid #e5e5e5;padding-bottom:4px}
table{border-collapse:collapse;width:100%;margin:0 0 4px;font-size:13px}
th,td{border:1px solid #e0e0e0;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f6f6f6;font-weight:600;font-size:12px}
td.num{white-space:nowrap}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;font-weight:600;color:#fff}
.good{background:#1a7f37}.bad{background:#b42318}.neutral{background:#6b7280}.review{background:#9a6700}
.lead{background:#f6f6f6;border-left:4px solid #1a7f37;padding:11px 13px;margin:0 0 14px}
.lead.bad{border-left-color:#b42318}
.lead.neutral{border-left-color:#6b7280}
.lead.review{border-left-color:#9a6700}
.lead p{margin:0 0 6px}
.lead p:last-child{margin:0}
ul{margin:0;padding-left:20px}
li{margin:0 0 5px}
li b{display:inline-block;min-width:150px}
.quote{background:#fafafa;border:1px solid #eee;border-left:4px solid #bbb;padding:11px 13px;font-style:italic}
.note{color:#555;font-size:12px}
pre{background:#fafafa;border:1px solid #eee;padding:10px;font-size:11px;overflow-x:auto;white-space:pre;line-height:1.45}
.baq{background:#fffdf5}
"""


def _h(s):
    return html.escape(str(s or ""), quote=True)


def build_html(m):
    bv = m["baq_verdict"]
    badge = VERDICT[bv][1] if bv else VERDICT["NEUTRAL"][1]
    cls = BADGE[bv] if bv else "neutral"

    rows = []
    for p in m["products"]:
        name = _h(p["label"].title())
        if len(p["ndcs"]) > 1:
            name += f" <span class='note'>({len(p['ndcs'])} NDCs)</span>"
        elif p["kind"] in ("ADDED", "REMOVED"):
            name = ("+ " if p["kind"] == "ADDED" else "- ") + name
        vc = BADGE[p["verdict"]]
        rows.append(
            f"<tr{' class=\"baq\"' if p['is_baqsimi'] else ''}>"
            f"<td>{name}</td><td>{_h(p['before'])}</td><td>{_h(p['after'])}</td>"
            f"<td><span class='badge {vc}'>{_h(VERDICT[p['verdict']][0])}</span>"
            f"<div class='note'>{_h(VERDICT[p['verdict']][1])}</div></td></tr>")

    bullets = "".join(
        f"<li><b>{_h(name)}</b> {_h(change)}</li>" for name, change, _ in m["bullets"])

    why = "".join(f"<p>{_h(p)}</p>" for p in m["why"])

    return f"""<div style="font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a">
<div style="max-width:760px">
<style>{CSS}</style>

<h1>Baqsimi - Washington Apple Health (Medicaid) drug list</h1>
<p class="sub">List effective: {_h(m['effective'])}</p>

<div class="lead {cls}">
  <p><span class="badge {cls}">{_h(badge)}</span></p>
  <p>{_h(m['headline'])}</p>
</div>

<h2>What changed, in plain terms</h2>
<ul>{bullets}</ul>

<h2>Before / after</h2>
<table>
<tr><th style="width:30%">Product</th><th style="width:24%">Before</th>
<th style="width:20%">After</th><th style="width:26%">Effect on Baqsimi</th></tr>
{''.join(rows)}
</table>

<h2>Why it matters</h2>
{why}

<h2>One paragraph, for forwarding</h2>
<div class="quote">{_h(m['forwardable'])}</div>

<h2>What this does not prove</h2>
<p class="note">{_h(m['caveat'])}</p>

<h2>Field-by-field detail (also in ALERT.txt)</h2>
<pre>{_h(m['raw'])}</pre>

</div></div>"""


def build(old, new, changes, raw_renderer):
    """Convenience: returns the plain-text brief."""
    return build_text(model(old, new, changes, raw_renderer))
