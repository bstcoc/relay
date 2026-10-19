create type public.role as enum ('owner', 'admin', 'approver', 'member', 'viewer');

create table public.profiles (
  user_id uuid primary key references auth.users on delete cascade,
  display_name text not null default '',
  avatar_url text,
  created_at timestamptz not null default now()
);

create table public.companies (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(btrim(name)) between 1 and 64),
  created_by uuid not null references auth.users,
  created_at timestamptz not null default now()
);

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 64),
  created_at timestamptz not null default now()
);

create table public.members (
  workspace_id uuid not null references public.workspaces on delete cascade,
  user_id uuid not null references auth.users on delete cascade,
  role public.role not null default 'member',
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

create table public.invitations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces on delete cascade,
  email text not null check (email ~ '^[^@\s]+@[^@\s]+$'),
  role public.role not null default 'member' check (role <> 'owner'),
  invited_by uuid not null references auth.users,
  created_at timestamptz not null default now(),
  accepted_at timestamptz,
  unique (workspace_id, email)
);

create table public.audit_log (
  id bigint generated always as identity primary key,
  workspace_id uuid not null references public.workspaces on delete cascade,
  actor uuid references auth.users on delete set null,
  action text not null,
  detail jsonb not null default '{}',
  at timestamptz not null default now()
);

create index members_user on public.members (user_id);
create index invitations_email on public.invitations (lower(email)) where accepted_at is null;
create index audit_log_workspace on public.audit_log (workspace_id, at desc);

create function public.role_in(workspace uuid) returns public.role
language sql stable security definer set search_path = '' as $$
  select m.role from public.members m where m.workspace_id = workspace and m.user_id = auth.uid()
$$;

create function public.is_admin(workspace uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(public.role_in(workspace) in ('owner', 'admin'), false)
$$;

create function public.shares_workspace(other uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.members mine join public.members theirs using (workspace_id)
    where mine.user_id = auth.uid() and theirs.user_id = other
  )
$$;

create function public.record(workspace uuid, what text, details jsonb default '{}') returns void
language sql security definer set search_path = '' as $$
  insert into public.audit_log (workspace_id, actor, action, detail) values (workspace, auth.uid(), what, details)
$$;

create function public.create_company(company_name text, workspace_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  company uuid;
  workspace uuid;
begin
  if auth.uid() is null then
    raise exception 'sign in first' using errcode = '42501';
  end if;
  insert into public.companies (name, created_by) values (btrim(company_name), auth.uid()) returning id into company;
  insert into public.workspaces (company_id, name) values (company, btrim(workspace_name)) returning id into workspace;
  insert into public.members (workspace_id, user_id, role) values (workspace, auth.uid(), 'owner');
  perform public.record(workspace, 'company.created', jsonb_build_object('company', company_name, 'workspace', workspace_name));
  return workspace;
end
$$;

create function public.create_workspace(company uuid, workspace_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  workspace uuid;
begin
  if not exists (
    select 1 from public.members m join public.workspaces w on w.id = m.workspace_id
    where w.company_id = company and m.user_id = auth.uid() and m.role in ('owner', 'admin')
  ) then
    raise exception 'only an owner or an admin of the company can add a workspace' using errcode = '42501';
  end if;
  insert into public.workspaces (company_id, name) values (company, btrim(workspace_name)) returning id into workspace;
  insert into public.members (workspace_id, user_id, role) values (workspace, auth.uid(), 'owner');
  perform public.record(workspace, 'workspace.created', jsonb_build_object('workspace', workspace_name));
  return workspace;
end
$$;

create function public.invite(workspace uuid, address text, given public.role default 'member') returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  invitation uuid;
begin
  if not public.is_admin(workspace) then
    raise exception 'only an owner or an admin can invite' using errcode = '42501';
  end if;
  insert into public.invitations (workspace_id, email, role, invited_by)
  values (workspace, lower(btrim(address)), given, auth.uid())
  on conflict (workspace_id, email) do update set role = excluded.role, invited_by = excluded.invited_by
  returning id into invitation;
  perform public.record(workspace, 'member.invited', jsonb_build_object('email', lower(btrim(address)), 'role', given));
  return invitation;
end
$$;

create function public.accept_invitation(invitation uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  pending public.invitations;
begin
  select * into pending from public.invitations
  where id = invitation and accepted_at is null and email = lower(auth.jwt() ->> 'email');
  if pending.id is null then
    raise exception 'no pending invitation for this account' using errcode = '42501';
  end if;
  insert into public.members (workspace_id, user_id, role) values (pending.workspace_id, auth.uid(), pending.role)
  on conflict (workspace_id, user_id) do nothing;
  update public.invitations set accepted_at = now() where id = invitation;
  perform public.record(pending.workspace_id, 'member.joined', jsonb_build_object('role', pending.role));
  return pending.workspace_id;
end
$$;

create function public.set_role(workspace uuid, member uuid, given public.role) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_admin(workspace) then
    raise exception 'only an owner or an admin can change a role' using errcode = '42501';
  end if;
  if given = 'owner' or (select role from public.members where workspace_id = workspace and user_id = member) = 'owner' then
    raise exception 'the owner role cannot be given or taken here' using errcode = '42501';
  end if;
  update public.members set role = given where workspace_id = workspace and user_id = member;
  perform public.record(workspace, 'member.role_changed', jsonb_build_object('member', member, 'role', given));
end
$$;

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (user_id, display_name, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', split_part(new.email, '@', 1), ''),
    new.raw_user_meta_data ->> 'avatar_url'
  );
  return new;
end
$$;

create trigger on_auth_user_created after insert on auth.users
for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.companies enable row level security;
alter table public.workspaces enable row level security;
alter table public.members enable row level security;
alter table public.invitations enable row level security;
alter table public.audit_log enable row level security;

create policy "see own and teammates' profiles" on public.profiles for select to authenticated
using (user_id = (select auth.uid()) or public.shares_workspace(user_id));
create policy "edit own profile" on public.profiles for update to authenticated
using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "see companies one works in" on public.companies for select to authenticated
using (exists (select 1 from public.workspaces w where w.company_id = companies.id and public.role_in(w.id) is not null));

create policy "see workspaces one belongs to" on public.workspaces for select to authenticated
using (public.role_in(id) is not null);
create policy "admins rename a workspace" on public.workspaces for update to authenticated
using (public.is_admin(id)) with check (public.is_admin(id));

create policy "see members of one's workspaces" on public.members for select to authenticated
using (public.role_in(workspace_id) is not null);
create policy "admins remove members, members leave" on public.members for delete to authenticated
using (role <> 'owner' and (public.is_admin(workspace_id) or user_id = (select auth.uid())));

create policy "admins and invitees see invitations" on public.invitations for select to authenticated
using (public.is_admin(workspace_id) or email = lower((select auth.jwt()) ->> 'email'));
create policy "admins withdraw invitations" on public.invitations for delete to authenticated
using (public.is_admin(workspace_id));

create policy "members read the audit log" on public.audit_log for select to authenticated
using (public.role_in(workspace_id) is not null);

revoke all on function public.record(uuid, text, jsonb) from public, anon, authenticated;
revoke all on function public.handle_new_user() from public, anon, authenticated;
revoke all on function public.create_company(text, text) from public, anon;
revoke all on function public.create_workspace(uuid, text) from public, anon;
revoke all on function public.invite(uuid, text, public.role) from public, anon;
revoke all on function public.accept_invitation(uuid) from public, anon;
revoke all on function public.set_role(uuid, uuid, public.role) from public, anon;
grant execute on function public.create_company(text, text) to authenticated;
grant execute on function public.create_workspace(uuid, text) to authenticated;
grant execute on function public.invite(uuid, text, public.role) to authenticated;
grant execute on function public.accept_invitation(uuid) to authenticated;
grant execute on function public.set_role(uuid, uuid, public.role) to authenticated;

revoke all on public.profiles, public.companies, public.workspaces, public.members, public.invitations, public.audit_log
from anon, authenticated;
grant select on public.profiles, public.companies, public.workspaces, public.members, public.invitations, public.audit_log
to authenticated;
grant update (display_name, avatar_url) on public.profiles to authenticated;
grant update (name) on public.workspaces to authenticated;
grant delete on public.members, public.invitations to authenticated;
