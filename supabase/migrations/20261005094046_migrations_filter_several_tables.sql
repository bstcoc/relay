alter table public.migrations add column subsets jsonb not null default '[]' check (
  jsonb_typeof(subsets) = 'array'
  and not jsonb_path_exists(subsets, '$[*].keyvalue() ? (!(@.key like_regex "^(table|limit)$"))')
);

update public.migrations
set subsets = jsonb_build_array(jsonb_strip_nulls(jsonb_build_object('table', subset_table, 'limit', subset_limit)))
where subset_table is not null;

alter table public.migrations drop column subset_table, drop column subset_limit;

grant insert (workspace_id, source_id, target_id, source_name, target_name, target_environment, mappings,
  anonymized, subsets) on public.migrations to authenticated;
