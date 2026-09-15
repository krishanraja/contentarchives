"""Guards: the lessons in docs/LEARNINGS.md, as code every stage imports.

A rule that lives in a document is followed by whoever remembers it. On
2026-09-15 eleven of them were broken in one afternoon by a session that had
cited several while building (learning 50). A rule that lives here is followed
by whoever calls the function, which is the only kind of following that survives
a new stage being written in a hurry.

    guards.files      atomic_writer, atomic_write_text   learning 42
                      require_dir, require_file           learnings 34, 41
                      complete_lines                      learning 42
    guards.alignment  check_alignment                     learning 45
    guards.verify     verdict, OK / WRONG / CANNOT_TELL   learnings 6, 46

Import with the repo root on sys.path:

    sys.path.insert(0, <repo root>)
    from guards.files import atomic_writer, require_dir

Also guards, but not Python: scripts/chains/steps.ps1 (Invoke-Step: preflight,
progress, verify, postcondition) and scripts/chains/arm.ps1 (detach, restart,
reap orphans). They move here when the running video chain has finished.
"""
