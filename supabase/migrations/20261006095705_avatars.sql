alter table public.profiles add column avatar_path text;
alter table public.workspaces add column avatar_path text;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 524288, array['image/webp', 'image/png']);

create function public.owns_avatar_folder(object_name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select object_name ~ '^(users|workspaces)/[0-9a-f-]{36}/[0-9a-f-]{36}\.(webp|png)$' and case split_part(object_name, '/', 1)
    when 'users' then split_part(object_name, '/', 2) = (select auth.uid())::text and public.verified()
    when 'workspaces' then public.is_admin(split_part(object_name, '/', 2)::uuid)
    else false
  end
$$;

create policy "upload one's own avatars" on storage.objects for insert to authenticated
with check (bucket_id = 'avatars' and public.owns_avatar_folder(name));
create policy "remove one's own avatars" on storage.objects for delete to authenticated
using (bucket_id = 'avatars' and public.owns_avatar_folder(name));

create function public.set_avatar(path text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if path is not null and not (
    split_part(path, '/', 1) = 'users' and public.owns_avatar_folder(path)
    and exists (select 1 from storage.objects o where o.bucket_id = 'avatars' and o.name = path)
  ) then
    raise exception 'this picture is not one of your uploads' using errcode = '42501';
  end if;
  update public.profiles set avatar_path = path where user_id = auth.uid();
end
$$;

create function public.set_workspace_avatar(workspace uuid, path text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_admin(workspace) then
    raise exception 'only an admin changes the team picture' using errcode = '42501';
  end if;
  if path is not null and not (
    split_part(path, '/', 1) = 'workspaces' and split_part(path, '/', 2) = workspace::text
    and exists (select 1 from storage.objects o where o.bucket_id = 'avatars' and o.name = path)
  ) then
    raise exception 'this picture is not one of this team''s uploads' using errcode = '42501';
  end if;
  update public.workspaces set avatar_path = path where id = workspace;
  perform public.record(workspace, 'workspace.avatar', '{}');
end
$$;

revoke all on function public.owns_avatar_folder(text) from public, anon;
revoke all on function public.set_avatar(text) from public, anon;
revoke all on function public.set_workspace_avatar(uuid, text) from public, anon;
grant execute on function public.owns_avatar_folder(text) to authenticated;
grant execute on function public.set_avatar(text) to authenticated;
grant execute on function public.set_workspace_avatar(uuid, text) to authenticated;
