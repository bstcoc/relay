begin;
create extension if not exists pgtap with schema extensions;
select plan(10);

insert into auth.users (id, email, email_confirmed_at, raw_user_meta_data, aud, role)
values
  ('11111111-1111-1111-1111-111111111111', 'ana@relay.test', now(), '{}', 'authenticated', 'authenticated'),
  ('22222222-2222-2222-2222-222222222222', 'bo@relay.test', now(), '{}', 'authenticated', 'authenticated');

create function pg_temp.act_as(who uuid, address text) returns void language sql as $$
  select set_config('role', 'authenticated', true),
         set_config('request.jwt.claims',
           json_build_object('sub', who, 'email', address, 'role', 'authenticated', 'aal', 'aal2')::text, true)
$$;

select pg_temp.act_as('11111111-1111-1111-1111-111111111111', 'ana@relay.test');
create temp table ws on commit drop as select public.create_team('Acme') as id;
grant select on ws to authenticated;
select public.invite((select id from ws), 'bo@relay.test', 'member');

select lives_ok($$ insert into storage.objects (bucket_id, name)
  values ('avatars', 'users/11111111-1111-1111-1111-111111111111/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.webp') $$,
  'a user uploads into their own folder');
select throws_ok($$ insert into storage.objects (bucket_id, name)
  values ('avatars', 'users/22222222-2222-2222-2222-222222222222/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.webp') $$, '42501', null,
  'a user cannot upload into someone else''s folder');
select throws_ok($$ insert into storage.objects (bucket_id, name)
  values ('avatars', 'users/11111111-1111-1111-1111-111111111111/../../teams/x.webp') $$, '42501', null,
  'a name that climbs out of its folder is refused');
select lives_ok($$ select public.set_avatar('users/11111111-1111-1111-1111-111111111111/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.webp') $$,
  'a user picks their own upload');
select is((select avatar_path from public.profiles where user_id = auth.uid()),
  'users/11111111-1111-1111-1111-111111111111/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.webp', 'the profile keeps the path, not the picture');

select lives_ok(format($$ insert into storage.objects (bucket_id, name) values ('avatars', 'teams/%s/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.webp') $$,
  (select id from ws)), 'the owner uploads the team picture');
select lives_ok(format($$ select public.set_team_avatar('%s', 'teams/%s/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.webp') $$,
  (select id from ws), (select id from ws)), 'the owner sets the team picture');

select pg_temp.act_as('22222222-2222-2222-2222-222222222222', 'bo@relay.test');
select public.accept_invitation((select id from public.invitations limit 1));
select throws_ok($$ select public.set_avatar('users/11111111-1111-1111-1111-111111111111/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.webp') $$, '42501', null,
  'a user cannot take someone else''s picture');
select throws_ok(format($$ insert into storage.objects (bucket_id, name) values ('avatars', 'teams/%s/cccccccc-cccc-cccc-cccc-cccccccccccc.webp') $$,
  (select id from ws)), '42501', null, 'a member cannot upload the team picture');
select throws_ok(format($$ select public.set_team_avatar('%s', null) $$, (select id from ws)), '42501', null,
  'a member cannot change the team picture');

select * from finish();
rollback;
