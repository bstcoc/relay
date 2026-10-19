create or replace function public.migration_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  source public.connections;
  target public.connections;
begin
  if tg_op = 'INSERT' then
    select * into source from public.connections where id = new.source_id and workspace_id = new.workspace_id;
    select * into target from public.connections where id = new.target_id and workspace_id = new.workspace_id;
    if source.id is null or target.id is null or source.id = target.id then
      raise exception 'a migration runs between two connections of its own workspace' using errcode = '42501';
    end if;
    new.source_name := source.name;
    new.target_name := target.name;
    new.target_environment := target.environment;
    perform public.record(new.workspace_id, 'migration.started',
      jsonb_build_object('source', new.source_name, 'target', new.target_name, 'anonymized', new.anonymized));
  elsif new.status is distinct from old.status then
    new.finished_at := now();
    perform public.record(new.workspace_id, 'migration.' || new.status,
      jsonb_build_object('source', new.source_name, 'target', new.target_name, 'rows', new.rows, 'findings', new.findings));
  end if;
  return new;
end
$$;

revoke all on function public.migration_changed() from public, anon, authenticated;
