begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, email, email_confirmed_at, raw_user_meta_data, aud, role)
values
  ('11111111-1111-1111-1111-111111111111', 'ana@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('22222222-2222-2222-2222-222222222222', 'bo@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('33333333-3333-3333-3333-333333333333', 'cy@relay.test', now(), '{}', 'authenticated', 'authenticated');

create function pg_temp.act_as(who uuid) returns void language sql as $$
  select set_config('role', 'authenticated', true),
         set_config('request.jwt.claims',
           json_build_object('sub', who, 'role', 'authenticated', 'aal', 'aal1')::text, true)
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
create temp table ws on commit drop as select public.create_team('Acme') as id;
grant select on ws to authenticated;

reset role;
insert into public.members (team_id, user_id, role)
select id, '22222222-2222-2222-2222-222222222222', 'viewer' from ws;
update public.profiles set display_name = 'Bo' where user_id = '22222222-2222-2222-2222-222222222222';

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select results_eq(
  $$ select email, role::text from public.team_members((select id from ws)) $$,
  $$ values ('ana@relay.test', 'owner'), ('bo@relay.test', 'viewer') $$,
  'a member sees every teammate with their email and role');
select is((select display_name from public.team_members((select id from ws)) where email = 'bo@relay.test'), 'Bo',
  'the display name comes with the email');
select isnt((select joined_at from public.team_members((select id from ws)) limit 1), null, 'the joining date is given');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
select is((select count(*)::int from public.team_members((select id from ws))), 0,
  'someone outside the team sees nobody');

set local role anon;
select throws_ok($$ select * from public.team_members('00000000-0000-0000-0000-000000000000') $$, '42501', null,
  'an anonymous caller cannot list members');

select * from finish();
rollback;
