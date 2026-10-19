begin;
create extension if not exists pgtap with schema extensions;
select plan(35);

insert into auth.users (id, email, email_confirmed_at, raw_user_meta_data, aud, role)
values
  ('11111111-1111-1111-1111-111111111111', 'ana@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('22222222-2222-2222-2222-222222222222', 'bo@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('33333333-3333-3333-3333-333333333333', 'cy@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('44444444-4444-4444-4444-444444444444', 'dee@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('55555555-5555-5555-5555-555555555555', 'eve@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('66666666-6666-6666-6666-666666666666', 'fay@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('77777777-7777-7777-7777-777777777777', 'gus@relay.test', now(), '{}', 'authenticated', 'authenticated');

create function pg_temp.act_as(who uuid) returns void language sql as $$
  select set_config('role', 'authenticated', true),
         set_config('request.jwt.claims',
           json_build_object('sub', who, 'role', 'authenticated', 'aal', 'aal1')::text, true)
$$;

create function pg_temp.actions(team uuid) returns text[] language sql as $$
  select array_agg(action order by id) from public.audit_log where team_id = team
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
create temp table ws on commit drop as select public.create_team('Acme') as id;
grant select on ws to authenticated;

reset role;
insert into public.members (team_id, user_id, role)
select id, who, given from ws, (values
  ('22222222-2222-2222-2222-222222222222'::uuid, 'admin'::public.role),
  ('33333333-3333-3333-3333-333333333333', 'member'),
  ('44444444-4444-4444-4444-444444444444', 'viewer')) as joining(who, given);

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ select public.set_role((select id from ws), '33333333-3333-3333-3333-333333333333', 'approver') $$,
  'the owner changes a role');
select is((select role::text from public.members where user_id = '33333333-3333-3333-3333-333333333333'), 'approver',
  'the new role is applied');
select throws_ok($$ select public.set_role((select id from ws), '55555555-5555-5555-5555-555555555555', 'admin') $$,
  'P0002', null, 'changing the role of someone outside the team is refused');
update public.teams set name = 'Acme SA' where id = (select id from ws);

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
select is((select name from public.teams), 'Acme SA', 'a member reads the team');

select pg_temp.act_as('44444444-4444-4444-4444-444444444444');
select throws_ok($$
  insert into public.connections (team_id, name, kind, environment) values ((select id from ws), 'ERP', 'postgresql', 'Test')
$$, '42501', null, 'a viewer cannot add a connection');
update public.teams set name = 'Hijacked' where id = (select id from ws);
select is((select name from public.teams), 'Acme SA', 'a viewer cannot rename the team');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
delete from public.members where user_id = auth.uid();
select is((select role::text from public.members where user_id = auth.uid()), 'owner', 'the owner cannot leave the team');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
delete from public.members where user_id = '11111111-1111-1111-1111-111111111111';
select is((select count(*)::int from public.members where role = 'owner'), 1, 'an admin cannot remove the owner');
select public.invite((select id from ws), 'dee@relay.test', 'admin');
select public.set_role((select id from ws), '44444444-4444-4444-4444-444444444444', 'member');
select is((select count(*)::int from public.invitations where email = 'dee@relay.test'), 0,
  'changing a role withdraws the pending invitation of that member');
select public.invite((select id from ws), 'dee@relay.test', 'admin');
delete from public.members where user_id = '44444444-4444-4444-4444-444444444444';
select is((select count(*)::int from public.members where user_id = '44444444-4444-4444-4444-444444444444'), 0,
  'an admin removes a member');
select is((select count(*)::int from public.invitations where email = 'dee@relay.test'), 0,
  'removing a member withdraws their pending invitation');

select pg_temp.act_as('33333333-3333-3333-3333-333333333333');
delete from public.members where user_id = auth.uid();
select is((select count(*)::int from public.teams), 0, 'a member who left no longer sees the team');

reset role;
select throws_ok($$ delete from auth.users where id = '11111111-1111-1111-1111-111111111111' $$, '42501', null,
  'the account of an owner whose team has other members cannot be deleted');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
create temp table invited on commit drop as
select public.invite((select id from ws), address, 'member') as id, address
from unnest(array['eve@relay.test', 'fay@relay.test', 'gus@relay.test', 'bo@relay.test']) as address;
grant select on invited to authenticated;
select ok((select bool_and(expires_at between now() + interval '6 days' and now() + interval '8 days') from public.invitations),
  'an invitation lasts seven days');
delete from public.invitations where email = 'fay@relay.test';
select is((select count(*)::int from public.invitations where email = 'fay@relay.test'), 0, 'an admin revokes an invitation');

select pg_temp.act_as('55555555-5555-5555-5555-555555555555');
select lives_ok($$ select public.decline_invitation((select id from invited where address = 'eve@relay.test')) $$,
  'the invitee declines');
select is((select count(*)::int from public.invitations), 0, 'a declined invitation is gone');
select throws_ok($$ select public.decline_invitation((select id from invited where address = 'gus@relay.test')) $$,
  '42501', null, 'nobody declines someone else''s invitation');

reset role;
update public.invitations set expires_at = now() - interval '1 minute' where email = 'gus@relay.test';
select pg_temp.act_as('77777777-7777-7777-7777-777777777777');
select is((select count(*)::int from public.invitations), 0, 'an expired invitation is not shown to the invitee');
select is((select count(*)::int from public.teams), 0, 'an expired invitation no longer reveals the team');
select throws_ok($$ select public.accept_invitation((select id from invited where address = 'gus@relay.test')) $$,
  '42501', 'this invitation has expired, ask for a new one', 'an expired invitation cannot be accepted');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select lives_ok($$ select public.accept_invitation((select id from invited where address = 'bo@relay.test')) $$,
  'a member accepts an invitation to their own team');
select is((select role::text from public.members where user_id = auth.uid()), 'member',
  'accepting as a member applies the invited role');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select throws_ok($$ select public.transfer_ownership((select id from ws), '55555555-5555-5555-5555-555555555555') $$,
  '42501', null, 'the team is only handed to one of its members');
select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select throws_ok($$ select public.transfer_ownership((select id from ws), auth.uid()) $$,
  '42501', null, 'only the owner hands the team over');
select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select lives_ok($$ select public.transfer_ownership((select id from ws), '22222222-2222-2222-2222-222222222222') $$,
  'the owner hands the team over');
select is((select array_agg(role::text order by user_id) from public.members),
  array['admin', 'owner'], 'the new owner owns the team and the former owner becomes an admin');

reset role;
select is(pg_temp.actions((select id from ws)), array[
  'team.created', 'member.role_changed', 'team.renamed',
  'member.invited', 'member.role_changed', 'invitation.revoked', 'member.invited', 'member.removed', 'invitation.revoked',
  'member.left',
  'member.invited', 'member.invited', 'member.invited', 'member.invited',
  'invitation.revoked', 'invitation.declined', 'member.role_changed', 'team.ownership_transferred'
], 'every change to the team is in the audit log');
select throws_ok($$ insert into public.members (team_id, user_id, role)
  values ((select id from ws), '33333333-3333-3333-3333-333333333333', 'owner') $$,
  '23505', null, 'a team never has two owners');

select pg_temp.act_as('11111111-1111-1111-1111-111111111111');
select throws_ok($$ select public.delete_team((select id from ws)) $$, '42501', null, 'an admin cannot delete the team');
delete from public.members where user_id = auth.uid();
select is((select count(*)::int from public.teams), 0, 'the former owner leaves like any member');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222');
select lives_ok($$ select public.delete_team((select id from ws)) $$, 'the owner deletes the team');
reset role;
select is((select count(*)::int from public.teams where id = (select id from ws)), 0, 'the team is gone');
select is((select count(*)::int from public.invitations where team_id = (select id from ws)), 0,
  'its invitations go with it');

select pg_temp.act_as('66666666-6666-6666-6666-666666666666');
create temp table solo on commit drop as select public.create_team('Solo') as id;
reset role;
delete from auth.users where id = '66666666-6666-6666-6666-666666666666';
select is((select count(*)::int from public.teams where id = (select id from solo)), 0,
  'a team is deleted when its last member goes');

select * from finish();
rollback;
