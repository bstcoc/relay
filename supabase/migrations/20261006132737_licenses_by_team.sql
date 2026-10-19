delete from public.licenses;

alter table public.licenses
  add column company_id uuid not null references public.companies on delete cascade;

create index licenses_company on public.licenses (company_id, expires desc);

drop policy "a holder reads their own licenses" on public.licenses;

create policy "a team reads its licenses" on public.licenses for select to authenticated
using (
  user_id = (select auth.uid())
  or exists (
    select 1 from public.workspaces w
    where w.company_id = licenses.company_id and public.role_in(w.id) is not null
  )
);
