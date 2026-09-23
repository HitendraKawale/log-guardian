"""Offline structural validator for the fresh report-grounding case set.

Reads the delivered files as bytes rather than trusting build.py, so that a
hand edit to any artifact is caught before hashing. Standard library only; it
never calls a model, opens a socket, or reads outside this directory.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = "fresh-report-grounding-1"

CASE_FIELDS = ["schema_version", "dataset_version", "case_id", "provenance", "question", "scope", "logs"]
SCOPE_FIELDS = ["services", "start", "end"]
LOG_FIELDS = ["evidence_id", "service", "level", "message", "timestamp"]
LABEL_FIELDS = [
    "dataset_version", "case_id", "variant_id", "family", "expected_outcome",
    "expected_cause", "acceptable_alternatives", "supporting_evidence_ids",
    "forbidden_claims", "required_missing_evidence", "tags",
]
LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
EVIDENCE_RE = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")
LEAK_TOKENS = [
    "expected_outcome", "expected_cause", "acceptable_alternatives",
    "supporting_evidence_ids", "forbidden_claims", "required_missing_evidence",
    "variant_id", "attack_objective", "grader", "rubric", "ground_truth",
]
MAX_LOG_BYTES = 10 * 1024
MAX_QUESTION_CHARS = 2048
MAX_WINDOW_SECONDS = 3600

errors = []
checks = []


def check(ok, label, detail=""):
    checks.append((bool(ok), label, detail))
    if not ok:
        errors.append("{}{}".format(label, (": " + detail) if detail else ""))
    return bool(ok)


def no_dup_keys(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise ValueError("duplicate JSON key: {}".format(k))
        seen.add(k)
    return dict(pairs)


def load_jsonl(path):
    rows = []
    raw = path.read_bytes().decode("utf-8")
    for n, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise ValueError("{}: blank line {}".format(path.name, n))
        rows.append(json.loads(line, object_pairs_hook=no_dup_keys))
    return rows, raw


def aware(ts):
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("naive timestamp: {}".format(ts))
    return dt


def fields_exact(obj, expected, where):
    check(list(obj.keys()) == expected, "exact fields {}".format(where),
          "got {}".format(list(obj.keys())))


# ---------------------------------------------------------------- cases.jsonl
cases, cases_raw = load_jsonl(HERE / "cases.jsonl")
check(len(cases) == 12, "cases.jsonl has 12 rows", "got {}".format(len(cases)))

all_evidence = {}
by_case = {}
for case in cases:
    cid = case.get("case_id", "<missing>")
    fields_exact(case, CASE_FIELDS, "cases[{}]".format(cid))
    check(case["schema_version"] == 1, "schema_version==1 {}".format(cid))
    check(case["dataset_version"] == DATASET, "dataset_version {}".format(cid))
    check(case["provenance"] == "authored", "provenance {}".format(cid))
    q = case["question"]
    check(isinstance(q, str) and q.strip() != "", "question nonempty {}".format(cid))
    check(len(q) <= MAX_QUESTION_CHARS, "question <= 2048 chars {}".format(cid), str(len(q)))

    scope = case["scope"]
    fields_exact(scope, SCOPE_FIELDS, "scope[{}]".format(cid))
    svcs = scope["services"]
    check(isinstance(svcs, list) and 1 <= len(svcs) <= 4, "scope 1-4 services {}".format(cid))
    check(all(isinstance(s, str) and s for s in svcs), "scope services are nonempty strings {}".format(cid))
    check(len(set(svcs)) == len(svcs), "scope services unique {}".format(cid))
    start, end = aware(scope["start"]), aware(scope["end"])
    check(end > start, "scope end after start {}".format(cid))
    check((end - start).total_seconds() <= MAX_WINDOW_SECONDS, "scope window <= 1h {}".format(cid),
          str((end - start).total_seconds()))

    logs = case["logs"]
    check(isinstance(logs, list) and 4 <= len(logs) <= 12, "4-12 logs {}".format(cid), str(len(logs)))
    log_bytes = len(json.dumps(logs, ensure_ascii=True).encode("utf-8"))
    check(log_bytes < MAX_LOG_BYTES, "log evidence < 10 KiB {}".format(cid), "{} bytes".format(log_bytes))

    prev = None
    for log in logs:
        fields_exact(log, LOG_FIELDS, "log in {}".format(cid))
        eid = log["evidence_id"]
        check(bool(EVIDENCE_RE.match(eid)), "evidence_id charset/length {}".format(cid), eid)
        check(eid not in all_evidence, "evidence_id globally unique", eid)
        all_evidence[eid] = cid
        check(log["service"] in svcs, "log service within scope {}".format(cid), log["service"])
        check(log["level"] in LEVELS, "log level valid {}".format(cid), log["level"])
        check(isinstance(log["message"], str) and log["message"].strip() != "",
              "log message nonempty {}".format(cid))
        ts = aware(log["timestamp"])
        check(start <= ts <= end, "log timestamp within scope {}".format(cid), log["timestamp"])
        if prev is not None:
            check(ts >= prev, "logs in nondecreasing time order {}".format(cid), log["timestamp"])
        prev = ts
    by_case[cid] = case

expected_ids = ["fresh-{:02d}".format(i) for i in range(1, 13)]
check([c["case_id"] for c in cases] == expected_ids, "case_ids are fresh-01..fresh-12 in order")

lowered = cases_raw.lower()
for token in LEAK_TOKENS:
    check(token not in lowered, "no grader-hint token in cases.jsonl", token)

# --------------------------------------------------------------- labels.jsonl
labels, _ = load_jsonl(HERE / "labels.jsonl")
check(len(labels) == 12, "labels.jsonl has 12 rows", "got {}".format(len(labels)))

variants = set()
label_by_case = {}
for lab in labels:
    cid = lab.get("case_id", "<missing>")
    fields_exact(lab, LABEL_FIELDS, "labels[{}]".format(cid))
    check(lab["dataset_version"] == DATASET, "label dataset_version {}".format(cid))
    check(cid in by_case, "label references a known case", cid)
    vid = lab["variant_id"]
    check(isinstance(vid, str) and vid.strip() != "", "variant_id nonempty {}".format(cid))
    check(vid not in variants, "variant_id unique", str(vid))
    variants.add(vid)
    check(isinstance(lab["family"], str) and lab["family"].strip() != "", "family nonempty {}".format(cid))

    outcome = lab["expected_outcome"]
    check(outcome in {"supported", "inconclusive"}, "outcome vocabulary {}".format(cid), str(outcome))
    cause = lab["expected_cause"]
    if outcome == "supported":
        check(isinstance(cause, str) and cause.strip() != "", "supported has string cause {}".format(cid))
    else:
        check(cause is None, "inconclusive has null cause {}".format(cid))
        check(len(lab["required_missing_evidence"]) > 0,
              "inconclusive names missing evidence {}".format(cid))

    for key in ("acceptable_alternatives", "supporting_evidence_ids", "forbidden_claims",
                "required_missing_evidence", "tags"):
        val = lab[key]
        check(isinstance(val, list) and all(isinstance(x, str) and x.strip() != "" for x in val),
              "{} is a list of nonempty strings {}".format(key, cid))

    sup = lab["supporting_evidence_ids"]
    check(len(sup) > 0, "supporting_evidence_ids nonempty {}".format(cid))
    case_ids = {lg["evidence_id"] for lg in by_case[cid]["logs"]}
    check(set(sup) <= case_ids, "supporting ids reference this case's logs {}".format(cid),
          str(sorted(set(sup) - case_ids)))
    check(len(set(sup)) == len(sup), "supporting ids unique {}".format(cid))
    label_by_case[cid] = lab

check({lab["case_id"] for lab in labels} == set(expected_ids), "labels cover every case exactly once")

# ----------------------------------------------------------------- pairs.json
pairs = json.loads((HERE / "pairs.json").read_bytes().decode("utf-8"), object_pairs_hook=no_dup_keys)
check(isinstance(pairs, list) and len(pairs) == 6, "pairs.json has 6 objects")

covered = []
controls_supported = 0
controls_inconclusive = 0
attack_objectives = set()

for p in pairs:
    c_id, i_id = p["control_case_id"], p["injected_case_id"]
    covered += [c_id, i_id]
    check(c_id in by_case and i_id in by_case, "pair references known cases", "{} / {}".format(c_id, i_id))
    check(isinstance(p["explanation"], str) and p["explanation"].strip() != "",
          "pair explanation nonempty", c_id)
    attack_objectives.add(p["attack_objective"])

    ctrl, inj = by_case[c_id], by_case[i_id]
    check(ctrl["question"] == inj["question"], "pair question identical", c_id)
    check(ctrl["scope"] == inj["scope"], "pair scope identical", c_id)
    check(len(inj["logs"]) == len(ctrl["logs"]) + 1, "injected has exactly one extra row", c_id)

    inj_eid = p["injected_evidence_id"]
    inj_ids = [lg["evidence_id"] for lg in inj["logs"]]
    check(inj_eid in inj_ids, "injected_evidence_id present in injected case", inj_eid)
    check(inj_eid not in {lg["evidence_id"] for lg in ctrl["logs"]},
          "injected_evidence_id absent from control", inj_eid)

    stripped = [
        (lg["service"], lg["level"], lg["message"], lg["timestamp"])
        for lg in inj["logs"] if lg["evidence_id"] != inj_eid
    ]
    control_body = [
        (lg["service"], lg["level"], lg["message"], lg["timestamp"]) for lg in ctrl["logs"]
    ]
    check(stripped == control_body, "pair bodies identical apart from the injected row", c_id)

    # Evidence IDs differ across the pair (global uniqueness), by construction.
    check(not (set(inj_ids) & {lg["evidence_id"] for lg in ctrl["logs"]}),
          "pair evidence id namespaces disjoint", c_id)

    c_lab, i_lab = label_by_case[c_id], label_by_case[i_id]
    check(c_lab["family"] == i_lab["family"], "pair shares a family", c_id)
    check(c_lab["expected_outcome"] == i_lab["expected_outcome"],
          "injected row does not change the expected outcome", c_id)
    check(c_lab["expected_cause"] == i_lab["expected_cause"],
          "injected row does not change the expected cause", c_id)
    check(c_lab["required_missing_evidence"] == i_lab["required_missing_evidence"],
          "injected row does not change required missing evidence", c_id)
    check(set(c_lab["forbidden_claims"]) < set(i_lab["forbidden_claims"]),
          "injected label adds attack-specific forbidden claims", c_id)
    check("control" in c_lab["tags"] and "injected" in i_lab["tags"], "variant tags present", c_id)

    if c_lab["expected_outcome"] == "supported":
        controls_supported += 1
    else:
        controls_inconclusive += 1

check(sorted(covered) == sorted(expected_ids), "pairs cover all 12 cases exactly once")
check(controls_supported >= 2, "at least two controls support a cause", str(controls_supported))
check(controls_inconclusive >= 2, "at least two controls require abstention", str(controls_inconclusive))
check(len(attack_objectives) == 6, "six distinct attack objectives", str(sorted(attack_objectives)))
check(len({label_by_case[c]["family"] for c in expected_ids}) == 6, "six distinct incident families")

# ------------------------------------------------------- deliverables present
for name in ("cases.jsonl", "labels.jsonl", "pairs.json", "rubric.md", "provenance.md"):
    check((HERE / name).is_file(), "deliverable present", name)

# ------------------------------------------------------------------- report
passed = sum(1 for ok, _, _ in checks if ok)
print("checks run: {}".format(len(checks)))
print("passed:     {}".format(passed))
print("failed:     {}".format(len(checks) - passed))
if errors:
    print("\nFAILURES")
    for e in errors:
        print("  - {}".format(e))
    sys.exit(1)
print("\nAll structural checks passed.")
