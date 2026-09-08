# Enrichment engine

Point it at any tree of photographs and video. It works out what each file is,
who is in it, and what it shows - and asks a human only the questions a machine
genuinely cannot answer.

Nothing in here is specific to this project's library. The only inputs are a
source folder, a thumbnail cache and a store directory.

---

## Why it exists

Metadata takes you a long way and then stops dead. On a 79,300-file corpus it
gave dates for 59%, GPS for 39%, a device for 41% and an origin folder for
100% - genuinely useful, and the reason the corpus became tractable at all.

Then it left **8,262 files undecidable**, and the reason is worth stating
precisely, because it is what the whole engine is built around:

> `042.jpg` is a toddler in green dinosaur pyjamas being handed a bowl.
> `bharti phone 3034.jpg` is a forwarded Ganesh Utsav flyer with somebody's
> bank details on it.
>
> Both are JPEGs of a couple of hundred KB. Both have no camera EXIF, because
> a messenger stripped it in transit. **No rule separates them.** A vision
> model separates them instantly, and a human separates the people in them.

So: cheap signals first, a small vision model for what they cannot settle, and
a human for what neither can.

---

## The pipeline

```
  thumbnail.py     512px JPEGs, keyed by content hash        local, ~1h/80k
        |
  classify.py      Haiku: kind, subject, people, keep        resumable, costed
        |
  swipe/server.py  a phone asks the human: who, and is this  LAN only
        |
  store.py         every claim, with its source and confidence
```

## Three decisions everything rests on

**1. Content hash, never path.** Paths are where a file sits this week. In this
project alone they have been invalidated by a Personal/Communal split, a rename
of the library root, moving every chronology tree into `Media\`, a D:->H:
mirror and 21,649 deletions. Enrichment keyed on paths would have died at the
first of those, silently. A hash also means a re-import arrives pre-tagged and
two copies collapse to one set of tags.

**2. Every claim carries its source and confidence.** `model:haiku` at 0.6 and
`human` at 1.0 are different kinds of thing. A store that flattens them can
never tell you what still needs asking - which is exactly what the swipe game
needs to know to pick its next question.

**3. Merges are recorded, not applied.** When two people turn out to be one,
person B is marked `merged_into:A`. Nothing is rewritten. Face merges are
sometimes wrong, and this way a mistake is one row to reverse.

---

## Cost, honestly

Vision cost scales with **pixel dimensions**, so the thumbnail pass is the
single biggest lever - far bigger than the choice of model. Sending originals
would multiply the bill several times over and classify no better.

At ~1,200 input tokens per 512px image, 79,300 files is roughly **95 million
tokens**. Use the cheap model: this is classification, not reasoning, and a
small model does it as well as a large one. `classify.py` prints measured
tokens per 1,000 files after every run, so the decision to continue is made on
a number rather than an estimate.

Reserve the strong model (`--strong`) for face identity and for the residue
that comes back uncertain.

---

## Privacy: this stays on the machine

The store holds the identities of a family, including children, joined to
photographs of them. The swipe server binds to the LAN so a phone on the same
wifi can reach it. **Do not port-forward it and do not publish it.** The same
rule that keeps the per-file map off a public repo applies here with more force.

---

## Usage

```bash
python thumbnail.py --source "D:\ContentLibrary" --out "D:\_thumbs"

set ANTHROPIC_API_KEY=...
python classify.py --thumbs "D:\_thumbs" --store "D:\_enrichment" --limit 200

python swipe/server.py --store "D:\_enrichment" --thumbs "D:\_thumbs"
```

`--limit` runs a costed tranche. Everything is resumable: the store records what
has been done and the next run skips it, so a batch killed by a watchdog, a
dropped connection or a closed laptop lid costs nothing already paid for.
