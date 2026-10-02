-- READ ONLY. Verify Dashboard URL project hcjfxbynqzsaidlwvdfx before running.
begin read only;
set local statement_timeout = '15s';
select 'database' as check_name, jsonb_build_object(
  'version', current_setting('server_version'),
  'read_only', current_setting('transaction_read_only'),
  'migration_history_exists', to_regclass('supabase_migrations.schema_migrations') is not null,
  'uuid_builtin', to_regprocedure('pg_catalog.gen_random_uuid()') is not null,
  'auth_users', to_regclass('auth.users') is not null,
  'auth_uid', to_regprocedure('auth.uid()') is not null) as result
union all
select 'extensions', coalesce(jsonb_agg(jsonb_build_object('name',extname,'version',extversion)), '[]')
from pg_extension
union all
select 'api_roles', jsonb_agg(jsonb_build_object('name',rolname,'bypassrls',rolbypassrls))
from pg_roles where rolname in ('anon','authenticated','service_role','authenticator')
union all
select 'public_tables', coalesce(jsonb_agg(jsonb_build_object('name',c.relname,'rls',c.relrowsecurity)), '[]')
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind='r'
union all
select 'public_functions', coalesce(jsonb_agg(jsonb_build_object(
 'name',p.proname,'args',pg_get_function_arguments(p.oid),
 'security_definer',p.prosecdef,'config',p.proconfig,
 'pt412',strpos(p.prosrc,'''PT412''')>0,
 'custom_40001',strpos(p.prosrc,'''40001''')>0)), '[]')
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public'
union all
select 'policies', coalesce(jsonb_agg(jsonb_build_object(
 'table',tablename,'policy',policyname,'roles',roles,'command',cmd)), '[]')
from pg_policies where schemaname='public'
union all
select 'client_grants', coalesce(jsonb_agg(jsonb_build_object(
 'table',table_name,'grantee',grantee,'privilege',privilege_type)), '[]')
from information_schema.table_privileges where table_schema='public'
and grantee in ('anon','authenticated','service_role')
union all
select 'correction_relationship', coalesce(jsonb_agg(pg_get_constraintdef(oid)), '[]')
from pg_constraint where conname='actual_fill_corrections_fill_id_fkey'
and conrelid=to_regclass('public.actual_fill_corrections');
rollback;
