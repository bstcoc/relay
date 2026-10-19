create function public.invited_to(workspace uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.invitations i
    where i.workspace_id = workspace and i.accepted_at is null and i.email = public.confirmed_email()
  )
$$;

create policy "invitees see the workspace they are invited to" on public.workspaces for select to authenticated
using (public.invited_to(id));
