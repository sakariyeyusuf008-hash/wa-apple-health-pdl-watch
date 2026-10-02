"""Tests for brief.py - the layer that explains a change to a human.

The scoring is a commercial judgement about Baqsimi, so it is tested
explicitly in both directions. Getting it backwards would tell a rep the
opposite of the truth, which is worse than saying nothing.
"""
import os
import sys

sys.path.insert(0, r"C:\Users\yusuf\OneDrive\Documents\WA-PDL-Watcher")
import brief

passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}\n        got:  {got!r}\n        want: {want!r}")


def sc(cat, field, before, after):
    return brief.score_change("CHANGED", cat, field, before, after)


print("\n1. the headline cases, in both directions")

print("\n  Baqsimi losing a PA is GOOD NEWS")
check("Baqsimi PA removed", sc("baqsimi", "PHARMACY PA STATUS", "Y", "N"), 1)
check("Baqsimi PA imposed", sc("baqsimi", "PHARMACY PA STATUS", "N", "Y"), -1)
check("Baqsimi PA flag cleared", sc("baqsimi", "NON CLINICAL TYPE", "RAFORM", ""), 1)
check("Baqsimi flag imposed", sc("baqsimi", "NON CLINICAL TYPE", "", "RAFORM"), -1)
check("Baqsimi keeps preferred", sc("baqsimi", "PHARMACY PREFERRED STATUS", "P", "P"), 0)
check("Baqsimi loses preferred", sc("baqsimi", "PHARMACY PREFERRED STATUS", "P", "N"), -1)
check("Baqsimi gains preferred", sc("baqsimi", "PHARMACY PREFERRED STATUS", "N", "P"), 1)
check("Baqsimi gets a step", sc("baqsimi", "NUMBER OF PREFERRED", "", "2"), -2)
check("Baqsimi loses its step", sc("baqsimi", "NUMBER OF PREFERRED", "2", ""), 2)
check("Baqsimi step 2 to 3", sc("baqsimi", "NUMBER OF PREFERRED", "2", "3"), -1)

print("\n  a competitor getting harder is GOOD NEWS for Baqsimi")
check("generic PA imposed", sc("generic", "PHARMACY PA STATUS", "N", "Y"), 1)
check("generic PA removed", sc("generic", "PHARMACY PA STATUS", "Y", "N"), -1)
check("generic loses preferred", sc("generic", "PHARMACY PREFERRED STATUS", "P", "N"), 1)
check("generic gains preferred", sc("generic", "PHARMACY PREFERRED STATUS", "N", "P"), -1)
check("generic gets a step", sc("generic", "NUMBER OF PREFERRED", "", "2"), 2)
check("generic loses its step", sc("generic", "NUMBER OF PREFERRED", "2", ""), -2)
check("Gvoke PA imposed", sc("brand_rival", "PHARMACY PA STATUS", "N", "Y"), 1)
check("Gvoke loses preferred", sc("brand_rival", "PHARMACY PREFERRED STATUS", "P", "N"), 1)
check("competitor flag changes do not move the needle",
      sc("generic", "NON CLINICAL TYPE", "RAFORM", ""), 0)

print("\n  no-op and unknown changes")
check("identical values score zero", sc("baqsimi", "PHARMACY PA STATUS", "Y", "Y"), 0)
check("unrelated field scores zero", sc("baqsimi", "COVERAGE TYPE", "CP", "CA"), 0)
check("a product entering the class needs a human",
      brief.score_change("ADDED", "generic", "", "", ""), None)
check("a product leaving the class needs a human",
      brief.score_change("REMOVED", "brand_rival", "", "", ""), None)

print("\n2. verdicts roll up correctly")
check("the real October 1 Baqsimi change is FAVOURABLE",
      brief.verdict_for([("CHANGED", "1", "BAQSIMI", "PHARMACY PA STATUS", "Y", "N"),
                         ("CHANGED", "1", "BAQSIMI", "NON CLINICAL TYPE", "RAFORM", "")]),
      "FAVOURABLE")
check("a new PA on Baqsimi is UNFAVOURABLE",
      brief.verdict_for([("CHANGED", "1", "BAQSIMI", "PHARMACY PA STATUS", "N", "Y")]),
      "UNFAVOURABLE")
check("a step on a competitor is FAVOURABLE",
      brief.verdict_for([("CHANGED", "1", "GLUCAGON EMERGENCY KIT",
                          "NUMBER OF PREFERRED", "", "2")]),
      "FAVOURABLE")
check("a new entrant is REVIEW, never guessed",
      brief.verdict_for([("ADDED", "1", "NEWCO NASAL", "", "", "")]), "REVIEW")
check("changes that cancel out are NEUTRAL",
      brief.verdict_for([("CHANGED", "1", "BAQSIMI", "PHARMACY PA STATUS", "Y", "N"),
                         ("CHANGED", "1", "BAQSIMI", "NUMBER OF PREFERRED", "", "1")]),
      "NEUTRAL")
check("Baqsimi and Gvoke are never scored against each other's label",
      brief.verdict_for([("CHANGED", "1", "GVOKE HYPOPEN 1-PACK",
                          "PHARMACY PA STATUS", "N", "Y")]),
      "FAVOURABLE")
check("the real October 1 generic demotion is FAVOURABLE",
      brief.verdict_for([("CHANGED", "1", "GLUCAGON EMERGENCY KIT",
                          "PHARMACY PREFERRED STATUS", "P", "N"),
                         ("CHANGED", "1", "GLUCAGON EMERGENCY KIT",
                          "NUMBER OF PREFERRED", "", "2")]),
      "FAVOURABLE")

print("\n3. plain English beats field codes")
check("PA=Y", brief.plain("PHARMACY PA STATUS", "Y"), "prior auth required")
check("PA=N", brief.plain("PHARMACY PA STATUS", "N"), "no prior auth")
check("pref=P", brief.plain("PHARMACY PREFERRED STATUS", "P"), "preferred")
check("pref=N", brief.plain("PHARMACY PREFERRED STATUS", "N"), "not preferred")
check("no step", brief.plain("NUMBER OF PREFERRED", ""), "no step therapy")
check("step 2", brief.plain("NUMBER OF PREFERRED", "2"), "2 preferred products first")
check("RAFORM explained", brief.plain("NON CLINICAL TYPE", "RAFORM"),
      "justify the route of administration")
check("blank type", brief.plain("NON CLINICAL TYPE", ""), "no extra flag")
check("short PA=Y fits a table cell", brief.short("PHARMACY PA STATUS", "Y"), "PA REQUIRED")
check("short step fits a table cell", brief.short("NUMBER OF PREFERRED", "2"), "2-step")
check("short flag fits a table cell", brief.short("NON CLINICAL TYPE", "RAFORM"), "route flag")

print("\n4. product classification")
check("Baqsimi", brief.classify("BAQSIMI"), "baqsimi")
check("Gvoke", brief.classify("GVOKE HYPOPEN 1-PACK"), "brand_rival")
check("generic kit", brief.classify("GLUCAGON EMERGENCY KIT"), "generic")
check("generic hcl", brief.classify("GLUCAGON HCL"), "generic")
check("Zegalogue", brief.classify("ZEGALOGUE AUTOINJECTOR"), "discontinued_rival")

print("\n5. the headline says the right thing")
OLD = {"effective": "Effective September 26, 2026 - September 30, 2026", "drugs": {
    "00548835101": {"NDC": "00548835101", "LABEL NAME": "BAQSIMI", "DOSE FORM": "SPRAY",
                    "PHARMACY PREFERRED STATUS": "P", "NUMBER OF PREFERRED": "",
                    "PHARMACY PA STATUS": "Y", "NON CLINICAL TYPE": "RAFORM",
                    "PA POLICY NUMBER": "", "COVERAGE TYPE": "CP", "MCO CARVE OUT": "N",
                    "AHPDL INCLUSION": "Y"},
    "00378806532": {"NDC": "00378806532", "LABEL NAME": "GLUCAGON EMERGENCY KIT",
                    "DOSE FORM": "VIAL", "PHARMACY PREFERRED STATUS": "P",
                    "NUMBER OF PREFERRED": "", "PHARMACY PA STATUS": "N",
                    "NON CLINICAL TYPE": "", "PA POLICY NUMBER": "", "COVERAGE TYPE": "CP",
                    "MCO CARVE OUT": "N", "AHPDL INCLUSION": "Y"},
}}
import copy
NEW = copy.deepcopy(OLD)
NEW["effective"] = "Effective October 1, 2026"
NEW["drugs"]["00548835101"]["PHARMACY PA STATUS"] = "N"
NEW["drugs"]["00548835101"]["NON CLINICAL TYPE"] = ""
NEW["drugs"]["00378806532"]["PHARMACY PREFERRED STATUS"] = "N"
NEW["drugs"]["00378806532"]["NUMBER OF PREFERRED"] = "2"

h = brief.baqsimi_headline(OLD, NEW)
check("headline leads with the PA removal", "no longer requires prior authorisation" in h, True)
check("headline mentions the cleared flag", "flag has been cleared" in h, True)
check("headline does not say the wrong thing", "REQUIRES prior" in h, False)

out = brief.build_text(brief.model(OLD, NEW,
    [("CHANGED", "00548835101", "BAQSIMI", "PHARMACY PA STATUS", "Y", "N"),
     ("CHANGED", "00548835101", "BAQSIMI", "NON CLINICAL TYPE", "RAFORM", ""),
     ("CHANGED", "00378806532", "GLUCAGON EMERGENCY KIT",
      "PHARMACY PREFERRED STATUS", "P", "N"),
     ("CHANGED", "00378806532", "GLUCAGON EMERGENCY KIT",
      "NUMBER OF PREFERRED", "", "2")],
    lambda ch: "\n".join("  raw " + c[3] for c in ch)))

for section in ("HEADLINE", "WHAT CHANGED, IN PLAIN TERMS", "BEFORE / AFTER",
                "WHY IT MATTERS", "ONE PARAGRAPH, FOR FORWARDING",
                "WHAT THIS DOES NOT PROVE", "FIELD-BY-FIELD DETAIL"):
    check(f"has a {section} section", section in out, True)
check("states the verdict as favourable", "Favourable to Baqsimi" in out, True)
check("never claims unfavourable for a PA removal", "Unfavourable" in out, False)
check("keeps the raw field detail", "raw PHARMACY PA STATUS" in out, True)
check("includes the effective date", "Effective October 1, 2026" in out, True)
check("carries the live-fill caveat", "live fill" in out, True)
check("uses bullets for the plain-terms list", "\n  * " in out, True)
check("plain-text before/after is bullets, not a truncating table",
      "before: " in out and "after:  " in out, True)
check("a status is never cut off mid-word",
      "before: preferred, PA required, route flag" in out, True)
check("after status is complete too",
      "after:  preferred, no PA" in out, True)
check("competitor before/after are complete",
      "after:  non-pref, no PA, 2-step" in out, True)
check("the verdict sits on the same line as the product where it fits",
      "Baqsimi - Favourable to Baqsimi" in out, True)
check("nothing overflows 80 columns", max(len(l) for l in out.splitlines()) <= 80, True)
check("html carries the real table instead",
      "<table>" in brief.build_html(brief.model(OLD, NEW, [], lambda c: "")), True)
check("no line is absurdly long", max(len(l) for l in out.splitlines()) <= 92, True)

print("\n6. the html brief is a real table, and escapes its data")
h = brief.build_html(brief.model(OLD, NEW,
    [("CHANGED", "00548835101", "BAQSIMI", "PHARMACY PA STATUS", "Y", "N"),
     ("CHANGED", "00378806532", "GLUCAGON EMERGENCY KIT",
      "NUMBER OF PREFERRED", "", "2")],
    lambda ch: "\n".join("  raw " + c[3] for c in ch)))

check("html has a <table>", "<table>" in h, True)
check("html has a header row", "<th" in h, True)
check("html has one row per product", h.count("<tr") >= 3, True)
check("html uses a badge for the verdict", "badge good" in h, True)
check("html lists the plain-terms bullets", "<li>" in h, True)
check("html keeps the forwardable quote", "quote" in h, True)
check("html keeps the caveat", "live fill" in h, True)
check("no raw field codes leak into the headline area",
      "PHARMACY PA STATUS: Y" not in h.split("<h2>")[0], True)

print("\n7. html injection from spreadsheet data is escaped")
NASTY = {"effective": "<script>alert(1)</script>", "drugs": {
    "X1": {"NDC": "X1", "LABEL NAME": "<img src=x onerror=alert(1)>BAQSIMI",
           "DOSE FORM": "SPRAY", "STRENGTH": "3 MG",
           "PHARMACY PREFERRED STATUS": "P", "NUMBER OF PREFERRED": "",
           "PHARMACY PA STATUS": "Y", "NON CLINICAL TYPE": "RAFORM",
           "PA POLICY NUMBER": "", "COVERAGE TYPE": "CP",
           "MCO CARVE OUT": "N", "AHPDL INCLUSION": "Y"}}}
ch = [("CHANGED", "X1", "<img src=x onerror=alert(1)>BAQSIMI",
       "PHARMACY PA STATUS", "Y", "N")]
hh = brief.build_html(brief.model(NASTY, NASTY, ch, lambda c: "raw"))
check("script tag from the effective date is escaped", "<script>" not in hh, True)
check("img onerror from a product label is escaped",
      "<img src=x" not in hh.lower(), True)
check("the escaped form is present instead",
      "&lt;img" in hh.lower(), True)
check("the escaped label survives intact",
      "BAQSIMI" in hh or "Baqsimi" in hh, True)

print("\n8. an added product is never guessed at")
added = brief.model(OLD, NEW,
    [("ADDED", "99999999999", "NEWCO NASAL", "", "", "")],
    lambda ch: "raw")
check("verdict is REVIEW", added["products"][0]["verdict"], "REVIEW")
check("verdict text asks for a human", "human" in brief.VERDICT["REVIEW"][1], True)

print("\n9. an empty baseline is not mistaken for a brand new product")
EMPTY = {"effective": "?", "drugs": {}}
first = brief.baqsimi_headline(EMPTY, NEW)
check("headline does not claim Baqsimi was added",
      "ADDED to the list" in first, False)
check("headline says it is a first reading",
      "nothing to compare against" in first, True)
check("headline does not claim a PA change",
      "no longer requires" in first, False)

m9 = brief.model(EMPTY, NEW,
    [("ADDED", "00548835101", "BAQSIMI", "", "", "")], lambda c: "raw")
check("why-it-matters admits there is nothing to compare",
      "first reading" in m9["why"][0].lower(), True)
check("no false PA history is invented",
      "only rescue glucagon in Washington" not in " ".join(m9["why"]), True)

print("\n10. one paragraph per product, not per label")
many = [("CHANGED", f"7206501{i:04d}", f"GVOKE HYPOPEN {i}-PACK",
         "PHARMACY PA STATUS", "N", "Y") for i in range(1, 6)]
m10 = brief.model(OLD, NEW, many, lambda c: "raw")
g = [p for p in m10["why"] if "Gvoke's listing has changed" in p]
check("five Gvoke labels produce one paragraph", len(g), 1)
check("the count of affected forms is stated", "5 product forms" in g[0], True)
t = brief.build_text(m10)
check("the repeated sentence appears once in the rendered brief",
      t.count("Gvoke's listing has changed"), 1)

print("\n11. the generic paragraph is also stated once")
gen = [("CHANGED", f"003788065{i}", "GLUCAGON EMERGENCY KIT",
        "NUMBER OF PREFERRED", "", "2") for i in range(3)]
m11 = brief.model(OLD, NEW, gen, lambda c: "raw")
check("three generic labels produce one paragraph",
      len([p for p in m11["why"] if "generic rescue glucagon" in p]), 1)

print(f"\n{'=' * 62}\n  {passed} passed, {failed} failed\n{'=' * 62}")
sys.exit(1 if failed else 0)
