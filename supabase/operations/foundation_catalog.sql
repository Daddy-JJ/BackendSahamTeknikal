-- READ ONLY; compares application DDL, never rows, identities or credentials.
begin read only;
set local statement_timeout = '15s';
set local search_path = public, pg_catalog;
with relations as (
  select c.* from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relkind in ('r','p','v','m','S','f')
), functions as (
  select p.* from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public'
), inventory as (
  select 'relations' category, c.relname::text object_key, jsonb_build_object(
    'kind',c.relkind,'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,
    'owner',pg_get_userbyid(c.relowner),'persistence',c.relpersistence,
    'replica_identity',c.relreplident,'options',c.reloptions) detail from relations c
  union all
  select 'columns',c.relname||'.'||a.attnum, jsonb_build_object(
    'name',a.attname,'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,
    'default',pg_get_expr(d.adbin,d.adrelid),'identity',a.attidentity,
    'generated',a.attgenerated,'dropped',a.attisdropped,'collation',co.collname)
  from relations c join pg_attribute a on a.attrelid=c.oid and a.attnum>0
  left join pg_attrdef d on d.adrelid=c.oid and d.adnum=a.attnum
  left join pg_collation co on co.oid=a.attcollation
  union all
  select 'constraints',c.relname||'.'||k.conname, jsonb_build_object(
    'definition',pg_get_constraintdef(k.oid),'validated',k.convalidated,
    'deferrable',k.condeferrable,'deferred',k.condeferred)
  -- PG18 catalogs NOT NULL separately; attnotnull above covers it on PG17/18.
  from relations c join pg_constraint k on k.conrelid=c.oid where k.contype <> 'n'
  union all
  select 'indexes',i.relname, jsonb_build_object('definition',pg_get_indexdef(i.oid),
    'valid',x.indisvalid,'ready',x.indisready,'replica_identity',x.indisreplident)
  from relations c join pg_index x on x.indrelid=c.oid join pg_class i on i.oid=x.indexrelid
  union all
  select 'triggers',c.relname||'.'||t.tgname, jsonb_build_object(
    'definition',pg_get_triggerdef(t.oid),'enabled',t.tgenabled)
  from relations c join pg_trigger t on t.tgrelid=c.oid where not t.tgisinternal
  union all
  select 'functions',p.proname||'('||pg_get_function_identity_arguments(p.oid)||')',
    -- Normalize Windows line endings only, never SQL whitespace or body tokens.
    jsonb_build_object('definition',replace(pg_get_functiondef(p.oid),chr(13)||chr(10),chr(10)),
      'owner',pg_get_userbyid(p.proowner)) from functions p
  union all
  select 'policies',schemaname||'.'||tablename||'.'||policyname,
    jsonb_build_object('roles',roles,'permissive',permissive,'command',cmd,
      'using',qual,'check',with_check) from pg_policies where schemaname='public'
  union all
  select 'table_grants',c.relname||'.'||coalesce(r.rolname,'PUBLIC')||'.'||a.privilege_type,
    jsonb_build_object('grantable',a.is_grantable,'grantor',pg_get_userbyid(a.grantor))
  from relations c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
  left join pg_roles r on r.oid=a.grantee
  union all
  select 'function_grants',p.proname||'('||pg_get_function_identity_arguments(p.oid)||').' ||
    coalesce(r.rolname,'PUBLIC')||'.'||a.privilege_type,
    jsonb_build_object('grantable',a.is_grantable,'grantor',pg_get_userbyid(a.grantor))
  from functions p cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
  left join pg_roles r on r.oid=a.grantee
  union all
  select 'column_grants',c.relname||'.'||att.attname||'.'||coalesce(r.rolname,'PUBLIC')||'.'||a.privilege_type,
    jsonb_build_object('grantable',a.is_grantable,'grantor',pg_get_userbyid(a.grantor))
  from relations c join pg_attribute att on att.attrelid=c.oid and att.attnum>0
  cross join lateral aclexplode(att.attacl) a left join pg_roles r on r.oid=a.grantee
), categories(category) as (values ('relations'),('columns'),('constraints'),('indexes'),
  ('triggers'),('functions'),('policies'),('table_grants'),('function_grants'),('column_grants'))
select c.category, count(i.object_key)::integer as object_count,
  encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_object('key',i.object_key,'detail',i.detail)
    order by i.object_key collate "C") filter(where i.object_key is not null),'[]')::text,'UTF8')),'hex') as sha256
from categories c left join inventory i using(category)
group by c.category order by c.category collate "C";
rollback;
