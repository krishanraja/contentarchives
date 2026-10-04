-- From the Supabase security advisor on first deploy (2026-10-04):
--   extension_in_public            vector lived in `public`
--   function_search_path_mutable   search_photos resolved names via the caller's path
-- Supabase's roles already search `extensions`; the function pins its own path.
create schema if not exists extensions;
alter extension vector set schema extensions;
alter function public.search_photos(extensions.vector, text, text[], text, int, int, int, int)
  set search_path = public, extensions;
