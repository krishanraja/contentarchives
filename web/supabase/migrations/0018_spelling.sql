-- 0018: a name spelled two ways can be put right once, everywhere (Krish,
-- 2026-10-21, on a child's name saved with one letter wrong: "How do we
-- handle accidental misspellings?").
--
-- The app already folds case and spacing (name_key, 0007) and asks "Did you
-- mean ...?" when a typed name is one slip from a known one. What it could not
-- do is put right a spelling already saved: the wrong one came from the PC
-- naming tool, before that check existed, and sat beside the right one as a
-- second person.
--
-- The fix is written as ANSWERS, never as edits (answers stays insert-only, and
-- the PC bridge carries every answer into the journal):
--   * each face group named the wrong way gets the owner's own answer with the
--     right spelling - his newer vote replaces his older one (group_votes);
--   * each photograph the library itself lists under the wrong spelling gets
--     "not in it: wrong" and "in it: right" (photo_people, 0012).
-- A relative's own vote is never rewritten on their behalf.
--
-- spelling_verdicts keeps what the owner decided about each pair the screen
-- showed him, so a pair he has looked at is not asked again: "same" (and
-- which spelling he kept) or "different" (two people, Asha and Isha).
-- The keys are name_key()s, the smaller first.

create table if not exists spelling_verdicts (
  a_key   text not null,
  b_key   text not null,
  verdict text not null check (verdict in ('same', 'different')),
  kept    text,                                   -- the spelling kept, for 'same'
  who     text not null,
  at      timestamptz not null default now(),
  primary key (a_key, b_key),
  check (a_key < b_key),
  check ((verdict = 'same') = (kept is not null))
);

alter table spelling_verdicts enable row level security;
revoke all on spelling_verdicts from anon, authenticated;
