alter table public.invitations add column expires_at timestamptz;
update public.invitations set expires_at = created_at + interval '7 days';
alter table public.invitations
  alter column expires_at set default now() + interval '7 days',
  alter column expires_at set not null;

alter table public.invitations alter column invited_by drop not null;
alter table public.invitations drop constraint invitations_invited_by_fkey;
alter table public.invitations add constraint invitations_invited_by_fkey
  foreign key (invited_by) references auth.users on delete set null;

create unique index members_one_owner on public.members (team_id) where role = 'owner';

create or replace function public.record(team uuid, what text, details jsonb default '{}') returns void
language sql security definer set search_path = '' as $$
  insert into public.audit_log (team_id, actor, action, detail)
  select team, (select u.id from auth.users u where u.id = auth.uid()), what, details where exists (select 1 from public.teams t where t.id = team)
$$;

create or replace function public.invited_to(team uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.invitations i
    where i.team_id = team and i.accepted_at is null and i.expires_at > now() and i.email = public.confirmed_email()
  )
$$;

create or replace function public.invite(team uuid, address text, given public.role default 'member') returns uuid
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
  do update set role = excluded.role, invited_by = excluded.invited_by, created_at = now(),
    expires_at = now() + interval '7 days', accepted_at = null
  returning id into invitation;
  perform public.record(team, 'member.invited', jsonb_build_object('email', lower(btrim(address)), 'role', given));
  return invitation;
end
$$;

create or replace function public.accept_invitation(invitation uuid) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  pending public.invitations;
begin
  select * into pending from public.invitations
  where id = invitation and accepted_at is null and email = public.confirmed_email();
  if pending.id is null then
    raise exception 'no pending invitation for this account' using errcode = '42501';
  end if;
  if pending.expires_at <= now() then
    raise exception 'this invitation has expired, ask for a new one' using errcode = '42501';
  end if;
  if exists (select 1 from public.members m where m.team_id = pending.team_id and m.user_id = auth.uid()) then
    update public.members set role = pending.role
    where team_id = pending.team_id and user_id = auth.uid() and role <> 'owner';
  else
    insert into public.members (team_id, user_id, role) values (pending.team_id, auth.uid(), pending.role);
    perform public.record(pending.team_id, 'member.joined', jsonb_build_object('role', pending.role));
  end if;
  update public.invitations set accepted_at = now() where id = invitation;
  return pending.team_id;
end
$$;

create function public.decline_invitation(invitation uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  delete from public.invitations
  where id = invitation and accepted_at is null and email = public.confirmed_email();
  if not found then
    raise exception 'no pending invitation for this account' using errcode = '42501';
  end if;
end
$$;

create or replace function public.set_role(team uuid, member uuid, given public.role) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_admin(team) then
    raise exception 'only an owner or an admin can change a role' using errcode = '42501';
  end if;
  if given = 'owner' or (select role from public.members where team_id = team and user_id = member) = 'owner' then
    raise exception 'the owner role cannot be given or taken here' using errcode = '42501';
  end if;
  update public.members set role = given where team_id = team and user_id = member;
  if not found then
    raise exception 'this person is not a member of the team' using errcode = 'P0002';
  end if;
  delete from public.invitations i using auth.users u
  where u.id = member and i.team_id = team and i.email = lower(u.email) and i.accepted_at is null;
end
$$;

create function public.transfer_ownership(team uuid, member uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if public.role_in(team) is distinct from 'owner' then
    raise exception 'only the owner hands the team over' using errcode = '42501';
  end if;
  perform 1 from public.members m where m.team_id = team and m.user_id = member for update;
  if member = auth.uid() or not found then
    raise exception 'the new owner must be another member of the team' using errcode = '42501';
  end if;
  update public.members set role = 'admin' where team_id = team and user_id = auth.uid();
  update public.members set role = 'owner' where team_id = team and user_id = member;
  perform public.record(team, 'team.ownership_transferred', jsonb_build_object('from', auth.uid(), 'to', member));
end
$$;

create function public.delete_team(team uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if public.role_in(team) is distinct from 'owner' then
    raise exception 'only the owner deletes the team' using errcode = '42501';
  end if;
  delete from public.teams where id = team;
end
$$;

create function public.team_deleting() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if old.stripe_subscription is not null then
    raise exception 'cancel the team''s subscription before deleting it' using errcode = '42501';
  end if;
  return old;
end
$$;

create function public.team_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.name is distinct from old.name then
    perform public.record(new.id, 'team.renamed', jsonb_build_object('from', old.name, 'to', new.name));
  end if;
  if new.anonymize_by_default is distinct from old.anonymize_by_default then
    perform public.record(new.id, 'team.anonymization_changed', jsonb_build_object('anonymize', new.anonymize_by_default));
  end if;
  return null;
end
$$;

create function public.member_leaving() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if old.role = 'owner'
    and exists (select 1 from public.teams t where t.id = old.team_id)
    and exists (select 1 from public.members m where m.team_id = old.team_id and m.user_id <> old.user_id) then
    raise exception 'the owner hands the team over before leaving it' using errcode = '42501';
  end if;
  return old;
end
$$;

create function public.member_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' then
    if new.role is distinct from old.role and 'owner' not in (old.role, new.role) then
      perform public.record(new.team_id, 'member.role_changed',
        jsonb_build_object('member', new.user_id, 'from', old.role, 'role', new.role));
    end if;
    return null;
  end if;
  perform public.record(old.team_id, case when old.user_id = auth.uid() then 'member.left' else 'member.removed' end,
    jsonb_build_object('member', old.user_id, 'role', old.role));
  delete from public.invitations i using auth.users u
  where u.id = old.user_id and i.team_id = old.team_id and i.email = lower(u.email) and i.accepted_at is null;
  if not exists (select 1 from public.members m where m.team_id = old.team_id) then
    delete from public.teams where id = old.team_id;
  end if;
  return null;
end
$$;

create function public.invitation_withdrawn() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if old.accepted_at is null then
    perform public.record(old.team_id,
      case when old.email = public.confirmed_email() then 'invitation.declined' else 'invitation.revoked' end,
      jsonb_build_object('email', old.email, 'role', old.role));
  end if;
  return null;
end
$$;

create trigger team_deleting before delete on public.teams
for each row execute function public.team_deleting();
create trigger team_changed after update on public.teams
for each row execute function public.team_changed();
create trigger member_leaving before delete on public.members
for each row execute function public.member_leaving();
create trigger member_changed after update or delete on public.members
for each row execute function public.member_changed();
create trigger invitation_withdrawn after delete on public.invitations
for each row execute function public.invitation_withdrawn();

drop policy "admins and invitees see invitations" on public.invitations;
create policy "admins and invitees see invitations" on public.invitations for select to authenticated
using (public.is_admin(team_id) or (email = public.confirmed_email() and expires_at > now()));

revoke all on function public.team_deleting() from public, anon, authenticated;
revoke all on function public.team_changed() from public, anon, authenticated;
revoke all on function public.member_leaving() from public, anon, authenticated;
revoke all on function public.member_changed() from public, anon, authenticated;
revoke all on function public.invitation_withdrawn() from public, anon, authenticated;
revoke all on function public.decline_invitation(uuid) from public, anon;
revoke all on function public.transfer_ownership(uuid, uuid) from public, anon;
revoke all on function public.delete_team(uuid) from public, anon;
grant execute on function public.decline_invitation(uuid) to authenticated;
grant execute on function public.transfer_ownership(uuid, uuid) to authenticated;
grant execute on function public.delete_team(uuid) to authenticated;

revoke select on public.teams from authenticated;
grant select (id, name, avatar_path, plan, trial_ends_at, paid_until, seats, anonymize_by_default, created_at)
on public.teams to authenticated;
grant select, update on public.teams to service_role;
grant select on public.members to service_role;
