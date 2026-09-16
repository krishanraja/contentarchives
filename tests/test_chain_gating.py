r"""Fail the build if a chain runs work that never proved it works.

    python tests\test_chain_gating.py

WHAT IT ENFORCES

Every subprocess launched from scripts/chains must go through Invoke-Step, which
makes a preflight, a progress signal and a postcondition mandatory. A convention
that lives only in a document is not a rule - the next person to add a step, or
the next agent in a hurry at 2am, writes `python -u thing.py` because that is
what the lines above it look like, and nothing objects.

This objects. It is the half of the guarantee that survives new subprocesses
being added creatively, which is exactly what was asked for.

HOW IT DECIDES

Inside scripts/chains/*.ps1 it looks for process launches - a bare `python`, a
`Start-Process`, a `&` call of an executable - and requires each to sit inside an
`Invoke-Step` block (or be on the allowlist below with a written reason).

WHAT IT DOES NOT CLAIM

It cannot stop anyone running python by hand in a terminal, and it does not try.
It stops ungated work entering a CHAIN - the thing that runs unattended for
fourteen hours while everybody is asleep, where an unproven step is expensive.
That boundary is worth stating rather than pretending the guard is total.

A step whose preflight is `{ $true }` passes this test. That is deliberate: the
goal is to make skipping the guard a visible, reviewable lie in a diff rather
than an omission nobody notices.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Chains live with the stage they drive, and the runner and launchers live in
# guards/. Before the conveyor they all sat in scripts/chains; a single directory
# constant would now scan nothing and pass, which is the failure mode this whole
# file exists to prevent (learning 44).
CHAIN_DIRS = [os.path.join(ROOT, "guards")] + [
    os.path.join(ROOT, "stages", d)
    for d in sorted(os.listdir(os.path.join(ROOT, "stages")))
    if os.path.isdir(os.path.join(ROOT, "stages", d))]

# Launches that are legitimately outside a step, each with a reason. Anything
# added here should be arguable out loud.
ALLOW = {
    # the launcher and the watcher are not steps; they START chains
    "arm.ps1": "registers the scheduled task - it launches chains, it is not one",
    "rearm_when.ps1": "watches a log and calls arm.ps1 - supervises, does no work",
    "steps.ps1": "defines Invoke-Step itself",
}

# Things that start a process, matched ANYWHERE in the line, not just at the
# start of it. The first version of this anchored with ^\s* and therefore missed
#
#     $jobs += Start-Process python -PassThru ...
#
# reporting "OK - every launch is inside Invoke-Step" for a file with an ungated
# launch in it. A detector with a hole is worse than no detector, because the
# green tick is believed. Deliberately broad now: a false positive costs one line
# on the allowlist, a false negative costs a night.
LAUNCH = re.compile(
    r"\bStart-Process\b"
    r"|\bStart-Job\b"
    r"|\bInvoke-Expression\b"
    r"|(?:^|[|;&(=]|\+=)\s*python(?:\.exe)?\b"   # python at the head of a command
    r"|&\s*[\"'$(]",                             # & "x.exe" / & $exe / & (Join-Path ...)
    re.IGNORECASE)

# Lines that only LOOK like launches: comments, and the many ways a script talks
# ABOUT a process without starting one.
IGNORE = re.compile(
    r"^\s*#"
    r"|^\s*<\#|^\s*\.DESCRIPTION"
    r"|Get-Command|Get-CimInstance|Get-Process|Win32_Process"
    r"|Stop-Process|Wait-Process|Where-Object"
    r"|-match|-replace|-Filter|Select-String",
    re.IGNORECASE)

# The detector is a safeguard, so it proves itself before it is believed - the
# same rule it exists to enforce. Each case is a line that has actually appeared
# in this project.
DETECTOR_CASES = [
    ("$jobs += Start-Process python -PassThru -WindowStyle Hidden", True),
    ('python -u "$repo\\engine\\classify_live.py" --apply', True),
    ('    python -u "$repo\\tools\\master_sheet.py" *>> $log', True),
    ("& (Join-Path $here 'arm.ps1') -Chain $Chain", True),
    ("$out = & python $repo\\engine\\classify_live.py --dry-run", True),
    # and things that must NOT trip it
    ('$p = Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'"', False),
    ("# python -u thing.py   (how it used to be launched)", False),
    ("if ($_.CommandLine -match 'classify|faces_embed') { 'busy' }", False),
    ("Say 'step B: re-judging with python'", False),
    ("$procs | Where-Object { -not $_.HasExited }", False),
]


def self_test():
    """Refuse to report on the chains until the detector is shown to work."""
    bad = []
    for line, should_flag in DETECTOR_CASES:
        flagged = bool(LAUNCH.search(line)) and not IGNORE.search(line)
        if flagged != should_flag:
            bad.append((line, should_flag, flagged))
    if bad:
        print("DETECTOR SELF-TEST FAILED - not scanning anything with a broken detector:")
        for line, want, got in bad:
            print("   want flag={!s:<5} got flag={!s:<5}  {}".format(want, got, line[:66]))
        sys.exit(1)
    print("detector self-test: {} cases OK".format(len(DETECTOR_CASES)))
    print()


def blocks_of(text):
    """Line index -> True if that line is inside an Invoke-Step call.

    Brace counting is enough here: chain scripts are flat, and the alternative
    (a real PowerShell parse) needs PowerShell, which a test should not.
    """
    inside = [False] * (len(text) + 1)
    active = False
    depth = 0
    seen_brace = False
    for i, ln in enumerate(text):
        if not active and re.search(r"\bInvoke-Step\b", ln) and not ln.strip().startswith("#"):
            active, depth, seen_brace = True, 0, False
        if active:
            inside[i] = True
            opens, closes = ln.count("{"), ln.count("}")
            if opens:
                seen_brace = True
            depth += opens - closes
            # The call ends once braces have opened and balanced AND the line is
            # not a backtick continuation. Without the continuation check the
            # block appears to end at the first `} \`` - the close of -Preflight -
            # so every later scriptblock (-Start, where the launch actually is)
            # reads as ungated. That is the failure this detector exists to
            # prevent, committed inside the detector itself.
            if seen_brace and depth <= 0 and not ln.rstrip().endswith("`"):
                active = False
    return inside


def main():
    self_test()
    failures = []
    checked = 0
    live = [d for d in CHAIN_DIRS if os.path.isdir(d)]
    if not live:
        print("no chain directories found among:\n  " + "\n  ".join(CHAIN_DIRS))
        sys.exit(1)

    found = [(fn, os.path.join(d, fn)) for d in live
             for fn in sorted(os.listdir(d)) if fn.endswith(".ps1")]
    if not found:
        # An empty scan passing is the failure this file exists to prevent: the
        # chains moved into their stages on 2026-09-16 and a stale directory
        # constant would have reported "all gated" while scanning nothing.
        print("no .ps1 found in any of:\n  " + "\n  ".join(live))
        sys.exit(1)

    for fn, path in found:
        text = io.open(path, encoding="utf-8", errors="replace").read().split("\n")
        if fn in ALLOW:
            print("  {:<28} allowed: {}".format(fn, ALLOW[fn]))
            continue
        checked += 1

        # A chain that CALLS Invoke-Step without dot-sourcing steps.ps1 is worse
        # than one that never used it: PowerShell reports an unknown command and
        # carries on by default, so every step is skipped in silence and the
        # chain prints its completion message anyway. That happened on
        # 2026-09-13 - "faces done" and "PHASE 3B COMPLETE" at 02:06, with no
        # faces run at all - because an edit inserting the dot-source aborted
        # before writing while the calls landed. The structural check is cheap.
        joined = "\n".join(text)
        if re.search(r"^\s*Invoke-Step\b", joined, re.M):
            if not re.search(r"^\s*\.\s+[\"'][^\"']*steps\.ps1[\"']", joined, re.M):
                failures.append((fn, [(0, "calls Invoke-Step but never dot-sources steps.ps1")]))
                print("  {:<28} CALLS Invoke-Step WITHOUT LOADING IT".format(fn))
                continue
            if not re.search(r"Get-Command\s+Invoke-Step", joined):
                failures.append((fn, [(0, "dot-sources steps.ps1 but never asserts it loaded")]))
                print("  {:<28} no assertion that steps.ps1 actually loaded".format(fn))
                continue

        # Every Invoke-Step must carry a -Verify. It is Mandatory in the runner,
        # so a missing one is already an error at run time - but at run time
        # means "three hours into an overnight job", and the whole point of
        # -Verify is that discovering things late is what hurts. A step whose
        # -Verify is `{ $true }` still passes this: the aim is to make skipping
        # correctness a visible line in a diff, not to stop a determined author.
        for m in re.finditer(r"^\s*Invoke-Step\b", joined, re.M):
            start = joined.count(chr(10), 0, m.start())
            window = chr(10).join(text[start:start + 90])
            if "-Verify" not in window:
                failures.append((fn, [(start + 1, "Invoke-Step with no -Verify: "
                                       "checks it is MOVING, not that it is CORRECT")]))
                print("  {:<28} an Invoke-Step has no -Verify".format(fn))
                break

        gated = blocks_of(text)
        hits = []
        for i, ln in enumerate(text):
            if IGNORE.search(ln):
                continue
            # An inline exemption must carry a reason and must sit on the line
            # directly above, so it appears in the diff next to what it excuses.
            # Silent exceptions are how a rule stops being a rule.
            prev = text[i - 1] if i else ""
            exempt = re.search(r"#\s*gate:exempt\s+(\S.*)", prev)
            if LAUNCH.search(ln) and not gated[i] and not exempt:
                hits.append((i + 1, ln.strip()[:76]))
        if hits:
            failures.append((fn, hits))
            print("  {:<28} {} UNGATED launch(es)".format(fn, len(hits)))
        else:
            print("  {:<28} OK - every launch is inside Invoke-Step".format(fn))

    print()
    if failures:
        print("FAILED: work that never proved it works can enter a chain.")
        print()
        for fn, hits in failures:
            for line_no, src in hits:
                print("  {}:{}  {}".format(fn, line_no, src))
        print()
        print("Wrap it in Invoke-Step (guards/steps.ps1), which forces a")
        print("preflight, a progress signal and a postcondition - or add it to")
        print("ALLOW in this file with a reason that survives being read aloud.")
        sys.exit(1)

    print("all {} chain script(s) gated".format(checked))


if __name__ == "__main__":
    main()
