r"""Score every model against a reference it did not write.

Agreement in bakeoff.py is measured against the labels already in the store, and
those labels are Haiku's. That makes Haiku's score meaningless by construction -
it is being asked how often it agrees with itself - and it quietly flatters
whatever model most resembles Haiku.

So: build the reference by majority vote of the OTHER models on each file,
leaving out the model being scored. A label two independent models agree on is
not truth, but it is evidence that does not come from the model on trial.
"""
import csv, collections, sys

ROWS = [r for r in csv.DictReader(
    open(r'D:\_enrichment\bakeoff-verdicts.csv', newline='', encoding='utf-8'))]

# latest run per model
latest = {}
for r in ROWS:
    m = r['model']
    if m not in latest or r['run'] > latest[m]:
        latest[m] = r['run']
by = collections.defaultdict(dict)
for r in ROWS:
    if r['run'] == latest[r['model']]:
        by[r['model']][r['hash']] = r
models = sorted(by)
print('models:', {m: len(by[m]) for m in models})

files = set.intersection(*(set(by[m]) for m in models))
print('files all models judged:', len(files))
print()

NONMEM = ('document', 'screenshot', 'graphic', 'meme')

def consensus(h, exclude):
    votes = collections.Counter(by[m][h]['model_kind'] for m in models
                                if m != exclude and h in by[m])
    if not votes:
        return None
    top, n = votes.most_common(1)[0]
    return top if n >= 2 else None       # a lone voice is not a reference

print('scored against the majority of the OTHER models (leave-one-out):')
print('%-16s%12s%14s%28s' % ('model', 'agreement', 'n', 'non-memories called photo'))
for m in models:
    ok = tot = 0
    bad = nm = 0
    for h in files:
        c = consensus(h, m)
        if c is None:
            continue
        mine = by[m][h]['model_kind']
        tot += 1
        ok += mine == c
        if c in NONMEM:
            nm += 1
            bad += mine == 'photo'
    print('%-16s%11.1f%%%14d%20s' % (m, 100*ok/max(tot,1), tot,
          '%d of %d (%.0f%%)' % (bad, nm, 100*bad/max(nm,1))))

print()
print('and the stored labels themselves, scored the same way:')
ok = tot = bad = nm = 0
for h in files:
    votes = collections.Counter(by[m][h]['model_kind'] for m in models
                                if m != 'haiku')
    top, n = votes.most_common(1)[0]
    if n < 2:
        continue
    stored = by[models[0]][h]['stored_kind']
    tot += 1
    ok += stored == top
    if top in NONMEM:
        nm += 1
        bad += stored == 'photo'
print('%-16s%11.1f%%%14d%20s' % ('stored (haiku)', 100*ok/max(tot,1), tot,
      '%d of %d (%.0f%%)' % (bad, nm, 100*bad/max(nm,1))))
