create function public.verified() returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(auth.jwt() ->> 'aal', 'aal1') = 'aal2'
    or not exists (select 1 from auth.mfa_factors f where f.user_id = auth.uid() and f.status = 'verified')
$$;

create or replace function public.role_in(workspace uuid) returns public.role
language sql stable security definer set search_path = '' as $$
  select m.role from public.members m
  where m.workspace_id = workspace and m.user_id = auth.uid() and public.verified()
$$;

create or replace function public.shares_workspace(other uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.verified() and exists (
    select 1 from public.members mine join public.members theirs using (workspace_id)
    where mine.user_id = auth.uid() and theirs.user_id = other
  )
$$;

create or replace function public.confirmed_email() returns text
language sql stable security definer set search_path = '' as $$
  select lower(u.email) from auth.users u
  where u.id = auth.uid() and u.email_confirmed_at is not null and public.verified()
$$;

create or replace function public.create_company(company_name text, workspace_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  company uuid;
  workspace uuid;
begin
  if auth.uid() is null or not public.verified() then
    raise exception 'sign in first' using errcode = '42501';
  end if;
  insert into public.companies (name, created_by) values (btrim(company_name), auth.uid()) returning id into company;
  insert into public.workspaces (company_id, name) values (company, btrim(workspace_name)) returning id into workspace;
  insert into public.members (workspace_id, user_id, role) values (workspace, auth.uid(), 'owner');
  perform public.record(workspace, 'company.created', jsonb_build_object('company', company_name, 'workspace', workspace_name));
  return workspace;
end
$$;

create or replace function public.create_workspace(company uuid, workspace_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  workspace uuid;
begin
  if not exists (
    select 1 from public.workspaces w
    where w.company_id = company and public.role_in(w.id) in ('owner', 'admin')
  ) then
    raise exception 'only an owner or an admin of the company can add a workspace' using errcode = '42501';
  end if;
  insert into public.workspaces (company_id, name) values (company, btrim(workspace_name)) returning id into workspace;
  insert into public.members (workspace_id, user_id, role) values (workspace, auth.uid(), 'owner');
  perform public.record(workspace, 'workspace.created', jsonb_build_object('workspace', workspace_name));
  return workspace;
end
$$;

drop policy "see own and teammates' profiles" on public.profiles;
create policy "see own and teammates' profiles" on public.profiles for select to authenticated
using ((user_id = (select auth.uid()) and (select public.verified())) or public.shares_workspace(user_id));
drop policy "edit own profile" on public.profiles;
create policy "edit own profile" on public.profiles for update to authenticated
using (user_id = (select auth.uid()) and (select public.verified()))
with check (user_id = (select auth.uid()));
