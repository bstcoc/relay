create table public.licenses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  holder text not null check (char_length(btrim(holder)) between 1 and 128),
  plan text not null check (plan in ('enterprise', 'developer')),
  expires date not null,
  key text not null,
  checkout text unique,
  created_at timestamptz not null default now()
);

create index licenses_user on public.licenses (user_id, expires desc);

alter table public.licenses enable row level security;

create policy "a holder reads their own licenses" on public.licenses for select to authenticated
using (user_id = (select auth.uid()));

revoke all on public.licenses from anon, authenticated;
grant select on public.licenses to authenticated;
