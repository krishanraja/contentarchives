-- 0020: the owner's "the same person, spelled this way" counts every vote
-- (Krish, 2026-10-23, putting right two misspellings and one second name a
-- relative gave).
--
-- 0018 put a spelling right by adding the owner's own answer under the right
-- spelling. That is enough when the wrong spelling was his; when a relative
-- gave it, his answer only TIES with theirs (0007: each person's latest answer
-- is one vote, and two spellings that fold differently are two answers), so
-- the face showed the first name given - the wrong one - and went back to the
-- family as contested.
--
-- Now a 'same' verdict in spelling_verdicts maps a vote's spelling before it
-- is counted: a vote for either spelling is a vote for the one kept. Nobody's
-- answer is edited (answers stays insert-only, and the journal on the PC still
-- carries what each person actually said); only the count reads through the
-- verdict.

create or replace view group_votes with (security_invoker = true) as
with wm as (select coalesce(max(watermark), 'epoch'::timestamptz) as t from snapshots where kind = 'seed'),
latest as (
  select distinct on (c.group_id, a.who) c.group_id, a.who, a.field, a.value, a.at
  from answers a
  join clusters c on c.cluster_id = a.target, wm
  where a.scope = 'cluster' and a.status in ('new', 'ingested') and a.at > wm.t
  order by c.group_id, a.who, a.at desc
),
spelled as (
  select l.group_id, l.who, l.field, l.at,
         case when l.field = 'person' then coalesce((
           select s.kept from spelling_verdicts s
           where s.verdict = 'same' and name_key(l.value) in (s.a_key, s.b_key)
           order by s.at desc limit 1), l.value) else l.value end as value
  from latest l
)
select group_id, who, field, value, at,
       case when field = 'person' then name_key(value)
            when field = 'unidentifiable' then '#unidentifiable' end as k
from spelled;
