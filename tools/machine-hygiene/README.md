# machine-hygiene

Enforcement for the file-routing rule: **nothing lives loose in the Windows profile
root.** Written after a cleanup that removed 68 stray directories and 109 loose files
from `C:\Users\<you>` and reclaimed 185 GB.

Full procedure: [`../../docs/MACHINE-HYGIENE.md`](../../docs/MACHINE-HYGIENE.md).

Both scripts derive the profile root from `USERPROFILE`, so they are portable.

## `guard-profile-root.mjs`

A Claude Code `PreToolUse` hook. Blocks, with routing guidance, anything that would
create a new file or folder directly in the profile root.

Copy into `~/.claude/hooks/` and register in `~/.claude/settings.json` for **both**
matchers, merging with any hooks already there:

```json
"PreToolUse": [
  { "matcher": "Bash",
    "hooks": [{ "type": "command",
      "command": "node C:/Users/<you>/.claude/hooks/guard-profile-root.mjs" }] },
  { "matcher": "Write|Edit|NotebookEdit",
    "hooks": [{ "type": "command",
      "command": "node C:/Users/<you>/.claude/hooks/guard-profile-root.mjs" }] }
]
```

> **Forward slashes are mandatory.** Hook commands run through Git Bash, where `\` is
> an escape character — a backslash path silently becomes an unresolvable one and the
> hook fails on every invocation without ever reporting an error.

**Blocks:** `Write` to the root; `git clone` / `touch` / `mkdir` / `cp` / `mv` /
shell redirection targeting the root; and any file-producing command whose **working
directory is the root** (the vector that caused most of the original mess — a script
writes relative to cwd, so no command-text inspection can catch it).

**Allows:** dotfiles and dot-directories, the standard Windows user folders, edits to
files already at the root, read-only commands at the root, and root paths appearing
inside heredoc bodies (that is data, not a write).

## `sweep-profile-root.mjs`

The backstop. The hook only sees Claude Code's own tool calls — Codex, Cursor, an
installer or a stray script can still drop files. This sweeps them up.

```bash
node sweep-profile-root.mjs           # report only (default); exit 2 if strays found
node sweep-profile-root.mjs --apply   # quarantine into .scratch/root-strays/<date>/
```

It **moves, never deletes**, and appends to `.scratch/root-sweep.log`. Schedule
`--apply` daily (see the runbook), and run the exact scheduled command by hand once to
confirm the node path resolves.

## `guard-profile-root.test.mjs`

24 cases covering both what must be blocked and what must **not** be (the
false-positive guards matter more — a guard that blocks ordinary work gets removed).

```bash
node guard-profile-root.test.mjs                  # tests the hook beside it
GUARD_HOOK=/path/to/installed.mjs node guard-profile-root.test.mjs
```

Passing tests prove the logic, **not** that the hook is wired up. After installing,
confirm it actually fires by attempting a write it should block.
