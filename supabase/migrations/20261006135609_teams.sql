drop policy "a team reads its licenses" on public.licenses;
drop table public.licenses;

drop policy "members read the audit log" on public.audit_log;
drop policy "see companies one works in" on public.companies;
drop policy "editors add connections" on public.connections;
drop policy "editors change connections" on public.connections;
drop policy "editors remove connections" on public.connections;
drop policy "members see their workspace's connections" on public.connections;
drop policy "admins and invitees see invitations" on public.invitations;
drop policy "admins withdraw invitations" on public.invitations;
drop policy "admins remove members, members leave" on public.members;
drop policy "see members of one's workspaces" on public.members;
drop policy "editors start migrations" on public.migrations;
drop policy "members see their workspace's migrations" on public.migrations;
drop policy "whoever started a migration records its outcome" on public.migrations;
drop policy "see own and teammates' profiles" on public.profiles;
drop policy "admins rename a workspace" on public.workspaces;
drop policy "invitees see the workspace they are invited to" on public.workspaces;
drop policy "see workspaces one belongs to" on public.workspaces;
drop policy "upload one's own avatars" on storage.objects;
drop policy "remove one's own avatars" on storage.objects;

drop function public.create_company(text, text);
drop function public.create_workspace(uuid, text);
drop function public.set_workspace_avatar(uuid, text);
drop function public.set_avatar(text);
drop function public.owns_avatar_folder(text);
drop function public.invite(uuid, text, public.role);
drop function public.accept_invitation(uuid);
drop function public.set_role(uuid, uuid, public.role);
drop function public.invited_to(uuid);
drop function public.shares_workspace(uuid);
drop function public.can_edit(uuid);
drop function public.is_admin(uuid);
drop function public.role_in(uuid);
drop trigger connection_changed on public.connections;
drop trigger migration_changed on public.migrations;
drop function public.connection_changed();
drop function public.migration_changed();
drop function public.record(uuid, text, jsonb);

alter table public.workspaces rename to teams;
update public.teams t set name = left(c.name || case
    when (select count(*) from public.teams other where other.company_id = t.company_id) > 1 then ' · ' || t.name
    else '' end, 64)
from public.companies c where c.id = t.company_id;
update public.teams set avatar_path = null where avatar_path is not null;
alter table public.teams drop column company_id;
drop table public.companies;

alter table public.members rename column workspace_id to team_id;
alter table public.invitations rename column workspace_id to team_id;
alter table public.audit_log rename column workspace_id to team_id;
alter table public.connections rename column workspace_id to team_id;
alter table public.migrations rename column workspace_id to team_id;
alter index public.audit_log_workspace rename to audit_log_team;
delete from public.audit_log where action = 'company.created';
update public.audit_log set action = replace(action, 'workspace.', 'team.') where action like 'workspace.%';
alter index public.connections_workspace rename to connections_team;

alter table public.teams
  add column plan text not null default 'trial' check (plan in ('trial', 'pro')),
  add column trial_ends_at timestamptz not null default now() + interval '14 days',
  add column paid_until timestamptz,
  add column seats integer check (seats > 0),
  add column stripe_customer text unique,
  add column stripe_subscription text unique;

create function public.role_in(team uuid) returns public.role
language sql stable security definer set search_path = '' as $$
  select m.role from public.members m
  where m.team_id = team and m.user_id = auth.uid() and public.verified()
$$;

create function public.is_admin(team uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(public.role_in(team) in ('owner', 'admin'), false)
$$;

create function public.can_edit(team uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(public.role_in(team) in ('owner', 'admin', 'approver', 'member'), false)
$$;

create function public.invited_to(team uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.invitations i
    where i.team_id = team and i.accepted_at is null and i.email = public.confirmed_email()
  )
$$;

create function public.shares_team(other uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.verified() and exists (
    select 1 from public.members mine join public.members theirs using (team_id)
    where mine.user_id = auth.uid() and theirs.user_id = other
  )
$$;

create function public.record(team uuid, what text, details jsonb default '{}') returns void
language sql security definer set search_path = '' as $$
  insert into public.audit_log (team_id, actor, action, detail) values (team, auth.uid(), what, details)
$$;

create function public.create_team(team_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  team uuid;
begin
  if auth.uid() is null or not public.verified() then
    raise exception 'sign in first' using errcode = '42501';
  end if;
  perform pg_advisory_xact_lock(hashtext(auth.uid()::text));
  insert into public.teams (name, trial_ends_at)
  values (btrim(team_name), case
    when exists (select 1 from public.members m where m.user_id = auth.uid() and m.role = 'owner') then now()
    else now() + interval '14 days'
  end)
  returning id into team;
  insert into public.members (team_id, user_id, role) values (team, auth.uid(), 'owner');
  perform public.record(team, 'team.created', jsonb_build_object('team', btrim(team_name)));
  return team;
end
$$;

create function public.invite(team uuid, address text, given public.role default 'member') returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  invitation uuid;
begin
  if not public.is_admin(team) then
    raise exception 'only an owner or an admin can invite' using errcode = '42501';
  end if;
  insert into public.invitations (team_id, email, role, invited_by)
  values (team, lower(btrim(address)), given, auth.uid())
  on conflict (team_id, email)
  do update set role = excluded.role, invited_by = excluded.invited_by, created_at = now(), accepted_at = null
  returning id into invitation;
  perform public.record(team, 'member.invited', jsonb_build_object('email', lower(btrim(address)), 'role', given));
  return invitation;
end
$$;

create function public.accept_invitation(invitation uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  pending public.invitations;
begin
  select * into pending from public.invitations
  where id = invitation and accepted_at is null and email = public.confirmed_email();
  if pending.id is null then
    raise exception 'no pending invitation for this account' using errcode = '42501';
  end if;
  insert into public.members (team_id, user_id, role) values (pending.team_id, auth.uid(), pending.role)
  on conflict (team_id, user_id) do nothing;
  update public.invitations set accepted_at = now() where id = invitation;
  perform public.record(pending.team_id, 'member.joined', jsonb_build_object('role', pending.role));
  return pending.team_id;
end
$$;

create function public.set_role(team uuid, member uuid, given public.role) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_admin(team) then
    raise exception 'only an owner or an admin can change a role' using errcode = '42501';
  end if;
  if given = 'owner' or (select role from public.members where team_id = team and user_id = member) = 'owner' then
    raise exception 'the owner role cannot be given or taken here' using errcode = '42501';
  end if;
  update public.members set role = given where team_id = team and user_id = member;
  perform public.record(team, 'member.role_changed', jsonb_build_object('member', member, 'role', given));
end
$$;

create function public.owns_avatar_folder(object_name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select object_name ~ '^(users|teams)/[0-9a-f-]{36}/[0-9a-f-]{36}\.(webp|png)$' and case split_part(object_name, '/', 1)
    when 'users' then split_part(object_name, '/', 2) = (select auth.uid())::text and public.verified()
    when 'teams' then public.is_admin(split_part(object_name, '/', 2)::uuid)
    else false
  end
$$;

create function public.set_avatar(path text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if path is not null and not (
    split_part(path, '/', 1) = 'users' and public.owns_avatar_folder(path)
    and exists (select 1 from storage.objects o where o.bucket_id = 'avatars' and o.name = path)
  ) then
    raise exception 'this picture is not one of your uploads' using errcode = '42501';
  end if;
  update public.profiles set avatar_path = path where user_id = auth.uid();
end
$$;

create function public.set_team_avatar(team uuid, path text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_admin(team) then
    raise exception 'only an admin changes the team picture' using errcode = '42501';
  end if;
  if path is not null and not (
    split_part(path, '/', 1) = 'teams' and split_part(path, '/', 2) = team::text
    and exists (select 1 from storage.objects o where o.bucket_id = 'avatars' and o.name = path)
  ) then
    raise exception 'this picture is not one of this team''s uploads' using errcode = '42501';
  end if;
  update public.teams set avatar_path = path where id = team;
  perform public.record(team, 'team.avatar', '{}');
end
$$;

create function public.connection_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    perform public.record(old.team_id, 'connection.removed', jsonb_build_object('name', old.name));
    return old;
  end if;
  new.updated_at := now();
  perform public.record(
    new.team_id,
    case when tg_op = 'INSERT' then 'connection.created' else 'connection.changed' end,
    jsonb_build_object('name', new.name)
  );
  return new;
end
$$;

create function public.migration_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  source public.connections;
  target public.connections;
begin
  if tg_op = 'INSERT' then
    select * into source from public.connections where id = new.source_id and team_id = new.team_id;
    select * into target from public.connections where id = new.target_id and team_id = new.team_id;
    if source.id is null or target.id is null or source.id = target.id then
      raise exception 'a migration runs between two connections of its own team' using errcode = '42501';
    end if;
    new.source_name := source.name;
    new.target_name := target.name;
    new.target_environment := target.environment;
    perform public.record(new.team_id, 'migration.started',
      jsonb_build_object('source', new.source_name, 'target', new.target_name, 'anonymized', new.anonymized));
  elsif new.status is distinct from old.status then
    new.finished_at := now();
    perform public.record(new.team_id, 'migration.' || new.status,
      jsonb_build_object('source', new.source_name, 'target', new.target_name, 'rows', new.rows, 'findings', new.findings));
  end if;
  return new;
end
$$;

create trigger connection_changed before insert or update or delete on public.connections
for each row execute function public.connection_changed();
create trigger migration_changed before insert or update on public.migrations
for each row execute function public.migration_changed();

create policy "see teams one belongs to" on public.teams for select to authenticated
using (public.role_in(id) is not null);
create policy "invitees see the team they are invited to" on public.teams for select to authenticated
using (public.invited_to(id));
create policy "admins rename a team" on public.teams for update to authenticated
using (public.is_admin(id)) with check (public.is_admin(id));

create policy "see members of one's teams" on public.members for select to authenticated
using (public.role_in(team_id) is not null);
create policy "admins remove members, members leave" on public.members for delete to authenticated
using (role <> 'owner' and (public.is_admin(team_id) or user_id = (select auth.uid())));

create policy "admins and invitees see invitations" on public.invitations for select to authenticated
using (public.is_admin(team_id) or email = public.confirmed_email());
create policy "admins withdraw invitations" on public.invitations for delete to authenticated
using (public.is_admin(team_id));

create policy "members read the audit log" on public.audit_log for select to authenticated
using (public.role_in(team_id) is not null);

create policy "see own and teammates' profiles" on public.profiles for select to authenticated
using ((user_id = (select auth.uid()) and (select public.verified())) or public.shares_team(user_id));

create policy "members see their team's connections" on public.connections for select to authenticated
using (public.role_in(team_id) is not null);
create policy "editors add connections" on public.connections for insert to authenticated
with check (public.can_edit(team_id));
create policy "editors change connections" on public.connections for update to authenticated
using (public.can_edit(team_id)) with check (public.can_edit(team_id));
create policy "editors remove connections" on public.connections for delete to authenticated
using (public.can_edit(team_id));

create policy "members see their team's migrations" on public.migrations for select to authenticated
using (public.role_in(team_id) is not null);
create policy "editors start migrations" on public.migrations for insert to authenticated
with check (public.can_edit(team_id) and status = 'running');
create policy "whoever started a migration records its outcome" on public.migrations for update to authenticated
using (created_by = (select auth.uid()) and status = 'running' and public.can_edit(team_id))
with check (created_by = (select auth.uid()) and public.can_edit(team_id));

create policy "upload one's own avatars" on storage.objects for insert to authenticated
with check (bucket_id = 'avatars' and public.owns_avatar_folder(name));
create policy "remove one's own avatars" on storage.objects for delete to authenticated
using (bucket_id = 'avatars' and public.owns_avatar_folder(name));

revoke all on function public.record(uuid, text, jsonb) from public, anon, authenticated;
revoke all on function public.connection_changed() from public, anon, authenticated;
revoke all on function public.migration_changed() from public, anon, authenticated;
revoke all on function public.create_team(text) from public, anon;
revoke all on function public.invite(uuid, text, public.role) from public, anon;
revoke all on function public.accept_invitation(uuid) from public, anon;
revoke all on function public.set_role(uuid, uuid, public.role) from public, anon;
revoke all on function public.owns_avatar_folder(text) from public, anon;
revoke all on function public.set_avatar(text) from public, anon;
revoke all on function public.set_team_avatar(uuid, text) from public, anon;
grant execute on function public.create_team(text) to authenticated;
grant execute on function public.invite(uuid, text, public.role) to authenticated;
grant execute on function public.accept_invitation(uuid) to authenticated;
grant execute on function public.set_role(uuid, uuid, public.role) to authenticated;
grant execute on function public.owns_avatar_folder(text) to authenticated;
grant execute on function public.set_avatar(text) to authenticated;
grant execute on function public.set_team_avatar(uuid, text) to authenticated;

revoke update on public.teams from authenticated;
grant update (name) on public.teams to authenticated;
