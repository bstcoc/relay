begin;
create extension if not exists pgtap with schema extensions;
select plan(12);

insert into auth.users (id, email, email_confirmed_at, raw_user_meta_data, aud, role)
values
  ('11111111-1111-1111-1111-111111111111', 'ana@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('22222222-2222-2222-2222-222222222222', 'vic@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('33333333-3333-3333-3333-333333333333', 'cy@relay.test', now(), '{}', 'authenticated', 'authenticated');

create function pg_temp.act_as(who uuid) returns void language sql as $$
  select set_config('role', 'authenticated', true),
         set_config('request.jwt.claims', json_build_object('sub', who, 'role', 'authenticated', 'aal', 'aal1')::text, true)
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
create temp table ws on commit drop as select public.create_team('Acme') as id;
grant select on ws to authenticated;
insert into public.connections (team_id, name, kind, environment)
values ((select id from ws), 'ERP prod', 'postgresql', 'Production'), ((select id from ws), 'ERP test', 'postgresql', 'Test');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
create temp table other on commit drop as select public.create_team('Autre') as id;
grant select on other to authenticated;

reset role;
create temp table prod on commit drop as select id from public.connections where name = 'ERP prod';
grant select on prod to authenticated;
insert into public.members (team_id, user_id, role)
select id, '22222222-2222-2222-2222-222222222222', 'member' from ws;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$
  insert into public.migrations (team_id, source_id, target_id, source_name, target_name, target_environment, mappings, anonymized)
  select (select id from ws), s.id, t.id, 'Fake', 'Fake', 'Production',
    '[{"entity": "workers", "columns": [{"source": "full_name", "target": "full_name", "anonymize": "pseudonym"}]}]', true
  from public.connections s, public.connections t where s.name = 'ERP prod' and t.name = 'ERP test'
$$, 'a member starts a migration between two connections of the team');
select is((select action from public.audit_log order by id desc limit 1), 'migration.started',
  'starting a migration is in the audit log');
select is((select target_environment from public.migrations), 'Test',
  'a migration names its connections as the team knows them');
select throws_ok($$
  insert into public.migrations (team_id, source_name, target_name, target_environment, mappings, anonymized)
  values ((select id from ws), 'ERP prod', 'ERP test', 'Test', '[]', false)
$$, '42501', null, 'a migration without its connections never enters the audit log');
select throws_ok($$
  insert into public.migrations (team_id, source_id, target_id, source_name, target_name, target_environment, mappings, anonymized)
  select (select id from ws), s.id, t.id, s.name, t.name, t.environment,
    '[{"source_scope": {"expected_missing": "name = ''Ana''"}}]', false
  from public.connections s, public.connections t where s.name = 'ERP prod' and t.name = 'ERP test'
$$, '23514', null, 'a filter that may hold client values is never stored');
select throws_ok($$
  update public.migrations set status = 'verified', rows = 3, findings = 0,
    tables = '[{"table": "workers", "rows": 3, "sample": "Ana Martin"}]'
$$, '23514', null, 'the outcome holds counts, never a value');
update public.migrations set status = 'verified', rows = 3, findings = 0,
  tables = '[{"entity": "workers", "table": "workers", "rows": 3, "passed": 9, "review": 0, "fail": 0, "accepted": 0}]';
select is((select status from public.migrations), 'verified', 'whoever started it records its outcome');
select is((select action from public.audit_log order by id desc limit 1), 'migration.verified',
  'the outcome is in the audit log');
update public.migrations set status = 'failed';
select is((select status from public.migrations), 'verified', 'a finished migration cannot be rewritten');

select throws_ok($$
  insert into public.migrations (team_id, source_id, target_id, source_name, target_name, target_environment, mappings, anonymized, subsets)
  select (select id from ws), s.id, t.id, s.name, t.name, t.environment, '[]', false,
    '[{"table": "sites", "where": "name = ''Lyon''"}]'
  from public.connections s, public.connections t where s.name = 'ERP prod' and t.name = 'ERP test'
$$, '23514', null, 'a row filter, which may hold client values, is never stored');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is((select count(*)::int from public.migrations), 1, 'a teammate sees the migrations of the team');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
select throws_ok($$
  insert into public.migrations (team_id, source_id, target_id, source_name, target_name, target_environment, mappings, anonymized)
  select (select id from other), id, id, 'ERP prod', 'ERP prod', 'Test', '[]', false from prod
$$, '42501', null, 'a migration never points to connections of another team');

select * from finish();
rollback;
