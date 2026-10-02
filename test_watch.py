"""Offline tests for pdl_watch - no network, no 13MB downloads."""
import copy
import json
import os
import sys

sys.path.insert(0, r"C:\Users\yusuf\OneDrive\Documents\WA-PDL-Watcher")
import pdl_watch as W

BASE = {
    "effective": "Effective September 26, 2026 - September 30, 2026",
    "drugs": {
        "00548835101": {"NDC": "00548835101", "LABEL NAME": "BAQSIMI", "STRENGTH": "3 MG",
                        "DOSE FORM": "SPRAY", "PHARMACY PREFERRED STATUS": "P",
                        "NUMBER OF PREFERRED": "", "PHARMACY PA STATUS": "Y",
                        "NON CLINICAL TYPE": "RAFORM", "PA POLICY NUMBER": "",
                        "AHPDL INCLUSION": "Y", "MCO CARVE OUT": "N", "COVERAGE TYPE": "CP"},
        "00378806532": {"NDC": "00378806532", "LABEL NAME": "GLUCAGON EMERGENCY KIT",
                        "STRENGTH": "1 MG", "DOSE FORM": "VIAL",
                        "PHARMACY PREFERRED STATUS": "P", "NUMBER OF PREFERRED": "",
                        "PHARMACY PA STATUS": "N", "NON CLINICAL TYPE": "",
                        "PA POLICY NUMBER": "", "AHPDL INCLUSION": "Y",
                        "MCO CARVE OUT": "N", "COVERAGE TYPE": "CP"},
    },
}

passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}\n        got:  {got}\n        want: {want}")


def mutate(**ndc_fields):
    s = copy.deepcopy(BASE)
    d = s["drugs"]["00548835101"]
    d.update(ndc_fields)
    return s


print("\n1. no change -> no diffs")
check("identical states", W.diff(BASE, copy.deepcopy(BASE)), [])

print("\n2. the Oct 1 Baqsimi change is detected")
ch = W.diff(BASE, mutate(**{"PHARMACY PA STATUS": "N", "NON CLINICAL TYPE": ""}))
check("2 changes found", len(ch), 2)
check("PA flip", ("CHANGED", "00548835101", "BAQSIMI",
                  "PHARMACY PA STATUS", "Y", "N") in ch, True)
check("RAFORM cleared", ("CHANGED", "00548835101", "BAQSIMI",
                         "NON CLINICAL TYPE", "RAFORM", "(blank)") in ch, True)
check("change carries the label name", ch[0][2], "BAQSIMI")
check("change carries the field name", ch[0][3], "PHARMACY PA STATUS")

print("\n3. blank -> value is a real change, not ignored")
ch = W.diff(BASE, mutate(**{"NUMBER OF PREFERRED": "2"}))
check("step added", ("CHANGED", "00548835101", "BAQSIMI",
                     "NUMBER OF PREFERRED", "(blank)", "2") in ch, True)

print("\n4. value -> blank is a real change")
ch = W.diff(BASE, mutate(**{"NON CLINICAL TYPE": ""}))
check("type removed", ("CHANGED", "00548835101", "BAQSIMI",
                       "NON CLINICAL TYPE", "RAFORM", "(blank)") in ch, True)

print("\n5. effective date alone does NOT trigger an alert")
# (this is why diff() only looks at drug rows, not the header)
s = copy.deepcopy(BASE)
s["effective"] = "Effective October 1, 2026"
check("date-only change is silent", W.diff(BASE, s), [])

print("\n6. new NDC entering the class is flagged")
s = copy.deepcopy(BASE)
s["drugs"]["99999999999"] = {"NDC": "99999999999", "LABEL NAME": "NEWCO NASAL",
                            "STRENGTH": "3 MG", "DOSE FORM": "SPRAY",
                            "PHARMACY PREFERRED STATUS": "N", "NUMBER OF PREFERRED": "",
                            "PHARMACY PA STATUS": "Y", "NON CLINICAL TYPE": "RAFORM",
                            "PA POLICY NUMBER": "", "AHPDL INCLUSION": "Y",
                            "MCO CARVE OUT": "N", "COVERAGE TYPE": "CP"}
ch = W.diff(BASE, s)
check("addition detected", ch[0][0], "ADDED")
check("added ndc", ch[0][1], "99999999999")
check("added row carries its label", ch[0][2], "NEWCO NASAL")
check("added row has no before value", ch[0][4], "")
check("added row has no after value", ch[0][5], "")

print("\n7. a NDC leaving the class is flagged")
s = copy.deepcopy(BASE)
del s["drugs"]["00378806532"]
ch = W.diff(BASE, s)
check("removal detected", [c[0] for c in ch], ["REMOVED"])
check("removed row carries its label", ch[0][2], "GLUCAGON EMERGENCY KIT")
check("removed row has no after value", ch[0][5], "")

print("\n7b. the alert filter keeps Baqsimi and the generic, drops Zegalogue")
os.environ.pop("PDL_ALERT_SCOPE", None)
mixed = [
    ("CHANGED", "00548835101", "BAQSIMI", "PHARMACY PA STATUS", "Y", "N"),
    ("CHANGED", "00378806532", "GLUCAGON EMERGENCY KIT", "NUMBER OF PREFERRED", "(blank)", "2"),
    ("CHANGED", "72065012011", "GVOKE HYPOPEN 1-PACK", "PHARMACY PA STATUS", "N", "Y"),
    ("CHANGED", "00169191201", "ZEGALOGUE AUTOINJECTOR", "PHARMACY PA STATUS", "Y", "N"),
    ("ADDED", "99999999999", "NEWCO NASAL", "", "", ""),
]
labels = [c[2] for c in W.relevant(mixed)]
check("Baqsimi kept", "BAQSIMI" in labels, True)
check("generic kept", "GLUCAGON EMERGENCY KIT" in labels, True)
check("Gvoke kept", "GVOKE HYPOPEN 1-PACK" in labels, True)
check("Zegalogue dropped", "ZEGALOGUE AUTOINJECTOR" in labels, False)
check("new entrant always kept", "NEWCO NASAL" in labels, True)
check("4 of 5 kept", len(labels), 4)

print("\n7c. a Zegalogue-only change produces no notification at all")
zegalogue_only = [c for c in mixed if "ZEGALOGUE" in c[2]]
check("nothing survives the filter", W.relevant(zegalogue_only), [])

print("\n7d. PDL_ALERT_SCOPE=all overrides the filter")
os.environ["PDL_ALERT_SCOPE"] = "all"
check("scope() is None for 'all'", W.scope(), None)
check("everything kept", len(W.relevant(zegalogue_only)), 1)
os.environ.pop("PDL_ALERT_SCOPE", None)

print("\n7e. PDL_ALERT_SCOPE can narrow, but never silences a product entering the class")
os.environ["PDL_ALERT_SCOPE"] = "BAQSIMI"
narrowed = [c[2] for c in W.relevant(mixed)]
check("Baqsimi kept", "BAQSIMI" in narrowed, True)
check("generic dropped", "GLUCAGON EMERGENCY KIT" in narrowed, False)
check("Gvoke dropped", "GVOKE HYPOPEN 1-PACK" in narrowed, False)
check("a new entrant is still reported", "NEWCO NASAL" in narrowed, True)
os.environ.pop("PDL_ALERT_SCOPE", None)

print("\n8. the DILUENT rows are excluded from tracking")
d = W.DRUG_RE
check("diluent would match regex", bool(d.search("DILUENT FOR GLUCAGON EMERG KIT")), True)
check("but parse() skips it by label prefix", "DILUENT FOR GLUCAGON EMERG KIT".upper().startswith("DILUENT"), True)

print("\n9. snapshot round-trips through JSON unchanged")
s = mutate(**{"PHARMACY PA STATUS": "N"})
check("fingerprint stable", W.fingerprint(s), W.fingerprint(json.loads(json.dumps(s))))

print("\n9b. identical changes across many NDCs collapse into one line each")
# This is the real October 1 shape: one step change repeated over 10 generic NDCs.
generic = {}
for i, ndc in enumerate(["00378806532", "00378806790", "00548585000", "00548590500",
                         "69097002750", "69097002832", "70748030901", "70748031101",
                         "63323058282", "63323058313"]):
    generic[ndc] = {"NDC": ndc,
                    "LABEL NAME": "GLUCAGON EMERGENCY KIT" if i < 8 else "GLUCAGON HCL",
                    "STRENGTH": "1 MG", "DOSE FORM": "VIAL",
                    "PHARMACY PREFERRED STATUS": "P", "NUMBER OF PREFERRED": "",
                    "PHARMACY PA STATUS": "N", "NON CLINICAL TYPE": "",
                    "PA POLICY NUMBER": "", "AHPDL INCLUSION": "Y",
                    "MCO CARVE OUT": "N", "COVERAGE TYPE": "CP"}
after = copy.deepcopy(generic)
for d in after.values():
    d["NUMBER OF PREFERRED"] = "2"
    d["PHARMACY PREFERRED STATUS"] = "N"

changes = W.diff({"drugs": generic}, {"drugs": after})
check("20 field changes found", len(changes), 20)
out = W.format_changes(changes)
check("2 products in the output", out.count("~ GLUCAGON"), 2)
check("each product lists its NDCs exactly once",
      out.count("NDCs (8):") + out.count("NDCs (2):"), 2)
check("long NDC lists are truncated with an accurate count",
      "NDCs (8): 00378806532, 00378806790, 00548585000 +5 more" in out, True)
check("short NDC lists are shown in full",
      "NDCs (2): 63323058282, 63323058313" in out, True)
check("20 field changes render as 8 lines", len(out.splitlines()), 8)
check("no per-NDC duplication of the same field change",
      out.count("NUMBER OF PREFERRED:") + out.count("PHARMACY PREFERRED STATUS:"), 4)

print("\n9c. a field change affecting only SOME of a product's NDCs says so")
# Needs two fields on the same product: one hitting every NDC, one hitting a
# subset. Then the subset is worth labelling, because the reader would
# otherwise assume it applies to the whole product.
base = copy.deepcopy(after)
nxt = copy.deepcopy(base)
for d in nxt.values():
    d["PA POLICY NUMBER"] = "9999"                     # all 8 NDCs
for ndc in ("00378806532", "00378806790"):
    nxt[ndc] = copy.deepcopy(nxt[ndc])
    nxt[ndc]["NUMBER OF PREFERRED"] = "3"             # only 2 of them
out2 = W.format_changes(W.diff({"drugs": base}, {"drugs": nxt}))
check("all-NDC change carries no count label",
      "PA POLICY NUMBER: (blank)  ->  9999\n" in out2, True)
check("subset change is labelled with how many NDCs it covers",
      "NUMBER OF PREFERRED: 2  ->  3  [2 NDC(s)]" in out2, True)

print("\n10. link discovery finds both files and never picks a dated archive as live")
anchors = [
    ("/assets/billers-and-providers/apple-health-preferred-drug-list.xlsx", "View the Apple Health PDL"),
    ("/assets/billers-and-providers/apple-health-pdl-20260912.xlsx", "Apple Health PDL 9/12/2026 - 9/18/2026"),
    ("/assets/billers-and-providers/apple-health-pdl-20260829.xlsx", "Apple Health PDL 8/29/2026 - 9/4/2026"),
    ("/assets/billers-and-providers/apple-health-pdl-pr-20261001.xlsx", "Apple Health PDL pre-release - Effective October 1, 2026"),
]
import re as _re
cur = pre = None
dated = []
for href, text in anchors:
    if "pre-release" in text.lower() or "-pr-" in href.lower():
        pre = href
    elif _re.search(r"\d{1,2}/\d{1,2}/\d{4}", text):
        dated.append(text)
    elif "preferred-drug-list" in href.lower() and cur is None:
        cur = href
check("live link", cur, "/assets/billers-and-providers/apple-health-preferred-drug-list.xlsx")
check("pre-release link", pre, "/assets/billers-and-providers/apple-health-pdl-pr-20261001.xlsx")
check("2 dated archives recognised, not treated as live", len(dated), 2)

print("\n11. setting() prefers a real env var, and treats empty as absent")
os.environ["PDL_TEST_PROBE"] = "from-env"
check("env var wins", W.setting("PDL_TEST_PROBE"), "from-env")
os.environ["PDL_TEST_PROBE"] = ""
check("empty env var is treated as absent, not returned",
      W.setting("PDL_TEST_PROBE", "fallback"), "fallback")
os.environ.pop("PDL_TEST_PROBE", None)
check("missing returns the default", W.setting("PDL_TEST_PROBE", "fallback"), "fallback")
check("missing with no default returns None", W.setting("PDL_NO_SUCH_VAR"), None)

print("\n12. setting() falls back to the Windows user environment block")
if os.name == "nt":
    import winreg
    probe = "PDL_WATCH_TEST_PROBE"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
        winreg.SetValueEx(k, probe, 0, winreg.REG_SZ, "from-registry")
    try:
        os.environ.pop(probe, None)          # simulate a process started before setup
        check("found in HKCU\\Environment even with an empty process env",
              W.setting(probe), "from-registry")
        os.environ[probe] = "from-env"
        check("a real env var still takes precedence",
              W.setting(probe), "from-env")
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, probe)
        os.environ.pop(probe, None)
    check("probe cleaned up from the registry",
          W.setting(probe), None)
else:
    print("  SKIP  not on Windows")

print(f"\n{'=' * 60}\n  {passed} passed, {failed} failed\n{'=' * 60}")
sys.exit(1 if failed else 0)
