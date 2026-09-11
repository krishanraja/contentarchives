"""What does the enrichment store actually contain right now?"""
import csv, collections, os

S = r"D:\_enrichment\content_tags.csv"
rows = list(csv.reader(open(S, encoding="utf-8", errors="replace")))
print("header:", rows[0])
print(f"rows: {len(rows)-1:,}")

by = collections.defaultdict(collections.Counter)
hashes = set()
kind_of, ppl_of = {}, {}
for r in rows[1:]:
    if len(r) < 3:
        continue
    hashes.add(r[0])
    by[r[1]][r[2]] += 1
    if r[1] == "kind":
        kind_of[r[0]] = r[2]
    elif r[1] == "people_count":
        ppl_of[r[0]] = r[2]

print(f"distinct hashes classified: {len(hashes):,}")
for k in ("kind", "keep"):
    print(f"-- {k}: {dict(by[k].most_common())}")
pc = by["people_count"]
print(f"-- files with >=1 person: "
      f"{sum(v for k, v in pc.items() if k.isdigit() and int(k) > 0):,}")

pwp = sum(1 for h, k in kind_of.items()
          if k == "photo" and ppl_of.get(h, "0").isdigit() and int(ppl_of[h]) > 0)
print(f"-- kind=photo AND people>=1: {pwp:,}")

print(f"thumbs on disk: {sum(len(f) for _, _, f in os.walk(r'D:\_thumbs')):,}")
