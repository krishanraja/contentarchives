r"""Every module in this repository can be imported. Nothing runs when it is.

    python tests\test_imports.py

WHY

Phase 3 moved 39 files into their stages and broke eleven of them. They all
compiled. They all passed `py_compile`. They died on IMPORT, because `paths.py`
had moved into `guards/` and nothing caught it - those scripts have no tests, and
`test_stage_contracts.py` checks that a cited file EXISTS at its path, never that
it loads. The breakage was found by hand, one script at a time.

Stages 01-04 and 09-12 have still to move. This is the net that should have been
under phase 3, in place before the next move rather than after it.

WHAT IT PINS, AND WHY IN THREE PARTS

  1. LIBRARIES import cleanly. A module with no top-level work is imported and
     nothing else - guards/, contentarchives/, the journal. These are the files
     phase 3 actually broke, and the first version of this sweep SKIPPED them:
     it excluded anything without a `main`, which is exactly the set most worth
     sweeping, and then reported a clean run. A check whose scope excludes its
     own subject is the recurring defect in this project (learnings 54, 55).

  2. GUARDED SCRIPTS import without doing their work. `if __name__ ==
     "__main__": main()` is what makes a 371 GB cloud survey safe to import, and
     that property is worth asserting rather than assuming: the import must
     succeed AND leave the filesystem alone.

  3. UNGUARDED SCRIPTS are a NAMED, SHRINKING list. Sixteen modules still run
     work at module level. They are listed below by name, and a module that
     joins them fails this test. That makes it a ratchet: the list can only get
     shorter - each is a candidate for the treatment h_capacity.py and
     verify_h_batch.py got, the body indented into main().
"""

from __future__ import annotations

import ast
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import stagepath  # noqa: E402,F401  - the same bootstrap every module uses

CODE_DIRS = ["scripts", "stages", "guards", "tools", "contentarchives"]

# Modules that still do work at module level, by name. A module joining this set
# fails the test; removing one from the set is the fix, not adding to it.
#
# These are one-shot scripts whose whole body is the program: no main(), no
# guard, so importing one runs it. Each is a candidate for the same treatment
# h_capacity.py and verify_h_batch.py got - the body indented into main(), the
# constants left at module level.
#
# answers.py and store.py were in this list and are NOT here now. A first,
# blunter sweep counted "32 libraries / 53 guarded / 18 unguarded" by flagging
# any top-level `if`, which nearly every script has, and those numbers are NOT
# the authority - reading answers.py settled it: its top level is a docstring,
# imports, the bootstrap, four constants, a threading.Lock() and a class. It
# touches nothing. It is a library, and the list was wrong, not the classifier.
# clear_scratch.py and free_wins.py LEFT this list on 2026-09-16, and they are
# the reason the list matters. Both sat in 10 reclaim - the only stage that
# destroys data - and both ran their whole body at import: clear_scratch called
# os.remove and shutil.rmtree, free_wins called os.remove with NO dry-run flag
# at all, so `import free_wins` deleted a file. The sweep could not touch either,
# which meant the safety net was built AROUND the two most dangerous files in the
# repo. Both now have a main() and a __main__ guard, and free_wins gained the
# --apply gate its sibling always had.
UNGUARDED = {
    "stages/10_reclaim/audit_deletions.py",
    "scripts/big_files.py",
    "stages/10_reclaim/check_scratch_safe.py",
    "scripts/check_tiny.py",
    "scripts/diagnose_new.py",
    "scripts/driver.py",
    "stages/10_reclaim/full_deletion_audit.py",
    "scripts/test_dedup.py",
    "scripts/verify_dupes.py",
    "scripts/watch_d_downloads.py",
    "scripts/whatsapp_breakdown.py",
    "stages/05_enrich/consensus.py",
    "stages/05_enrich/store_summary.py",
}

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  {:<64} {}".format(name, "OK" if ok else
                               "FAIL got={!r} want={!r}".format(got, want)))
    if not ok:
        FAILURES.append(name)


def _is_syspath_insert(node):
    """Exactly `sys.path.insert(...)` or `_sys.path.insert(...)`, nothing else.

    This exemption was `func.attr == "insert"` in the first version, which
    forgave EVERY top-level insert call anywhere - and with the while-walk
    exemption beside it, almost every script's real body read as harmless. The
    sweep then reported 87 libraries and 1 guarded script, against 32 and 53
    counted by hand, and passed. Matching loosely is how a check comes to measure
    something other than its subject (learnings 54, 55).
    """
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    f = node.value.func
    if not isinstance(f, ast.Attribute) or f.attr != "insert":
        return False
    owner = f.value                                  # want `<mod>.path`
    return (isinstance(owner, ast.Attribute) and owner.attr == "path"
            and isinstance(owner.value, ast.Name)
            and owner.value.id in ("sys", "_sys"))


def _is_stagepath_walk(node):
    """The bootstrap's `while ... not exists(join(_d, 'stagepath.py')): ...`."""
    if not isinstance(node, ast.While):
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value == "stagepath.py":
            return True
    return False


def classify(path):
    """-> ("library" | "guarded" | "unguarded"), by what the TOP LEVEL does.

    Every module carries the same three-line bootstrap - a `while` walking up to
    stagepath.py and one `sys.path.insert` - which is top-level work in the
    literal sense and must not count, or every guarded script reads as dangerous.
    Both exemptions are matched EXACTLY (see above); anything else at top level
    is work.
    """
    src = io.open(path, encoding="utf-8", errors="replace").read()
    tree = ast.parse(src)
    guard, work = False, False
    for node in tree.body:
        if isinstance(node, ast.If):
            t = node.test
            if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                    and t.left.id == "__name__"):
                guard = True
                continue
            work = True
        elif _is_stagepath_walk(node):
            continue
        elif isinstance(node, (ast.For, ast.While, ast.With)):
            work = True
        elif _is_syspath_insert(node):
            continue
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            work = True
    # THE GUARD DECIDES FIRST, and this ordering is the whole bug fixed twice.
    # `work` only ever became True for a top-level For/While/With or bare call,
    # and a well-formed script has none of those: its body is a docstring,
    # imports, constants, defs, and `if __name__ == "__main__": main()`. So
    # `work` stayed False and h_capacity.py, build_db.py and 85 others returned
    # "library" - indistinguishable from guards/paths.py - while section 3
    # asserted the guard property about exactly one file and passed.
    #
    # A module carrying a __main__ guard IS a script, by definition. A module
    # with neither a guard nor top-level work is a library.
    if guard:
        return "guarded"
    return "unguarded" if work else "library"


def modules():
    for d in CODE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [x for x in dns if x != "__pycache__"]
            for fn in sorted(fns):
                if fn.endswith(".py"):
                    full = os.path.join(dp, fn)
                    yield os.path.relpath(full, ROOT).replace("\\", "/"), full


def imports_cleanly(path):
    """-> None on success, or a one-line reason."""
    name = "importsweep_" + os.path.basename(path)[:-3]
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return None
    except BaseException as e:                       # SystemExit included
        return "{}: {}".format(type(e).__name__, str(e).splitlines()[0][:100])
    finally:
        sys.modules.pop(name, None)


def main():
    found = {"library": [], "guarded": [], "unguarded": []}
    broken_syntax = []
    for rel, full in modules():
        try:
            found[classify(full)].append((rel, full))
        except SyntaxError as e:
            broken_syntax.append((rel, str(e)[:60]))

    print("1. every module parses")
    check("no module has a syntax error", [r for r, _ in broken_syntax], [])

    print()
    print("2. libraries import cleanly - the files phase 3 actually broke")
    print("   {} of them".format(len(found["library"])))
    bad = []
    for rel, full in found["library"]:
        why = imports_cleanly(full)
        if why:
            bad.append("{} ({})".format(rel, why))
    check("every library imports", bad, [])

    print()
    print("3. guarded scripts import WITHOUT running their work")
    print("   {} of them".format(len(found["guarded"])))
    bad = []
    for rel, full in found["guarded"]:
        why = imports_cleanly(full)
        if why:
            bad.append("{} ({})".format(rel, why))
    check("every guarded script imports", bad, [])

    print()
    print("4. the unguarded list only ever shrinks (a ratchet, not a snapshot)")
    now = {rel for rel, _ in found["unguarded"]}
    joined = sorted(now - UNGUARDED)
    left = sorted(UNGUARDED - now)

    # A RELOCATION is not a regression, and the message used to claim it was.
    # Moving 10 reclaim's scripts into their stage made this report three modules
    # as "newly started working at import time" and three as having "left the
    # list" - the same three files, arriving at one path and departing another.
    # Nothing about them had changed. A correct result with a wrong explanation
    # is how somebody comes to distrust a working check, so say `moved` when a
    # basename appears on both sides.
    moved = sorted(j for j in joined
                   if os.path.basename(j) in {os.path.basename(l) for l in left})
    if moved:
        print("   {} MOVED rather than regressed - repoint them in UNGUARDED:".format(
            len(moved)))
        for m in moved:
            print("      " + m)
    arrived = [j for j in joined if j not in moved]
    check("no module has newly started working at import time", arrived, [])
    if left:
        print("   {} left the list - remove them from UNGUARDED: {}".format(
            len(left), ", ".join(left)))
    check("the list is {} long and documented".format(len(UNGUARDED)),
          len(now - set(left)) <= len(UNGUARDED), True)

    print()
    print("5. every script a subprocess launches still exists")
    # An import sweep cannot see a subprocess launch, and two stage moves in one
    # afternoon each left one dangling: runner.py went on launching
    # scripts/purge_redundant.py after it moved to stages/10_reclaim/. The
    # failure is silent until somebody runs that stage, which for a runner means
    # overnight. stagepath.script() resolves a name wherever the conveyor put it,
    # so the rule is: launch by NAME, never by a path built from __file__.
    launched = re.compile(r'os\.path\.join\(\s*(?:SCRIPTS|HERE|_HERE)\s*,\s*["\']([^"\']+\.py)["\']')
    dangling = []
    for rel, full in modules():
        src = io.open(full, encoding="utf-8", errors="replace").read()
        for m in launched.finditer(src):
            target = m.group(1)
            line = src[:m.start()].count("\n") + 1
            if not os.path.isfile(os.path.join(os.path.dirname(full), target)):
                where = stagepath.find(target)
                dangling.append("{}:{} launches {} (it is at {})".format(
                    rel, line, target, where or "NOWHERE"))
    check("no launch points at a script that has moved", dangling, [])

    print()
    print("summary: {} libraries, {} guarded, {} unguarded".format(
        len(found["library"]), len(found["guarded"]), len(found["unguarded"])))
    if FAILURES:
        print()
        print("{} FAILED: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
