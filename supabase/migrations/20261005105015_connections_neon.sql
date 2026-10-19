alter table public.connections drop constraint connections_kind_check;
alter table public.connections add constraint connections_kind_check
  check (kind in ('postgresql', 'supabase', 'neon', 'sqlserver', 'mysql', 'sqlite', 'csv', 'parquet'));
