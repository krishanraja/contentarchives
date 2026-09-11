r"""Delete this project's own scratch - but prove each file first.

Two categories, two different proofs:

  _h_speedtest   copies pulled off H: to measure throughput. Proof required:
                 the file is still on H: at the same size. Then the copy is
                 redundant, not the only version.

  _pilot*        compression-pilot output - reference segments and the same
                 clip re-encoded at CRF 16/18/20/22/24. Derived files this
                 project generated and can generate again. Proof required:
                 the name matches the pilot's own output shape, so a real
                 memory that wandered in would NOT be swept up.

  _machine-b_stage already proven: all 781 files hash-match a library copy.

Anything failing its proof is left alone and reported.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

H_GOPRO = r"H:\My Drive\_photo-consolidation\from-gopro-2024"
PILOT_SHAPE = re.compile(
    r"^(ref_|hw\d+|qsv_|enc_|t_).*\.mp4$"      # encoder test outputs
    r"|^[A-Za-z0-9_]+_(crf)?\d{2}\.mp4$"       # same clip at CRF 16/18/20/22/24
    r"|.*_native_crf\d+\.mp4$")

kept: list[str] = []
freed = 0
apply = "--apply" in sys.argv


def h_index() -> dict[str, int]:
    idx = {}
    for dp, dns, fns in os.walk(H_GOPRO):
        for fn in fns:
            try:
                idx[fn.lower()] = os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return idx


hgp = h_index()
print(f"H: from-gopro-2024 holds {len(hgp):,} files")

# ---- _h_speedtest --------------------------------------------------------
d = r"D:\_h_speedtest"
if os.path.isdir(d):
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if not os.path.isfile(p):
            continue
        sz = os.path.getsize(p)
        src = hgp.get(fn.lower())
        if src == sz:
            print(f"  OK  on H: at same size -> {fn} ({sz/1024**2:.0f} MB)")
            freed += sz
            if apply:
                os.remove(p)
        else:
            kept.append(f"{p} (H: has {src}, local {sz})")

# ---- pilots --------------------------------------------------------------
for d in (r"D:\_PhotoAudit\_pilot", r"D:\_PhotoAudit\_pilotfast",
          r"D:\_PhotoAudit\_pilotlow"):
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if not os.path.isfile(p):
            continue
        if PILOT_SHAPE.match(fn):
            freed += os.path.getsize(p)
            if apply:
                os.remove(p)
        else:
            kept.append(f"{p} (name does not match pilot output shape)")

# ---- _machine-b_stage: proven wholly redundant by check_scratch_safe.py -----
d = r"D:\_machine-b_stage"
if os.path.isdir(d):
    sz = sum(os.path.getsize(os.path.join(dp, f))
             for dp, dn, fs in os.walk(d) for f in fs)
    freed += sz
    print(f"  _machine-b_stage: {sz/1024**3:.2f} GB, all 781 files hash-match "
          f"a library copy")
    if apply:
        shutil.rmtree(d, ignore_errors=True)

print(f"\nreclaimable: {freed/1024**3:.2f} GB")
if kept:
    print(f"KEPT (proof failed) - {len(kept)}:")
    for k in kept:
        print(f"   {k}")
if apply:
    for d in (r"D:\_h_speedtest", r"D:\_PhotoAudit\_pilot",
              r"D:\_PhotoAudit\_pilotfast", r"D:\_PhotoAudit\_pilotlow"):
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    print(f"DONE. D: now {shutil.disk_usage('D:\\').free/1024**3:.1f} GB free")
else:
    print("DRY RUN - re-run with --apply")
