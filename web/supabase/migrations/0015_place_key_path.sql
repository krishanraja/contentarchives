-- 0015: place_key (0014) runs with a fixed search_path, as every other
-- function here does (the Supabase security advisor, 2026-10-12, on the new
-- London database).
alter function place_key(text) set search_path = public;
