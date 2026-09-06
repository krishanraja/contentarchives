# Learnings

Every rule here was paid for. Most came from a real consolidation of ~87,000 photos
and videos across an external drive, two cloud accounts, two machines and a failing
USB enclosure. Several were paid for with permanently destroyed files.

Read this before changing the safety rules. The rules look paranoid until you learn
why each one exists.

---

## 1. A path is never sufficient grounds to delete

**The incident.** An exclusion rule contained the path fragment `\Downloads\`, intended
to catch downloaded course videos. It matched:

```
...\work backup 2020\Downloads\Samsung S9 Edge Backup - April 2019\DCIM\Camera\20181019_215516.mp4
```

A phone backup nested inside a Downloads folder. 40 camera-original videos from 2018
were destroyed. A second rule excluded a folder called `Movies` as ripped films and
took three `MVI_*.MOV` Canon camcorder files with it. Total: 45 irreplaceable files,
2.0 GB, deleted with `os.remove()` — which bypasses the recycle bin.

**The rule.** Deletion must be justified by *content*, never by what a path looks like.
Before deleting anything, prove the identical bytes exist elsewhere. The proof is a
whole-file hash comparison, not a filename, not a size, not a folder name.

**The deeper failure.** A content-hash engine already existed in the same codebase and
was used rigorously for *adding* files to the library. For *deleting* 30,959 files it
used a filename regex. The rigour was applied to the safe operation and withheld from
the dangerous one. If you have a strong check, use it on the irreversible path first.

See `contentarchives/safety.py` — deletion goes through a single allowlist function
that refuses anything not explicitly permitted.

---

## 2. Folder names lie, constantly

Real cases from one machine, with the folder names generalised:

| Folder named after… | What was actually in it |
|---|---|
| a medical document | 961 files, 15.8 GB — New Year's Eve photos and video |
| an immigration form | a 973-file phone backup |
| a scanned form | a full camera roll from the previous year |
| `work backup <year>` | 2,626 family photos, 6.4 GB |
| a former employer's laptop | scans of irreplaceable old family photographs |
| `Documents\Movies` | ripped films — **and** two real holiday photos |
| a person's name + a place | brand screenshots from a trade conference, i.e. work |

Six times a folder-name heuristic produced the wrong answer, in both directions:
personal material hidden under administrative names, and work material hidden under
names that read as personal.

The pattern is that people name folders after *why they created them*, not after what
ends up inside. A folder created to hold a scanned form becomes wherever that phone
got dumped six months later. Treat folder names as a weak hint for *review*, never as
a decision.

---

## 3. Modification times are worthless in a synced archive

Sync clients, backup tools and cloud downloads all rewrite mtime. A photo taken in
2018 will happily report a 2026 mtime. In one corpus, **40.6% of files** had no
trustworthy date from the filesystem at all.

Date precedence that actually works:

1. **Filename patterns** — `20190501_120000.jpg`, `IMG_20190501_120000`, `PXL_...`.
   Covered 69% of one corpus on its own.
2. **EXIF `DateTimeOriginal`** (tag 0x9003), parsed from the JPEG APP1 segment.
3. **Container metadata** for video — `ffprobe` `format_tags=creation_time`.
4. **Sidecar JSON** — Google Takeout ships `photoTakenTime.timestamp` next to each file.
5. **Folder name** containing a date, e.g. `2019-09-15 phone backup`.
6. Give up. Put it in `NoDate/` rather than inventing a date from mtime.

Validate every derived year against a plausible range. Phone clocks reset: real
filenames encountered included `VID_19740818_022559.mp4` and `VID_20340608_182645.mp4`.

---

## 4. Extensions lie too

`.mts` is normally AVCHD video. In two different corpora it was neither:

- 6,782 files averaging **1.5 KB** — app junk, not video
- 45,028 files that were **TypeScript declaration files** (`emnapi.d.mts`) in `node_modules`

Sanity-check extension against size before trusting it. A 1.5 KB video file is not a
video file. Similarly, `Photos.zip` turned out to contain 20 MP4s and no photos.

---

## 5. Cloud placeholders are invisible to naive scans

**OneDrive Files On-Demand** sets `FILE_ATTRIBUTE_REPARSE_POINT` on every placeholder.
A .NET enumeration with `AttributesToSkip = ReparsePoint` returns **zero** OneDrive
files and reports success. Set `AttributesToSkip` to 0 and test for
`RECALL_ON_DATA_ACCESS (0x00400000)`, `OFFLINE (0x1000)` and `UNPINNED (0x00100000)`.

**Google Drive for Desktop** sets none of those attributes, so hydration state is not
detectable from the filesystem at all. Reading a file may trigger a multi-GB download.

**Both report the local cache volume's free space, not cloud quota.** Two different
Drive mounts on the same machine reported identical free space, matching `C:`. Never
read quota from `Get-PSDrive` on a Drive mount; you are reading the wrong disk.

Reading a placeholder hydrates it and consumes local disk. Plan for it, and release
files afterwards (`attrib +U -P` on Windows) or the system drive fills.

---

## 6. Verify the thing, not a proxy for the thing

Three verification failures in a single 50 GB file copy:

| Check | Claimed | Reality |
|---|---|---|
| Byte-size comparison | copy complete | `Copy-Item` **pre-allocates** the destination; sizes match from the moment the copy starts |
| Process-exit poll | process finished | a transient spawn failure in the poll loop was read as "exited" |
| Log file written by the script | would confirm | the script had not reached that line yet |

All three failed in the direction of *falsely reporting success*. The only check that
behaved correctly was opening the archive and reading its central directory — because
that cannot succeed unless the data is genuinely there.

**Verify by doing the thing that requires the property you care about.** For an
archive, open it and count entries. For a media file, decode it. Size and mtime are
hints, not proof.

---

## 7. Deduplication needs content proof, but ruling out is cheap

A three-tier approach that is both fast and safe:

1. **Size** — from the directory or archive index. A file whose exact byte size exists
   nowhere in the library *cannot* be a duplicate. No I/O needed to clear it.
2. **Head + tail signature** — first and last 256 KB. Cheap, and rules out most
   collisions.
3. **Whole-file hash** — the only thing that may *declare* a duplicate.

Never skip to a verdict on filename plus size. In testing, two different files sharing
a name and an exact byte count are rare but real, and the failure mode is silent loss.
`tests/test_dedupe.py` encodes exactly this case.

**Same-recording-different-bytes is a real category.** Files can share an exact byte
count, an identical duration to the microsecond, and an identical creation timestamp,
yet differ in content hash — a re-mux or a rename. Content hashing correctly keeps
both. Deciding whether that is desirable is a human's call, not the tool's.

---

## 8. Compression settings are per-source, and must be measured

A single CRF across a mixed library is wrong. Measured on real footage, encoding to
HEVC and scoring against the source:

| Source | CRF | Saving | SSIM | VMAF | Verdict |
|---|---|---|---|---|---|
| Phone 4K, 73 Mbps | 22 | 76.7% | 0.9859 | — | compress |
| Phone 4K | 26 | 89.7% | 0.9815 | — | compress |
| Sony HD, 25 Mbps | 16 | 45.0% | 0.9824 | 94.24 | compress |
| Sony HD | 22 | 86.4% | 0.9738 | — | reject |
| GoPro 2.7K, 68 Mbps | 16 | 37.5% | 0.9760 | 89.83 | **reject** |
| GoPro 2.7K | 22 | 87.0% | 0.9630 | — | reject |
| DJI 1080p, 27 Mbps | 22 | 35.0% | 0.9672 | — | reject |

**Grainy footage has a quality ceiling that bitrate cannot raise.** GoPro SSIM moved
only 0.0092 across CRF 16→22 while size changed by a factor of five. The encoder is
removing sensor noise; the metric counts that as damage. VMAF independently agreed
(89.8 at the gentlest setting), so this is real degradation, not a metric artefact.

Clean sensors compress beautifully. Grainy ones should be left alone.

**Gate every file individually** — encode, check duration matches, check the saving is
worth it, then score quality. Replace only on all four. Anything failing keeps its
original untouched.

---

## 9. Long jobs get killed. Design for it.

On a memory-constrained machine, background jobs were killed roughly every five
minutes. Without checkpointing, a 40 GB / 3,000-member archive restarted from the
beginning every time and would never have finished.

- **Checkpoint per unit of work**, not per job. Append and flush after each item.
- **Journal decisions**, so a resumed run knows what it already concluded.
- **Cache anything expensive and stable.** Library file hashes never change; persist
  them. Re-deriving them cost gigabytes of reads per pass.
- **Stream, never slurp.** `zipfile.read()` loads an entire member into memory — on an
  archive of multi-GB videos that is a multi-GB allocation per file, and it is what
  triggered the kills. Use `zipfile.open()` and `shutil.copyfileobj` in chunks.
- **Detached processes survive watchdogs** that kill tracked background tasks.

---

## 10. Disk space projections from short samples are worthless

A download rate measured over 45 seconds gave 49.6 GB/hour and a prediction of 42
minutes of headroom. The actual rate was ~200 GB/hour and the drive filled well
before the projection said it would.

Do not extrapolate bursty I/O from a short window. Watch the actual free-space number
and act on thresholds, not forecasts. Keep a hard floor that halts work, and remember
a floor only stops *your* writes — it does not stop a browser downloading into the
same drive.

---

## 11. Hardlinks make a local library free

If the library lives on the same volume as the source files, hardlink instead of
copying. 26,506 files addressing 276 GB consumed **zero** additional bytes.

Consequences to remember:

- A hardlink is a second name for one set of bytes, **not** a second copy. It provides
  no redundancy whatsoever.
- Deleting the "original" frees nothing while the library entry exists.
- Backup tools walking the library tree copy real content, so backing up the library
  alone is sufficient — but back up *only* the library, or hardlinked content uploads
  twice.

---

## 12. A drive that drops under write load is failing, even if chkdsk is clean

An enclosure passed `chkdsk` with zero bad sectors and a clean filesystem, while
dropping off the bus under any sustained write — Event 51 paging errors, Event 153 I/O
retries, and a climbing device instance number (`DR3` → `DR4` → `DR5`) as it
re-enumerated. Reads worked perfectly throughout.

"The filesystem is clean" and "the hardware is fine" are different claims. Before
reformatting a drive you believe is corrupt, check whether it holds anything that
exists nowhere else — in this case 2,346 files, 28.8 GB, including a family member's
entire phone backup.

---

## 13. Let other agents refuse your instructions

A second machine running the same tooling twice refused tasks and was right both
times: once because a script's regex would not compile, once because the accompanying
description of a file list contradicted the list's own contents.

Both refusals cost a few minutes. Both would have cost far more had they complied.
Tell collaborating agents explicitly that refusing a wrong-looking instruction is the
desired behaviour, and give them the context to judge.

---

## 14. A file list built by extension describes the machine, not the memories

The second machine was surveyed for media by extension and produced 1,525 candidate
files. That sounded like a photo collection. It was not.

Triaged by origin folder, the batch was:

| | files | size |
|---|---|---|
| software screenshots — QA shots, prerendered UI, audit evidence | 1,055 | 424 MB |
| media | 460 | 6.6 GB |

And most of the 6.6 GB was produced content — a podcast recording, drone footage
exported for YouTube, marketing video — not memories either. The genuinely personal
material was a small fraction of a list that a size-and-extension filter had
presented as uniformly worth ingesting.

**A developer's machine is full of PNGs.** `shots/`, `screenshots/`, `.prerender/`,
`evidence/`, `profile/` — none of it is a photograph, all of it passes an extension
filter, and 1,055 of them dropped into a personal library would have made the
subsequent personal-versus-communal sort materially harder.

Two things follow.

**Triage by origin folder before ingesting, not after.** The folder a file came from
carries most of the signal about what it is. Extension carries almost none. This is
the same lesson as rule 4 from the other direction: there, an extension made real
media look like something else; here, an extension made project output look like
media.

**Where classification is genuinely ambiguous, preserve the origin folder instead of
guessing.** Deciding "podcast recording" versus "reference video someone downloaded"
from a filename is inference, and inference is what cost this project files (rule 1).
Files whose category is uncertain go to a holding tree with their origin folder as
the subfolder, where a person can settle it in seconds by looking at the grouping.
Sorting stays possible; guessing wrong stops being.
