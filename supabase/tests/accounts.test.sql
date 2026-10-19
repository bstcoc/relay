begin;
create extension if not exists pgtap with schema extensions;
select plan(25);

insert into auth.users (id, email, email_confirmed_at, raw_user_meta_data, aud, role)
values
  ('11111111-1111-1111-1111-111111111111', 'ana@relay.test', now(), '{"full_name": "Ana Martin"}', 'authenticated', 'authenticated'),
  ('22222222-2222-2222-2222-222222222222', 'bo@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('33333333-3333-3333-3333-333333333333', 'cy@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('44444444-4444-4444-4444-444444444444', 'dee@relay.test', null, '{}', 'authenticated', 'authenticated'),
  ('55555555-5555-5555-5555-555555555555', 'eve@relay.test', now(), '{}', 'authenticated', 'authenticated');

insert into auth.mfa_factors (id, user_id, factor_type, status, created_at, updated_at)
values (gen_random_uuid(), '55555555-5555-5555-5555-555555555555', 'totp', 'verified', now(), now());

select is((select display_name from public.profiles where user_id = '11111111-1111-1111-1111-111111111111'),
  'Ana Martin', 'a new account gets a profile named after it');

create function pg_temp.act_as(who uuid, address text, level text default 'aal1') returns void language sql as $$
  select set_config('role', 'authenticated', true),
         set_config('request.jwt.claims',
           json_build_object('sub', who, 'email', address, 'role', 'authenticated', 'aal', level)::text, true)
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111', 'ana@relay.test');
create temp table ws on commit drop as select public.create_team('Acme') as id;
grant select on ws to authenticated;

select is((select role::text from public.members where user_id = auth.uid()), 'owner',
  'the creator owns the team');
select is((select count(*)::int from public.teams), 1, 'the owner sees the team');
select ok((select anonymize_by_default from public.teams where id = (select id from ws)),
  'a new team anonymizes outside production by default');
update public.teams set anonymize_by_default = false where id = (select id from ws);
select is((select anonymize_by_default from public.teams where id = (select id from ws)), false,
  'an owner can turn off default anonymization');
select is((select array_agg(action order by id) from public.audit_log), array['team.created', 'team.anonymization_changed'],
  'creating the team and turning off anonymization are in the audit log');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222', 'bo@relay.test');
select is((select count(*)::int from public.teams), 0, 'an outsider sees no team');
select throws_ok($$ select public.invite((select id from ws), 'cy@relay.test') $$, '42501', null,
  'an outsider cannot invite');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111', 'ana@relay.test');
select throws_ok($$ select public.invite((select id from ws), 'eve@relay.test', 'owner') $$, '23514', null,
  'nobody is invited as an owner');
select lives_ok($$ select public.invite((select id from ws), 'Bo@Relay.test', 'member') $$, 'the owner invites');

create temp table unconfirmed on commit drop as select public.invite((select id from ws), 'dee@relay.test') as id;
grant select on unconfirmed to authenticated;

select pg_temp.act_as('44444444-4444-4444-4444-444444444444', 'dee@relay.test');
select throws_ok($$ select public.accept_invitation((select id from unconfirmed)) $$, '42501', null,
  'an unconfirmed address cannot accept, whatever its token claims');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222', 'bo@relay.test');
select is((select count(*)::int from public.invitations), 1, 'the invitee sees the invitation');
select is((select name from public.teams), 'Acme', 'the invitee sees the team they are invited to');
select lives_ok($$ select public.accept_invitation((select id from public.invitations limit 1)) $$,
  'the invitee accepts');
select is((select role::text from public.members where user_id = auth.uid()), 'member',
  'the invitee joins with the invited role');
select is((select count(*)::int from public.profiles), 2, 'teammates see each other''s profiles');
select throws_ok($$ select public.invite((select id from ws), 'cy@relay.test') $$, '42501', null,
  'a member cannot invite');
select throws_ok($$ select public.set_role((select id from ws), auth.uid(), 'admin') $$, '42501', null,
  'a member cannot promote themself');
select throws_ok($$ insert into public.audit_log (team_id, action) values ((select id from ws), 'forged') $$,
  '42501', null, 'nobody writes the audit log directly');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333', 'cy@relay.test');
select is((select count(*)::int from public.teams), 0, 'someone not invited sees no team');
select throws_ok($$ select public.accept_invitation((select id from public.invitations limit 1)) $$, '42501', null,
  'an invitation only works for its own address');

select pg_temp.act_as('55555555-5555-5555-5555-555555555555', 'eve@relay.test', 'aal2');
select lives_ok($$ select public.create_team('Azur') $$, 'a second factor opens the account');
select pg_temp.act_as('55555555-5555-5555-5555-555555555555', 'eve@relay.test');
select is((select count(*)::int from public.teams), 0,
  'a password alone shows nothing to an account that has a second factor');
select throws_ok($$ select public.create_team('Azur') $$, '42501', null,
  'a password alone changes nothing for an account that has a second factor');

select throws_ok($$ update public.profiles set avatar_url = 'https://tracker.example/pixel.png' where user_id = auth.uid() $$,
  '42501', null, 'a photo comes from the login provider, never from the account itself');

select * from finish();
rollback;
