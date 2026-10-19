alter table public.connections drop constraint connections_definition_check;
alter table public.connections add constraint connections_definition_check check (
  jsonb_typeof(definition) = 'object'
  and not definition ?| array['password', 'secret', 'sshSecret', 'sshPassword', 'token', 'path', 'sslCa', 'sshKey']
  and position('${' in definition::text) = 0
);
