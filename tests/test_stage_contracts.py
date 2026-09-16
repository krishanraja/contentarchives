r"""The repo is a conveyor of stages. Fail the build when it stops being one.

    python tests\test_stage_contracts.py

WHY

On 2026-09-15 a session with all forty-nine learnings in reach broke eleven of
them in one afternoon (learning 50). The lessons lived in a 1,650-line document
and reached new machinery only through whoever remembered them. This test moves
that memory into the build:

  1. every stage has a STAGE.md with Inputs, Outputs, Invariants, Code, Tests
     and Lessons
  2. every learning in docs/LEARNINGS.md has an owner
  3. every enforcement a Lessons table names EXISTS - the file, and the literal
     text inside it (a function, a test's check name) - so a claim cannot outlive
     the code that backed it
  4. every code file in the repo belongs to exactly one stage, and every test
     file to at least one
  5. learnings enforced only in prose are counted and printed as debt: allowed,
     but visible, never silent

Adding learning 51 fails this test until a stage claims it.

A detector with a hole is worse than none, because the green tick is believed
(test_chain_gating.py found that the hard way), so the checks are first run
against a deliberately broken stage and must catch every defect in it.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ["Inputs", "Outputs", "Invariants", "Code", "Tests", "Lessons"]
# "Edge cases" is optional and holds the one-off investigations: Krish, 2026-09-16,
# "one off investigations need to be stored not as part of core machinery but how
# to deal with common edge cases". A script claimed there is OWNED - findable when
# the edge case recurs - without being machinery anyone must maintain.
OPTIONAL = ["Edge cases"]
# stages/ was missing from this list when the conveyor's first stages moved, and
# 34 files silently became unowned without the test objecting: the ownership
# check can only see the trees it is told about. Anything holding .py or .ps1
# belongs here, and an empty tree costs nothing.
CODE_DIRS = ["contentarchives", "engine", "tools", "scripts", "guards", "stages"]
REF = re.compile(r"`(test|guard|code):([^`:]+?)(?::([^`]+))?`")


def sections(text):
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    return out


def table_rows(body):
    rows = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|") or re.match(r"^\|[\s:|-]+\|$", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    return rows[1:] if rows else []                 # drop the header row


def backticked(cell):
    return re.findall(r"`([^`]+)`", cell)


def audit_stage(name, text, root):
    """-> (problems, code files, test files, {learning: [refs]}, prose-only learnings)"""
    problems, code, tests, owned, prose = [], [], [], {}, []
    sec = sections(text)
    for s in REQUIRED:
        if s not in sec:
            problems.append("{}: no '## {}' section".format(name, s))
    # Code, plus any Edge cases table: a one-off investigation is owned so it can
    # be found when that edge case recurs, without being core machinery.
    for section in ["Code"] + OPTIONAL:
        for cells in table_rows(sec.get(section, "")):
            for p in backticked(cells[0])[:1]:
                if not p.endswith((".py", ".ps1", ".mjs")):
                    continue
                code.append(p)
                if not os.path.isfile(os.path.join(root, p)):
                    problems.append("{}: {} lists {} which does not exist".format(
                        name, section, p))
    for p in re.findall(r"`(tests/[^`]+)`", sec.get("Tests", "")):
        tests.append(p)
        if not os.path.isfile(os.path.join(root, p)):
            problems.append("{}: Tests lists {} which does not exist".format(name, p))
    for cells in table_rows(sec.get("Lessons", "")):
        if len(cells) < 3 or not cells[0].isdigit():
            problems.append("{}: a Lessons row is not '| N | ... | enforced by |': {}".format(
                name, " | ".join(cells)[:60]))
            continue
        n, enforced = int(cells[0]), cells[-1]
        refs = REF.findall(enforced)
        if "prose-only" in enforced:
            prose.append(n)
        elif not refs:
            problems.append("{}: learning {} names no enforcement and does not say "
                            "prose-only".format(name, n))
        for kind, path, needle in refs:
            full = os.path.join(root, path.strip())
            if not os.path.isfile(full):
                problems.append("{}: learning {} cites {} which does not exist".format(
                    name, n, path))
            elif needle and needle not in io.open(full, encoding="utf-8",
                                                  errors="replace").read():
                problems.append("{}: learning {} cites '{}' in {} and it is not there".format(
                    name, n, needle, path))
        owned.setdefault(n, []).extend(refs)
    return problems, code, tests, owned, prose


def self_test():
    """The detector must catch a broken stage, or nothing it passes means anything."""
    bad = ("# 99 broken\n\n## Inputs\n- x\n## Outputs\n- x\n## Code\n"
           "| file | role |\n|---|---|\n| `engine/does_not_exist.py` | ghost |\n"
           "## Tests\n- `tests/nope.py`\n## Lessons\n| # | what | enforced by |\n|---|---|---|\n"
           "| 6 | a claim | `code:guards/verify.py:this text is not in that file` |\n"
           "| 7 | a claim with no evidence | trust me |\n")
    problems = audit_stage("self-test", bad, ROOT)[0]
    want = ["no '## Invariants' section", "does_not_exist.py which does not exist",
            "tests/nope.py which does not exist", "and it is not there",
            "does not say prose-only"]
    missed = [w for w in want if not any(w in p for p in problems)]
    if missed:
        print("DETECTOR SELF-TEST FAILED - it did not catch: {}".format(missed))
        return False
    return True


def main():
    if not self_test():
        sys.exit(1)
    stage_files = sorted(
        os.path.join("stages", d, "STAGE.md") for d in os.listdir(os.path.join(ROOT, "stages"))
        if os.path.isdir(os.path.join(ROOT, "stages", d))) + [os.path.join("guards", "STAGE.md")]
    problems, owners, test_owners, all_owned, prose = [], {}, set(), {}, {}
    enforced_refs = {}                  # learning -> [refs from each stage that cites code/tests]
    for sf in stage_files:
        full = os.path.join(ROOT, sf)
        if not os.path.isfile(full):
            problems.append("{} does not exist".format(sf))
            continue
        name = os.path.basename(os.path.dirname(sf))
        p, code, tests, owned, pr = audit_stage(name, io.open(full, encoding="utf-8").read(), ROOT)
        problems += p
        for c in code:
            owners.setdefault(c.replace("\\", "/"), []).append(name)
        test_owners.update(t.replace("\\", "/") for t in tests)
        for n, refs in owned.items():
            all_owned.setdefault(n, []).append(name)
            if refs:
                enforced_refs.setdefault(n, []).append(refs)
        for n in pr:
            prose.setdefault(n, []).append(name)

    learnings = [int(n) for n in re.findall(r"^## (\d+)\. ", io.open(
        os.path.join(ROOT, "docs", "LEARNINGS.md"), encoding="utf-8").read(), re.M)]
    unowned = [n for n in learnings if n not in all_owned]
    if unowned:
        problems.append("every learning has an owner: learnings {} have none".format(unowned))

    repo_code = []
    for d in CODE_DIRS:
        for dp, dns, fns in os.walk(os.path.join(ROOT, d)):
            dns[:] = [x for x in dns if x != "__pycache__"]
            for fn in fns:
                if fn.endswith((".py", ".ps1")):
                    repo_code.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace("\\", "/"))
    for f in sorted(repo_code):
        if f not in owners:
            problems.append("every code file belongs to a stage: {} belongs to none".format(f))
        elif len(owners[f]) > 1:
            problems.append("{} is claimed by {} stages: {}".format(f, len(owners[f]), owners[f]))
    for dp, dns, fns in os.walk(os.path.join(ROOT, "tests")):
        for fn in fns:
            if fn.endswith((".py", ".ps1")):
                rel = os.path.relpath(os.path.join(dp, fn), ROOT).replace("\\", "/")
                if rel not in test_owners:
                    problems.append("every test belongs to a stage: {} belongs to none".format(rel))

    # Debt is a learning NO stage enforces. One stage may enforce it in code
    # while another records it as prose-only work still to do - as 02 ingest does
    # for learning 51, which 06 faces enforces - and that is not debt, it is a
    # stage being honest about what it has not built yet.
    enforced = [n for n in learnings
                if any(refs for stage_refs in enforced_refs.get(n, []) for refs in [stage_refs])]
    prose = {n: s for n, s in prose.items() if n not in enforced}
    print("stages: {}   code files owned: {} of {}   learnings: {}".format(
        len(stage_files), sum(1 for f in repo_code if f in owners), len(repo_code), len(learnings)))
    print("learnings enforced in code or tests: {}".format(len(enforced)))
    print("learnings enforced ONLY in prose (debt): {}  {}".format(
        len(prose), sorted(prose)))
    if problems:
        print()
        print("FAILED ({}):".format(len(problems)))
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
