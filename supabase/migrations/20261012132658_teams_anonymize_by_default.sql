alter table public.teams add column anonymize_by_default boolean not null default true;

grant update (anonymize_by_default) on public.teams to authenticated;
