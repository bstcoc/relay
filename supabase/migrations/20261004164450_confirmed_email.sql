create function public.confirmed_email() returns text
language sql stable security definer set search_path = '' as $$
  select lower(u.email) from auth.users u where u.id = auth.uid() and u.email_confirmed_at is not null
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
  insert into public.members (workspace_id, user_id, role) values (pending.workspace_id, auth.uid(), pending.role)
  on conflict (workspace_id, user_id) do nothing;
  update public.invitations set accepted_at = now() where id = invitation;
  perform public.record(pending.workspace_id, 'member.joined', jsonb_build_object('role', pending.role));
  return pending.workspace_id;
end
$$;

create or replace function public.invite(workspace uuid, address text, given public.role default 'member') returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  invitation uuid;
begin
  if not public.is_admin(workspace) then
    raise exception 'only an owner or an admin can invite' using errcode = '42501';
  end if;
  insert into public.invitations (workspace_id, email, role, invited_by)
  values (workspace, lower(btrim(address)), given, auth.uid())
  on conflict (workspace_id, email)
  do update set role = excluded.role, invited_by = excluded.invited_by, created_at = now(), accepted_at = null
  returning id into invitation;
  perform public.record(workspace, 'member.invited', jsonb_build_object('email', lower(btrim(address)), 'role', given));
  return invitation;
end
$$;

drop policy "admins and invitees see invitations" on public.invitations;
create policy "admins and invitees see invitations" on public.invitations for select to authenticated
using (public.is_admin(workspace_id) or email = public.confirmed_email());

revoke all on function public.confirmed_email() from public, anon;
grant execute on function public.confirmed_email() to authenticated;
