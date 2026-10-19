create function public.can_edit(workspace uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(public.role_in(workspace) in ('owner', 'admin', 'approver', 'member'), false)
$$;

create table public.connections (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 64),
  kind text not null check (kind in ('postgresql', 'supabase', 'sqlserver', 'mysql', 'sqlite', 'csv', 'parquet')),
  environment text not null,
  definition jsonb not null default '{}' check (
    jsonb_typeof(definition) = 'object'
    and not definition ?| array['password', 'secret', 'sshSecret', 'sshPassword', 'token']
  ),
  created_by uuid references auth.users on delete set null default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, name)
);

create index connections_workspace on public.connections (workspace_id);

create function public.connection_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    perform public.record(old.workspace_id, 'connection.removed', jsonb_build_object('name', old.name));
    return old;
  end if;
  new.updated_at := now();
  perform public.record(
    new.workspace_id,
    case when tg_op = 'INSERT' then 'connection.created' else 'connection.changed' end,
    jsonb_build_object('name', new.name)
  );
  return new;
end
$$;

create trigger connection_changed before insert or update or delete on public.connections
for each row execute function public.connection_changed();

alter table public.connections enable row level security;

create policy "members see their workspace's connections" on public.connections for select to authenticated
using (public.role_in(workspace_id) is not null);
create policy "editors add connections" on public.connections for insert to authenticated
with check (public.can_edit(workspace_id));
create policy "editors change connections" on public.connections for update to authenticated
using (public.can_edit(workspace_id)) with check (public.can_edit(workspace_id));
create policy "editors remove connections" on public.connections for delete to authenticated
using (public.can_edit(workspace_id));

revoke all on function public.connection_changed() from public, anon, authenticated;
revoke all on public.connections from anon, authenticated;
grant select, delete on public.connections to authenticated;
grant insert (workspace_id, name, kind, environment, definition) on public.connections to authenticated;
grant update (name, environment, definition) on public.connections to authenticated;
