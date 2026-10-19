alter table public.invitations add constraint invitations_not_owner check (role <> 'owner');
