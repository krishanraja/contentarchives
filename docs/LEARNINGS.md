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

### The fallback branch that verifies nothing

A later run reproduced the same failure in a subtler place. A verifier dispatched on
file type — JPEG decoded, PNG decoded, MP4 box structure walked — and sent everything
else to a generic branch that read the first four bytes and recorded them as a
signature. **That branch has no failure mode.** Hand it an empty file and it reads
`b""`, reports `sig=`, and returns no error.

A zero-byte `.mpg` passed verification on that basis and was published, in a run whose
whole purpose was catching zero-byte files. Thirty-one of its siblings *were* caught,
but only by accident: JPEG and MP4 parsing happen to fail when given no input. Nothing
in the design was catching them, and the one file whose extension missed the typed
checks walked straight through, hashed clean, and shipped.

**Check the invariants that hold for every file before dispatching on type.** Zero
bytes is never valid content. Neither is a size that disagrees with the manifest, nor a
file that has since vanished. A per-type check is for what makes *that type* valid; it
is the wrong place to discover the file is empty.

Then audit the fallback branch on its own terms. Ask what input would make it **fail**.
If there is no answer, it is not a check — it is a log line that happens to run inside
a function called `verify`.

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

---

## 15. A cloud stream mount hangs; it does not fail

Hashing a batch of files directly off a Google Drive stream mount stopped dead
partway through. No exception, no timeout, no error in any log — the process simply
stopped making progress with the loop counter frozen.

What proved it was a hang rather than slow I/O:

```
ReadTransferCount at T:      685,809,515
ReadTransferCount at T+20s:  685,809,515
```

Zero bytes in twenty seconds. A slow mount still moves bytes; a hung one does not.
**Check the process's I/O counters before concluding "it's just slow"** — on
Windows, `Get-CimInstance Win32_Process | Select ReadTransferCount`. That single
measurement separates "wait longer" from "this will never finish", and it takes
twenty seconds.

The cause is that a stream client presents remote files as local ones. When it
cannot fetch a file's content, the read blocks rather than returning an error, and
there is no timeout to trip. Rule 5 covered these mounts lying about *presence*;
this is the same class of problem for *content*.

**Copy the batch to local disk first, then work on it.** Not because copying is
faster, but because a local read either succeeds or raises. A bounded copy with
explicit retry limits (`robocopy /R:2 /W:5`) fails loudly in minutes where the
direct read hangs forever.

It is also usually free. If the staging copy lands on the same volume as the
library, files enter the library as hardlinks — a second name for bytes already on
disk, no copy, no wait (rule 11).

### And kill the orphan

The first hung run's Python process survived cancellation of the shell that
started it. It sat there competing for the same saturated mount while the
replacement run tried to make progress, and would have overwritten the report with
output from a superseded classifier. **After cancelling a long job, confirm the
process is actually gone** — `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`
lists command lines and start times, which is enough to tell the orphan from the
replacement.

---

## 16. Reconcile the manifest against the disk, or removals go unrecorded

The manifest maps every library file to where it came from, and the origin map is
built from it. Checking it against reality found 12 rows pointing at files that no
longer exist:

| | rows |
|---|---|
| journalled at the library, with a reason | 2 |
| not journalled anywhere | 10 |

The 10 are DVD cover art and a torrent-site logo — worthless, and almost certainly
removed by the same cleanup that took the ripped films they belonged to. But
**nothing recorded their removal**, and that is the part that matters. Their sources
were not in the deletion journals either, so there is no record establishing what
took them.

If ten worthless files can leave the library unrecorded, so can ten irreplaceable
ones, and the only reason this was noticed at all is that something reconciled the
record against the disk. Rule 1 stops the wrong file being deleted. This is the
check that notices when something was deleted anyway.

**Run `tools/check_manifest.py` after any pass that removes or moves files.** It
exits non-zero on an unexplained absence, so it belongs in the end-of-session
routine next to `refresh.py` — a count of "present" is not evidence when nobody
compared it to what should be there.

Note the deliberate distinction it draws: a library file whose *source* was
journalled is reported as weaker evidence, not as accounted for. A hardlinked
library entry survives its source being deleted, so "we deleted the original" does
not explain the library copy vanishing — and quietly treating it as an explanation
would hide exactly the case worth seeing.

---

## 17. A cloud mount's free space is the local cache's free space

`Get-PSDrive` on a Google Drive for Desktop mount reports the free space of the
**local cache volume**, not the cloud account. Two mounts backed by entirely
different accounts both echoed the system drive's figure.

The error is not small and it points the dangerous way: a 2 TB destination with
~1.65 TB free reported about 133 GB. Planning from that number rules out a backup
that is comfortably possible.

There is a matching trap on the way out. Drive for Desktop **stages uploads through
that same local cache**. So the destination has room, the source has room, and one
large copy still fills the system drive and dies partway. Batch the upload and check
the cache volume between batches.

**Capacity for a cloud mount comes from the account, not the filesystem.** This is
the same lesson as rule 5 — these mounts present themselves as ordinary drives and
are not — applied to space rather than to presence.

**Baseline what you have reviewed, or the check stops working.** Those 10 rows would
report red on every future run, and a check that is permanently red is one people
learn to skip — which is exactly when a real absence slips through. `--accept`
records reviewed absences into `state/accepted-absences.csv` with a note and a date,
so the check returns to green and *any new absence stands out immediately*. The
accepted file is committed: it is the record of what was looked at and by when, not
a way to make the warning go away.

---

## 18. Journal before the destructive act, not after

A purge script deleted verified-duplicate files in a loop and wrote its journal
after the loop finished. That is backwards.

The journal exists for the case where something goes wrong. A crash, a kill by the
memory watchdog, a power cut — any of them leaves files deleted and the record of
what they were never written. The one moment the journal is genuinely needed is the
exact moment that design fails to produce one.

Write the record first, flush it, then delete:

```python
journal_one(path, size, keep)   # append + flush + fsync
os.remove(path)
```

`flush()` alone is not enough; the buffer can still be sitting in the OS page cache
when the process dies. `os.fsync()` is what puts it on the disk.

The asymmetry decides the ordering. A journal entry for a deletion that then failed
is a harmless over-record — it says a file went that is still there, and the next
reconciliation (`check_manifest.py`) will notice and say so. A deletion with no
entry is unrecoverable ignorance: nothing left to compare against, and no way to
know what was lost.

Same reasoning as rule 6 — verify the thing, not a proxy — applied to bookkeeping.
An end-of-run journal records what a *successful* run did. It says nothing about the
runs that matter.

---

## 19. Read the video's own clock, or a folder name will date it for you

The date chain was filename, then EXIF, then a sidecar JSON, then the folder name,
then NoDate. EXIF parsing only handles JPEG headers. Nothing ever called `ffprobe`.

So every video without a date in its filename was dated by **the name of the folder
it happened to arrive in**. 1,707 videos in an 8,310-video library.

What that produced, from one phone backup:

| file | filed as | actually shot |
|---|---|---|
| `…phone upto sept 2019 030.mp4` | 2019-07 | **2014-06** |
| `…phone upto sept 2019 120.mp4` | 2019-07 | **2017-12** |
| `…phone upto sept 2019 814.mp4` | 2019-07 | **2019-08** |

Five years of one phone's video history collapsed into a single month, because the
containing folder was named `2019-07-23 …`. Probing the containers found 392
misfiled and 18 recoverable from `NoDate`; 750 were already right, which is exactly
what made the problem invisible.

**A container's `creation_time` is written by the camera when it records.** It is
evidence. A folder name is somebody's filing decision from years later, and it dates
the *arrival* of a file, not its creation — an archive called
`drive-download-20220107…` says when it was exported, and diving footage inside it
was filed under that January.

Guards worth having, because container metadata is not uniformly trustworthy:

- **Reject known-bogus epochs.** Muxers that cannot read a clock write `1970-01-01`,
  `1904-01-01`, `1601-01-01`. They are not dates.
- **Never override a filename date.** A camera-assigned name like
  `20180310_161838.mp4` outranks the container; re-muxing tools rewrite
  `creation_time` to the moment of the re-mux.
- **Take no timestamp over a bad one.** 518 files had nothing usable and were left
  alone. `NoDate` is an honest answer.

Wrong dates lose nothing, which is why this survived so long. In a chronology it is
still the central failure: putting a memory in the wrong year defeats the one thing
the structure exists to do.

---

## 20. `\b` is the wrong word boundary for filenames

Classifying documents by filename produced two nonsense results:

```
202-2024981_ganesha-vector-ganesh-visarjan-clipart.png   -> 01-Identity
ASSET- logo usable as icon or favicon, social shares.jpg -> 01-Identity
```

`visa` matched inside **visa**rjan. `oci` matched inside s**oci**al. A substring
decided a file's fate, which is rule 1 wearing different clothes: there it deleted
files, here it only misfiled them, but the reasoning error is identical.

The obvious fix — wrap every term in `\b` — then broke the true positives:

```
Screenshot_20181205-141138_CommBank.jpg   ->  no match
AUSPASSPORT.jpg                           ->  no match
```

**Underscore is a word character.** There is no `\b` between `_` and `C`, so
`\bcommbank\b` cannot match a name that plainly says CommBank. Filenames separate
words with underscores, hyphens and digits; `\b` respects none of them.

The boundary that actually applies to filenames is *not a letter*:

```python
def W(*terms):
    return r"(?<![A-Za-z])(" + "|".join(terms) + r")(?![A-Za-z])"
```

That rejects visarjan and social, accepts `_CommBank` and `-passport`, and for
multi-word terms the separator class must be `[\s_-]*` rather than `\s*`, or
`marriage_certificate.jpg` slips through. Concatenations with no separator at all
(`AUSPASSPORT`) still need an explicit alternative.

Two things worth carrying:

**Test the classifier against the names that actually exist**, not invented ones.
Every failure above came from real filenames and none would have appeared in a
hand-written test case.

**When a term is weak, find a stronger one.** The fix for `bank` was not a cleverer
boundary but the names of banks — `commbank`, `natwest`, `barclays`. A specific term
needs no boundary tricks because it cannot be a substring of something innocent.

---

## 21. A resolution is only evidence when a camera could not have produced it

Classifying screenshots by exact screen dimensions flagged 14,826 files. Broken
down by which signal fired, 4,302 of those rested on "screen resolution + no camera
EXIF" with nothing else — and that bucket was full of photographs:

```
1,425  768x1024      IMAG0647.jpg, IMAG0961.jpg   (Windows Phone camera)
  870  1536x2048     IMG-20140806-WA0001.jpg      (WhatsApp, 2014)
  548  1024x768      IMG_20161229_160711.jpg
```

Those resolutions are iPad screen sizes. They are also standard **camera**
resolutions — 1536x2048 is a 3MP photograph. Every 4:3 frame in the library was a
candidate for being called a screenshot.

**Aspect ratio is the discriminator, not the pixel count.** Cameras produce 4:3,
3:2 and 16:9. Phone screens are 19.5:9 or 20:9. A file at 1080x2400 cannot be a
photograph; a file at 1024x768 tells you nothing at all. Screen resolutions that
overlap camera shapes belong in an explicitly *ambiguous* set that never counts as
evidence on its own.

The second error compounded it: a screen-size match was allowed to **override a
camera filename**. Messenger platforms strip EXIF, so a forwarded photograph has no
camera tags; if its resolution then collided with a screen size, the filename lost
and the file was reclassified. Nothing about a resolution should outrank the fact
that a camera named the file.

### The part that generalises

The total looked plausible. 14,826 screenshots in a 65,000-image library is exactly
what you would expect, and it was wrong by 3,000 files.

**Break a classifier's output down by which signal fired, and inspect the weakest
combination.** The 10,244 files with `Screenshot` literally in the name were never
in doubt. All the error lived in the bucket that rested on inference, and that
bucket is invisible in a summary count.

A classifier that moves rather than deletes makes false positives cheap — which is
the point of rule 1 — but cheap is not free. Three thousand photographs quietly
relocated out of a chronology are not destroyed, and are still lost to anyone
browsing for them.

---

## 22. Equal size is not equal content, and some formats make collisions ordinary

**The incident.** A Norton 360 backup set kept several generations of each file. An
extractor wrote every generation to the same destination path, so they overwrote each
other. When this was found, 55 of the 58 affected groups were written off as harmless
because *all generations were the same number of bytes* — clearly just repeated backups
of an unchanged file.

Once each generation was given its own destination and hashed, two of those groups held
genuinely different content at **identical size**:

```
Tax 82a accounts 2015 2016.xls   50,688 B, 4 generations, 2 distinct contents
Ba Will allocation.xls           79,872 B, 4 generations, 2 distinct contents
```

Legacy `.xls` allocates in fixed-size sectors. Editing a cell frequently does not change
the file length at all. The same is true of many container formats that pad or
pre-allocate: `.doc`, disk images, database files, some TIFFs.

One of those two documents allocates a will.

**The rule.** Size equality is not evidence of content equality, and it is at its most
dangerous where it is most convincing — a byte-exact match on a large file *feels* like
proof. If two files must be shown to be the same, hash them.

**Why this is not a contradiction of rule 7.** Rule 7 uses size to rule duplicates
*out*: a file whose size appears nowhere in the library cannot be a duplicate of
anything in it, which is sound and costs no I/O. The converse does not follow. A size
match narrows the candidates; it never closes the question.

**The deeper failure.** The two versions would have overwritten each other *and passed
verification*, because verification compared sizes. A check that shares an assumption
with the thing it checks confirms the assumption, not the data.

---

## 23. A destination map must be proven injective before the first write

**The incident.** The extractor above keyed each output on the payload's original path.
Norton's multiple generations, and any live file sharing that path, all resolved to one
destination. 62 destinations absorbed 304 files. Last writer won, in silence.

29 of those writes came from containers that turned out to be 201–203 byte headers with
no payload at all. They extracted to zero bytes *over files that were already correct*,
destroying 29 family photographs, one of them a 47 MB video.

The copy job reported `0 failures`, and it was telling the truth. Every write succeeded.

**The rule.** Before writing anything, build the full source→destination map and assert
that no two sources share a destination. Abort on collision. Do this even when the
naming scheme "obviously" cannot collide.

```python
seen = {}
for src, dst in jobs:
    if dst.lower() in seen:
        raise SystemExit("collision: %s and %s -> %s" % (seen[dst.lower()], src, dst))
    seen[dst.lower()] = src
```

**The deeper failure.** The eventual fix had three parts: give recovered payloads their
own subtree, suffix colliding names with a generation id, and assert uniqueness up
front. The first two make a collision *unlikely*. Only the third makes a silent
overwrite **unrepresentable** — and unlikely is not a safety property, because the
failure is silent and the report still says success.

Corollary: **a copy job's "0 failures" counts write errors. It says nothing about files
a later write destroyed.** Count distinct destinations against source rows, and treat a
shortfall as a defect.

---

## 24. When the source is being destroyed, a skip needs the same proof as a delete

**The incident.** Rescuing a drive that was to be physically destroyed afterwards, an
extractor skipped 19,209 backup payloads whose **path and size** matched a file already
being copied off the live filesystem. Skipping them was framed as an optimisation:
those files were already coming across, so re-extracting them was waste.

Hashing all 156 GB of the skipped set took 45 minutes and found the assumption false for
**174 of them**: 16 differed in content despite an identical path and size, and 158 had
no live counterpart being copied at all. Every one of those would have ceased to exist
when the drive was destroyed.

**The rule.** Once the source is going away, *declining to copy is deleting*. A skip
therefore needs the same standard of proof as rule 1 demands for deletion: identical
bytes, proven by hash, present somewhere that survives.

**The deeper failure.** Deletion gets scrutiny because it looks dangerous. A skip looks
like efficiency, is invisible in the output, produces no log line, and shows up in the
metrics as *speed*. There is no artefact to audit afterwards — the missing file leaves
no trace anywhere.

If the copy set was filtered, verify the **filter**, not just the files that made it
through.

---

## 25. A cloud mount cannot tell you whether the cloud has your data

**The incident.** 140.62 GB was published to a Google Drive mount and every file was
re-read from that mount and verified by content hash. 17,102 of 17,102 matched. The
obvious reading — the data is safely in the cloud — was wrong, and the source drive was
about to be destroyed on the strength of it.

A write into a Drive mount lands in the **local cache** and uploads behind it. Reading
the mount reads the cache. The check and the thing being checked were the same local
bytes.

Two probes exposed it. A 12 KB README, rewritten and copied in, still served its
*previous* version through the Drive API an hour later. And the files robocopy wrote
last were absent from the cloud entirely — not delayed, simply not there.

**The rule.** Verify a cloud destination through the **cloud's** API, and verify sync
completion from the **client's own queue** — never from the mounted filesystem.

Google Drive for Desktop keeps its state in SQLite:

```
%LOCALAPPDATA%\Google\DriveFS\<account_id>\metadata_sqlite_db
```

The `operations` table is the backlog of work not yet committed to the cloud. Copy the
file before reading it, then count rows. It drains to 0 when the client is actually
finished. Here it started at **21,615** and took roughly three hours to clear, at
1.6–3.5 ops/s.

**The deeper failure.** Progress was reported for over an hour as "waiting for Drive"
while the one number that would have answered the question sat in a database on the same
machine. Polling the API for one file's size and inferring the state of 140 GB from it
is not measurement, it is anecdote. When something is "still syncing", find the queue
and read its depth — an ETA changes what a person can decide; a shrug does not.

**Related.** Rule 17 says a cloud mount's free space is the local cache's free space.
This is the same illusion one layer along: a cloud mount's *contents* are the local
cache's contents.

---

## 26. Export part numbers are not stable identities

**The incident.** Three of six Takeout archives (002, 003, 004) had exhausted Google's
five-download limit, so a fresh export of the same photo set was requested two days
later. The plan was reasonable and nearly cost thousands of files: verify that the new
`001` matched the already-ingested old `001`, and if so, ingest only the new 002-004.

The new `001` did not match. Of the 5,857 files old `001` had contributed to the
library, **4,260 were still there at the same path and byte size, 1,595 were absent
from the new `001` entirely**, and 2 had merely moved path. Zero size mismatches — the
bytes were stable. What moved was the **partitioning**.

Fingerprinting then showed the new `001` carried **3,058 files the library did not
have** (8.8 GB, 36% of the part), and the new `002` carried **4,291** (16.5 GB, 60%).
Files from the never-ingested old 002/003/004 had scattered across the new archives.
Skipping the new `001` as "already done" would have silently dropped 3,058 files.

**Why.** An exporter packs a traversal into fixed-size parts and cuts a new part
whenever the running total hits the cap. Every boundary therefore depends on the total
size of everything before it, so **one file added or removed anywhere shifts that
boundary and every boundary after it.** Two days of phone backups, plus trash aging out
on its 60-day timer, is more than enough. Boundaries cascade forward, which is the
cruel part: a change late in the traversal leaves part 001 pristine while moving
everything downstream. The check most likely to be run is the one least able to detect
the problem.

**The rule.** A part number identifies a position in one export, never a set of files.
Two exports are two different partitionings of overlapping content; **parts may never be
matched across them by number.** Judge a part only by what it contains.

**How.** `zip_fingerprint.py` reads the **central directory** only — member names and
sizes, no extraction, no hashing — so a 50 GB archive is triaged in seconds against the
library's `(name, size)` index. Run it on every part of every export and let the count
of un-held files decide whether the part is worth ingesting. Content-hash dedup at
ingest remains the authority; the fingerprint only decides where to spend the effort.

**The cheap safe fallback.** Ingest every part of the new export and let the dedup
absorb the overlap. Once the link was fixed this cost about two hours of unattended
transfer — far less than the cost of being wrong about which parts mattered.

---

## 27. A cache is invalidated by moves, not just by writes

**The incident.** 35,114 Takeout members were checked against the library's dedup
index. **382** were rejected as duplicates. The other 34,732 were filed as new, and
roughly **222 GB of them were byte-identical to files the library already held**.
Nothing errored, no check failed, and the ingest reported success.

The index maps size to library paths. It is cached, and refreshed by replaying
`autopilot-added.csv`, on a premise stated in its own docstring: that file is *"the
ONLY thing that adds to the library"*. That premise is true. It is also the wrong
question.

`apply_split.py` had **moved** tens of thousands of files out of `Library\` into
`Personal\` and `Communal\`. A move is not an addition, nothing recorded it, and
every cached path pointing at those files went stale. Measured afterwards: **62.9%
of cached paths pointed at files that no longer existed.**

**Why it was silent.** The dedup asks `full_hash(candidate) == this_member`.
`full_hash` returns `None` for a file it cannot open. `None == hash` is `False`.
So a stale candidate is indistinguishable from a genuine non-match:

```python
for c in candidates:
    if full_hash(c) == th:      # None == th  ->  False  ->  "not a duplicate"
        ...
```

There is no exception to catch, no error to log, and no counter that moves. The
only visible symptom was a suspiciously low duplicate count, which reads as good
news.

**A correction, found 2026-09-08.** The above is true and was NOT the main cause.
Rebuilding the cache did not fix it, because `_walk_index()` walked only
`Library\` and `NoDate\` - **8,036 files** - while `Personal\` and `Communal\`
held **60,724, or 88% of the library**. `apply_split.py` created those two trees
and nothing ever taught the index they existed.

So the dedup was not consulting a stale map of the library. It was consulting a
map of 12% of it, and a fresh walk of the wrong roots is still the wrong roots.
The staleness was real and secondary; this was the bug.

It is a nastier failure than staleness because rebuilding - the obvious remedy,
and the one applied first - produces an index that is perfectly current and
still blind. The symptom is identical, the fix appears to work, and nothing
errors either way.

**The rule.** A path index is invalidated by anything that changes a path -
moves and renames included, not only writes. Delete `lib-index.pickle` after any
split, reclassification or manual tidy.

**The stronger rule.** An index must be able to state WHAT IT COVERS, and that
claim must be checked against reality. `INDEX_ROOTS` is now explicit, and the
cheap assertion is a count: an index holding 8,036 entries for a 79,300-file
library is wrong on its face, and nobody looked at the number for a day.

**The deeper rule.** *A comparison that returns a falsy sentinel on failure cannot
distinguish "different" from "unreadable".* Wherever a lookup can fail, count the
failures and report them; a dedup that cannot open its own candidates should say
so loudly, not quietly conclude there is no duplicate. The counter added here fires
at 1, 100, 1,000 and 10,000 stale candidates for exactly that reason.

**How it was found.** Not by the ingest, which was content. By asking why a drive
was full: a size-group scan showed 23,082 groups of same-size files, and hashing a
sample by **inode** - not by path, because hardlinks make two names look like two
copies - showed 97.2% were genuinely duplicated content on separate inodes. The
question "why is the disk full" audited the ingest more effectively than the
ingest audited itself.

---

## 28. Two names for one file is not two copies, and hashing cannot tell you

**The incident.** Twice in one evening, on the same question - "how much of this
drive is duplicated?" - the same wrong answer was produced two different ways.

*First:* a folder listing showed six backup folders totalling 264 GB, apparently
free for the taking. They were **94-97% hardlinked** into the library. Deleting
them would have freed **1-3 GB each**, not 264 GB. The consolidation had already
banked that saving; the listing was double-counting bytes that exist once.

*Second, worse:* a sample hashed pairs of same-size files and reported **96.8%
byte-identical**, which reads as an enormous reclaim. But two hardlinks to one
inode return the *same hash by construction* - it is the same file being read
twice. The measurement could not have produced any other answer, and it was
about to justify deleting "duplicates" that were the library's own entries.

**The rule.** Identity of CONTENT is not identity of STORAGE.

  - `hash(a) == hash(b)` proves the bytes match. It says nothing about whether
    deleting one frees anything.
  - `(st_dev, st_ino)` equality proves they are the same file. Deleting one name
    frees **zero** bytes.
  - Reclaimable duplication requires **both**: identical content AND distinct
    inodes.

So any deduplication measurement must key on `st_ino` before it hashes anything,
and any "bytes on this volume" figure must count each inode once. Counting by
name inflated 879.5 GB of real data to 1,202.0 GB - a phantom 322.5 GB.

**Where it bites hardest.** A drive whose consolidation strategy was
*hardlink rather than copy* - which was the right strategy, and is exactly why
293 GB entered this library at zero cost - is a drive where every naive
duplicate scan reports a fortune that does not exist. The better the earlier
work, the more convincing the illusion.

**The tell.** If a reclaim estimate is suspiciously close to the amount of data
you know was consolidated, you are measuring the consolidation, not the waste.

**Related.** Learning 17 (a cloud mount reports the wrong volume's free space)
and learning 22 (equal size is not equal content) are the same family: a number
that is easy to read standing in for one that is true.

---

## 29. A classifier's precedence order can defeat its own strongest rule

The router that decides whether a file from H: is a memory, produced work, or
admin was built with a deliberate precedence: **positive provenance outranks
negative inference**. `DCIM\100GOPRO\GH010008.MP4` sitting under a folder called
Downloads is a camera file that passed through a downloads folder, not a QA
artifact, so the camera test runs first and wins.

That reasoning is sound and it produced a wrong answer at scale.

Android names a screenshot `Screenshot_20230105_031931.png`. The datestamp
`\d{8}_\d{6}` is the *same shape a camera writes*, so the camera test matched,
returned `chronology`, and the word "Screenshot" - sitting in plain sight at the
front of the filename - was never examined. 17,173 files were routed to the
chronology on this rule, and thousands of them were screenshots, which is
precisely the category the user had asked to keep out of it.

**The rule.** Order signals by how *self-declaring* they are, not by how strong
they feel:

  1. the file says what it is (`Screenshot_`, `screen_record`) - trust it
  2. provenance inferred from a naming convention (`DCIM`, `GH######`)
  3. inference from surrounding folder names
  4. a permissive default

A name a device *chose to write* beats a pattern you *recognised*. Two devices
can share a pattern; only one of them writes the word.

**The tell.** A precedence rule justified by a good example is untested against
the case where both rules fire on the same file. Enumerate those overlaps
deliberately - they are the only place the ordering actually does any work.

---

## 30. `\b` treats `_` as a word character, so half the pattern never fired

`\bdsc\d{4}` does not match `_DSC1215.JPG`. `\bshots?\b` does not match
`shot_adweek.png`. Underscore is in `[A-Za-z0-9_]`, so there is no word boundary
between `_` and `D`, nor between `t` and `_`.

Camera filenames and path-flattened dumps are *made of underscores*. The camera
and production patterns were both silently under-firing on exactly the corpus
they were written for, and the failure was invisible: every file still got a
destination - the default one - and the totals looked plausible.

**The rule.** In any pattern meant to match filenames, `\b` is the wrong
boundary. Use explicit character-class edges - `(?<![a-z0-9])` and
`(?![a-z0-9])` - so `_`, `-` and `.` all count as separators.

**The tell.** A regex validated only on strings that match. Validate on strings
that *should* match and currently do not: after the fix, `from-lorimer`'s
production share moved 46.5% to 58.0%, and `_DSC1215.JPG` was newly recognised
as a camera file. Neither was visible in the totals.

---

## 31. `ignore_errors=True` on a cleanup path hides the failure that fills the disk

The batched ingest keeps peak disk usage to one batch by deleting the staged
copy after each batch: `shutil.rmtree(lp(STAGE), ignore_errors=True)`.

`shutil.rmtree` on a `\?\`-prefixed path failed here. With `ignore_errors=True`
it failed **silently**, returned normally, and the next batch staged another
20 GB on top of it. Across 24 batches that is not a warning, it is a full disk -
and the log would have shown 24 successful batches right up until it stopped.

**The rule.** Error suppression is fine where failure is harmless. On a path
whose *entire purpose* is to reclaim a resource, suppression converts a loud
failure into a silent one. Delete without suppression, then assert the
postcondition - the directory is gone - and halt if it is not.

**The tell.** `ignore_errors=True` written on the same line as the thing that
makes the algorithm's space bound hold.

---

## 32. "356 GB of originals to delete" was 318.9 GB of hardlinks and 4.2 GB of reclaim

D: held 362 GB outside the library - `Samsung S9+ Backup`, `work backup 2020`,
`Laptop 2024 files` and a dozen more: the sources the library was built from,
authorised for deletion once verified safe inside it.

Classified against the filesystem, with `(st_dev, st_ino)` checked *before*
hashing anything:

| | files | GB |
|---|---|---|
| RECLAIMABLE - different inode, identical bytes | 987 | **4.2** |
| HARDLINK - same inode, deleting frees nothing | 26,398 | 318.9 |
| ONLY - exists nowhere in the library | 51,492 | 39.2 |

Deleting every "original" on the drive would have freed **4.2 GB**, not 356.
This is learning 28 arriving as a plan rather than a measurement: the
consolidation was *done well*, by hardlink, and a well-consolidated drive is one
where every source folder looks like pure waste and is in fact the library
itself wearing a second name.

**The second half matters more.** 51,492 files exist on D: and nowhere in the
library. The instinct that produced the deletion plan would have removed them as
"already consolidated". They are the opposite: they are what consolidation
missed.

**The rule.** A deletion plan needs three outcomes, not two. `redundant` /
`only copy` omits the case that is both - same bytes, one name to delete, zero
bytes recovered - and that case was 88% of this drive.

---

## 33. A plan that covered 5 of 11 folders reported success on 5

The H: ingest was sized, dry-run, and verified end-to-end on a pilot folder:
21,262 files, 295.5 GB, 15 batches, 8.1 hours. Every number was measured. The
pilot passed all five verification checks with a file-count delta of exactly 0.

H: had **11 folders**. The plan named 5. The missing 6 included
`Krish - Phone Backup - Jun to Sep 2025` - 73.2 GB and, by camera signature, the
most memory-dense folder on the drive.

Nothing in the pipeline could catch this, because every tool was asked "did you
do what you were told?" and every one correctly answered yes.

**The rule.** Verification confirms the work you specified. It cannot confirm
the specification. Any job defined over a *set* must separately prove the set is
complete: enumerate the container, diff it against the plan, and name what is
excluded and why. The ingest now prints and appends folders missing from its
priority list rather than skipping them in silence.

**The tell.** A dry run whose totals were never reconciled against an
independent enumeration of the source. "15 batches, 295.5 GB" is a statement
about the plan, not about the drive.

---

## 34. `os.walk` on a directory that does not exist reports an empty library

`track.py` opens with "Every number here is counted from a file that exists, not
asserted." It then counted `D:\ContentLibrary\Library` and
`D:\ContentLibrary\NoDate`. The restructure had moved the chronology to
`Media\Personal`, `Media\Communal`, `Media\Pending-Segmentation` and
`Media\NoDate`, so neither path existed.

`os.walk` on a missing directory does not raise. It yields nothing. Both counters
finished at zero, the arithmetic worked, the file wrote successfully, and
`PROGRESS.md` reported a **61,678-file, 646.2 GB library as 0 files** under a
header promising the opposite. It stayed that way for two days, through a
session that read it.

The repo's own copy had a different version of the same bug, and a comment above
it recording the *previous* time this happened: "Counting the pre-split paths
alone made STATE.json report 1,274 files for a 73,000-file library - and the
audit passed it, because it compared that figure against a count made the same
wrong way."

**The rule.** An absent input is not an empty one. Any walk, glob or scan over a
path that is supposed to hold something must assert the path exists before
counting, and fail loudly when it does not. `paths.py` exists so a rename is one
edit; a script that hardcodes tree names off a root imported from `paths.py` gets
the worst of both - it survives the rename and reports nothing.

**The tell.** A generated figure that is exactly zero. Zero is what a broken
counter and an empty directory look like from the outside, and only one of them
is worth believing.

---

## 35. The cheap model was not less accurate, it had one answer

A bake-off across five vision models scored each on agreement with the labels
already in the store. GPT-5 nano came back at **49% agreement for 1/12th of the
price** - a figure that reads like a tolerable trade, and one a cost table would
have made irresistible.

The run printed that percentage and kept nothing else. Recording each verdict
showed what the other 51% actually was. On a sample stratified at 50 files each
of photo, document, screenshot, graphic, meme and poster, nano answered
**"photo" for 162 of 300 files** - in a set that is 17% photographs. It scored
50/50 on photos by saying "photo" to almost everything, and would have filed
**97 of 200 non-memories - screenshots, memes, documents, graphics - into the
personal chronology as photographs.**

The saving was $3.50 against $16. The cost was the single outcome this project
exists to prevent.

**The rule.** An aggregate agreement score cannot distinguish a model that is
somewhat wrong from a model that is degenerate, and the degenerate one scores
*better* on whichever class it collapses to. Never choose a classifier on a
scalar. Keep the per-item verdicts, build the confusion matrix, and look at which
direction the errors run - a model that only over-calls the class you are trying
to *exclude* is worse than its score, and a model that corrects old labels is
better than its score.

**The tell.** A model whose recall on one class is perfect while everything else
degrades. Also: a benchmark run that costs real money and writes only a summary
- when it was killed before printing that summary, it left nothing at all.

---

## 36. Two files, one name, one exact byte count, different content

`Archive\` and `ContentProduction\` were missing from `INDEX_ROOTS`, and
`ingest_tree --dest-root` writes into both, so nothing deduplicating the library
ever looked there. Four videos turned up held twice - once in
`ContentProduction\2026\` and once in the chronology - matching on name and on
size exactly.

Learning 28 says check the inode before believing a duplicate count, so that was
done first: four separate inodes, 22.09 GB of real disk. Then the whole-file
hashes, because the rule is that a duplicate may only be declared on a content
match:

    20260205_161023.mp4   6.8 GB   IDENTICAL
    20260305_132059.mp4   4.3 GB   IDENTICAL
    20260305_133914.mp4   4.2 GB   IDENTICAL
    20260205_165928.mp4   7.4 GB   DIFFERENT   8833730743a6df7f / d7eaef8dd2f5ae60

**Three of four were duplicates. The fourth is 7.4 GB of unique footage wearing
an identical name and an identical size.** Not a near-match: 7,736,000,000-odd
bytes agreeing to the byte while the content does not. Any pass that had deduped
on `(name, size)` - which is the cheap check every one of these tools reaches for
first, and which `ingest_folder` uses as its fast path - would have deleted it and
reported a clean 22.09 GB reclaimed.

**The rule.** Size is a filter, never a verdict, and adding the filename to it
adds nothing: two exports of the same source clip from the same tool at the same
settings collide on both. The reclaim figure is the hash-confirmed subset -
14.88 GB here, not 22.09 - and the gap between those two numbers is the whole
lesson.

**The tell.** A duplicate set whose members all come from the same device on the
same day. That is precisely when a naming scheme and an encoder will produce
identical metadata for different moments.

---

## 37. Two models agreeing is correlated error, not evidence

A bake-off scored five vision models against each other. Because scoring any of
them against the labels already in the store meant asking Haiku how often it
agrees with itself, the reference was rebuilt per file from the majority of the
OTHER models - leave-one-out consensus. It was a real improvement on the
circular version, and it was reported with the right caveat attached: *"a
majority vote among models favours whatever those models share, so it is
evidence and not ground truth."*

Then it was used as though it were ground truth anyway. The session reported
that **40 of 300 stored labels were wrong, "corroborated" because two
independent models diverged from the store and agreed with each other** - most
often `screenshot -> graphic`, 12 of the 40.

Krish looked at the images and said: the screenshots are screenshots.

They were pictures of the London Underground map, transit map tiles, a map
legend. **Both challenger models called them graphics and both were wrong**,
because a screenshot of a map genuinely looks like a graphic. The models share
training data and they share the ambiguity of the image. A third model would
most likely have agreed as well, and made the wrong answer more convincing
rather than less.

Self-reported confidence did not help either. Mean confidence where the two
models agreed: **0.995**. Where they disagreed: **0.984**. Nineteen files out of
7,786 came in under 0.75. The model is not hesitant when it is wrong.

**The rule.** Model agreement measures shared priors, not truth. It is useful for
exactly one thing: *disagreement* is a cheap signal that a human should look.
Agreement is not the complementary signal - it is silence. Errors where models
concur are invisible to any number of additional models, and they are the
dangerous ones precisely because concurrence reads as confirmation. Never let a
model overrule another model on a contested field; carry the disagreement into
the record and let a person settle it. `master_sheet.py` now writes `KindAlt`
and `KindDisputed` rather than picking a winner.

**The tell.** A "corroborated" finding where the corroboration comes from
systems of the same kind. Ask what would have had to be different for them to
disagree - if the answer is "nothing, they see the same thing the same way",
there is one opinion here, not two. The instrument that caught this was a
contact sheet grouped by label, and a human looking at it for ten seconds.

## 38. `-WindowStyle Hidden` hides a window; it does not detach a process

The classifier died at **12:56:00** on 2026-09-12, in the same second the agent
session ended, 53,325 files into 79,017 and four hours into paid work. Both
chains waiting on it died with it. Nothing had crashed and nothing was wrong
with the work — the store on disk was intact and resuming cost only the 25,695
files that were genuinely outstanding.

Every one of those three processes had been launched with:

```powershell
Start-Process pwsh -WindowStyle Hidden -ArgumentList ...
```

which had been treated for days as the way to survive the session, including in
learning 9's advice about the memory watchdog. It is not. `-WindowStyle Hidden`
sets a *window* property. The child stays in the caller's process tree, and when
the session's tree was killed, the tree was killed — hidden or not. The symptom
that made this hard to see is that it *looks* detached: the process keeps running
for hours, has no visible window, and is not a tracked background task. It
survives everything except the one event it was chosen to survive.

**The rule.** If work must outlive the session that started it, hand it to
something that is not the session. On Windows that is the Task Scheduler:

```powershell
pwsh -NoProfile -File scripts\chains\arm.ps1 -Chain <chain>.ps1
```

`scripts/chains/arm.ps1` registers the chain as a scheduled task, so its parent
is `svchost.exe` and it survives the session ending, the terminal closing and
logging out. Verify it rather than trusting it — walk the parents and check that
none of them is the agent:

```powershell
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$pid"   # python
Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)"
```

`python ← pwsh ← svchost.exe` is detached. `python ← pwsh ← ... ← claude.exe` is
not, however hidden the window.

**The tell.** A mechanism chosen for a property nobody ever tested. "Detached"
was inferred from the absence of a window and from jobs surviving the memory
watchdog — a different threat, which it genuinely does survive. The first real
test of the claim was also the first time it cost anything. When something is
load-bearing and untested, test it while the cost of being wrong is still zero:
one `Get-CimInstance` on the parent pid, at any point in those four hours, would
have shown it.
