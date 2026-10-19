create table public.migrations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces on delete cascade,
  source_id uuid references public.connections on delete set null,
  target_id uuid references public.connections on delete set null,
  source_name text not null check (char_length(source_name) between 1 and 64),
  target_name text not null check (char_length(target_name) between 1 and 64),
  target_environment text not null,
  mappings jsonb not null check (
    jsonb_typeof(mappings) = 'array'
    and not jsonb_path_exists(mappings, '$[*] ? (exists(@.source_scope) || exists(@.business_rules))')
  ),
  anonymized boolean not null,
  subset_table text,
  subset_limit integer check (subset_limit > 0),
  run_id text check (run_id ~ '^[A-Za-z0-9_-]{1,64}$'),
  status text not null default 'running' check (status in ('running', 'verified', 'review', 'failed')),
  rows bigint check (rows >= 0),
  findings integer check (findings >= 0),
  tables jsonb not null default '[]' check (
    jsonb_typeof(tables) = 'array'
    and not jsonb_path_exists(tables, '$[*].keyvalue() ? (!(@.key like_regex "^(entity|table|rows|passed|review|fail|accepted)$"))')
  ),
  created_by uuid references auth.users on delete set null default auth.uid(),
  created_at timestamptz not null default now(),
  finished_at timestamptz
);

create index migrations_workspace on public.migrations (workspace_id, created_at desc);

create function public.migration_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if exists (select 1 from public.connections c
               where c.id in (new.source_id, new.target_id) and c.workspace_id <> new.workspace_id) then
      raise exception 'a migration runs between connections of its own workspace' using errcode = '42501';
    end if;
    perform public.record(new.workspace_id, 'migration.started',
      jsonb_build_object('source', new.source_name, 'target', new.target_name, 'anonymized', new.anonymized));
  elsif new.status is distinct from old.status then
    new.finished_at := now();
    perform public.record(new.workspace_id, 'migration.' || new.status,
      jsonb_build_object('source', new.source_name, 'target', new.target_name, 'rows', new.rows, 'findings', new.findings));
  end if;
  return new;
end
$$;

create trigger migration_changed before insert or update on public.migrations
for each row execute function public.migration_changed();

alter table public.migrations enable row level security;

create policy "members see their workspace's migrations" on public.migrations for select to authenticated
using (public.role_in(workspace_id) is not null);
create policy "editors start migrations" on public.migrations for insert to authenticated
with check (public.can_edit(workspace_id) and status = 'running');
create policy "whoever started a migration records its outcome" on public.migrations for update to authenticated
using (created_by = auth.uid() and status = 'running' and public.can_edit(workspace_id))
with check (created_by = auth.uid() and public.can_edit(workspace_id));

revoke all on function public.migration_changed() from public, anon, authenticated;
revoke all on public.migrations from anon, authenticated;
grant select on public.migrations to authenticated;
grant insert (workspace_id, source_id, target_id, source_name, target_name, target_environment, mappings,
  anonymized, subset_table, subset_limit) on public.migrations to authenticated;
grant update (status, rows, findings, tables, run_id) on public.migrations to authenticated;
