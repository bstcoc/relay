drop trigger team_deleting on public.teams;
drop function public.team_deleting();

create or replace function public.create_team(team_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  team uuid;
begin
  if auth.uid() is null or not public.verified() then
    raise exception 'sign in first' using errcode = '42501';
  end if;
  insert into public.teams (name) values (btrim(team_name)) returning id into team;
  insert into public.members (team_id, user_id, role) values (team, auth.uid(), 'owner');
  perform public.record(team, 'team.created', jsonb_build_object('team', btrim(team_name)));
  return team;
end
$$;

revoke select on public.teams from authenticated;

alter table public.teams
  drop column plan,
  drop column trial_ends_at,
  drop column paid_until,
  drop column seats,
  drop column stripe_customer,
  drop column stripe_subscription;

grant select (id, name, avatar_path, anonymize_by_default, created_at) on public.teams to authenticated;
