create function public.team_members(team uuid)
returns table (user_id uuid, display_name text, avatar_url text, avatar_path text, email text, role public.role, joined_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select m.user_id, coalesce(p.display_name, ''), p.avatar_url, p.avatar_path, u.email::text, m.role, m.created_at
  from public.members m
  join auth.users u on u.id = m.user_id
  left join public.profiles p on p.user_id = m.user_id
  where m.team_id = team and public.role_in(team) is not null
  order by m.created_at
$$;

revoke all on function public.team_members(uuid) from public, anon;
grant execute on function public.team_members(uuid) to authenticated;
