# contentarchives

Tools for consolidating scattered personal media — phones, old laptops, external
drives, cloud exports, digitised tapes — into one deduplicated, date-organised
library, without destroying anything on the way.

Built out of a real consolidation of ~87,000 photos and videos spread across an
external drive, two cloud accounts, two machines and a failing USB enclosure.
Several of the rules in [`docs/LEARNINGS.md`](docs/LEARNINGS.md) were paid for with
permanently lost files. **Read that document before changing the safety rules.**

---

## This repo is also the project's canon

It is not only a toolkit. It is the shared brain for an in-flight consolidation that
several sessions, on more than one machine, read and write.

| Read first | |
|---|---|
| [`state/STATE.json`](state/STATE.json) | current state, generated — cannot have drifted |
| [`state/PROGRESS.md`](state/PROGRESS.md) | the same, readable |
| [`state/origin-folders.csv`](state/origin-folders.csv) | where every library file came from |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | storage model, and the protocol for sessions |
| [`docs/HANDOVER.md`](docs/HANDOVER.md) | what is done, what is open |

Finish by regenerating and committing state, even mid-task:

```bash
python tools/refresh.py    # rebuild origin map, recount, redact, update state/
```

**Never write project state from memory.** `track.py` counts files that exist;
a narrated summary drifts within minutes and the drift is invisible.

---

## The one thing to understand

> **A path is never sufficient grounds to delete.**

An exclusion rule containing the substring `\Downloads\` once matched
`...\work backup 2020\Downloads\Samsung S9 Edge Backup\DCIM\Camera\20181019_215516.mp4`
— a phone backup nested inside a downloads folder — and destroyed 45 irreplaceable
camera-original files.

Everything in `contentarchives/safety.py` exists because of that. Deletion is
allowlist-only, camera-original filenames are protected unconditionally, and a
duplicate may only be declared on a whole-file hash match.

---

## What it does

| Stage | Module | Notes |
|---|---|---|
| Scan sources | `inventory` | handles OneDrive placeholders and Drive stream mounts |
| Establish dates | `dating` | filename → EXIF → container → sidecar JSON → folder |
| Detect duplicates | `dedupe` | size → head+tail → whole-file hash |
| File into a library | `ingest` | hardlinks on the same volume, copies across |
| Consume cloud exports | `archives` | streams zip/tar members, never unpacks whole |
| Reduce size | `compress` | per-source settings, gated on measured SSIM/VMAF |

Nothing is ever deleted to make a stage succeed.

---

## Design rules

**Verify the thing, not a proxy for it.** A byte-size match does not prove a copy
completed — `Copy-Item` pre-allocates the destination, so sizes match from the moment
a copy starts. Open the archive and read its central directory instead.

**Checkpoint everything.** On a constrained machine, long jobs get killed. A 40 GB
archive with 3,000 members must resume mid-archive, not restart. Journal each
decision; cache hashes of files that never change.

**Stream, never slurp.** `zipfile.read()` loads a whole member into memory. On an
archive full of multi-gigabyte videos, that is what gets the process killed.

**Measure compression per source.** One CRF across a mixed library is wrong. Clean
phone sensors compress beautifully; grainy action-camera footage has a quality ceiling
bitrate cannot raise. Gate every file individually and keep the original on failure.

**Prefer keeping junk to losing signal.** A false positive costs disk space. A false
negative costs a memory. Those are not symmetric.

---

## Quick start

```bash
git clone git@github.com:krishanraja/contentarchives.git
cd contentarchives
python tests/test_safety_and_dedupe.py     # 9 tests, no dependencies
```

Copy `profiles/example.yaml`, point it at your sources and library, and work through
[`docs/HANDOVER.md`](docs/HANDOVER.md).

**Requirements:** Python 3.10+. `ffmpeg`/`ffprobe` on PATH for video dates and
compression (build with `libvmaf` if you want perceptual scoring). No other
dependencies for the core safety and dedupe paths — deliberately, so they can be
dropped onto any machine.

---

## Status

Working tools extracted from a live consolidation, not a finished product. The
safety, dating and dedupe layers are tested and in use. `inventory`, `ingest`,
`archives` and `compress` are being lifted out of the original single-machine
scripts.

## Licence

MIT — see [LICENSE](LICENSE).
